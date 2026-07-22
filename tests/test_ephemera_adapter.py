from hashlib import md5
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from urllib.parse import parse_qs, urlparse

from amanuensis.acquisition import CandidateIntent, CatalogueQuery
from amanuensis.adapters.ephemera import AdapterError, EphemeraAdapter, RemoteState
from amanuensis.queue import AcquisitionState, SQLiteAcquisitionQueue
from amanuensis.workflow import AcquisitionCoordinator


BOOK_BYTES = b"fixture epub content\n"
BOOK_MD5 = md5(BOOK_BYTES, usedforsecurity=False).hexdigest()


class FixtureEphemeraHandler(BaseHTTPRequestHandler):
    status_reads = 0
    seen_query = {}

    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/search":
            type(self).seen_query = parse_qs(parsed.query)
            self._json(
                {
                    "results": [
                        {
                            "md5": "f" * 32,
                            "title": "Candide, a modern commentary",
                            "authors": ["Someone Else"],
                            "language": "en",
                            "format": "pdf",
                        },
                        {
                            "md5": BOOK_MD5,
                            "title": "Candide",
                            "authors": ["Voltaire"],
                            "language": "fr",
                            "format": "epub",
                            "filename": "Candide - Voltaire.epub",
                            "source": "fixture",
                        },
                    ],
                    "pagination": {
                        "page": 1,
                        "per_page": 50,
                        "has_next": False,
                        "estimated_total_results": 2,
                    },
                }
            )
            return
        if parsed.path == f"/api/queue/{BOOK_MD5}":
            type(self).status_reads += 1
            if type(self).status_reads == 1:
                self._json({"status": "downloading", "progress": 50})
            else:
                self._json({"status": "available", "progress": 100})
            return
        if parsed.path == f"/api/download/{BOOK_MD5}/file":
            self.send_response(200)
            self.send_header("Content-Type", "application/epub+zip")
            self.send_header("Content-Disposition", 'attachment; filename="Candide.epub"')
            self.send_header("Content-Length", str(len(BOOK_BYTES)))
            self.end_headers()
            self.wfile.write(BOOK_BYTES)
            return
        self.send_error(404)

    def do_POST(self):
        if self.path == f"/api/download/{BOOK_MD5}":
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self._json({"status": "queued", "position": 1})
            return
        self.send_error(404)

    def do_DELETE(self):
        if self.path == f"/api/download/{BOOK_MD5}":
            self._json({"success": True})
            return
        self.send_error(404)

    def _json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class EphemeraAdapterEndToEndTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureEphemeraHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        FixtureEphemeraHandler.status_reads = 0
        FixtureEphemeraHandler.seen_query = {}

    def test_full_search_queue_download_and_stage_flow(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteAcquisitionQueue(root / "state.db")
            coordinator = AcquisitionCoordinator(
                repository,
                EphemeraAdapter(self.base_url),
                root / "staging",
                poll_interval_seconds=0,
            )
            request = coordinator.submit(
                CatalogueQuery("Candide", author="Voltaire", languages=("fr",), formats=("epub",)),
                CandidateIntent("Candide", ("Voltaire",)),
            )

            transitions = coordinator.run_due(maximum_steps=10)
            completed = repository.get(request.identifier)

            self.assertGreaterEqual(len(transitions), 3)
            self.assertEqual(AcquisitionState.STAGED, completed.state)
            staged = Path(completed.staged_path)
            self.assertEqual(BOOK_BYTES, staged.read_bytes())
            self.assertEqual(root / "staging", staged.parent)
            self.assertEqual(["Voltaire"], FixtureEphemeraHandler.seen_query["author"])
            self.assertEqual(["fr"], FixtureEphemeraHandler.seen_query["lang"])
            event_names = [item["event"] for item in repository.events(request.identifier)]
            self.assertIn("candidate_queued", event_names)
            self.assertIn("file_staged", event_names)

    def test_actual_pagination_shape_is_normalised(self):
        page = EphemeraAdapter(self.base_url).search(CatalogueQuery("Candide"))

        self.assertEqual(2, page.total)
        self.assertEqual(1, page.total_pages)

    def test_already_queued_reply_uses_existing_state(self):
        adapter = _ReplyAdapter(
            {"status": "already_in_queue", "existing": {"status": "downloading", "progress": 42}}
        )
        candidate = EphemeraAdapter(self.base_url).search(CatalogueQuery("Candide")).items[1]

        download = adapter.queue(candidate)

        self.assertEqual(RemoteState.DOWNLOADING, download.state)
        self.assertEqual(42, download.progress)

    def test_checksum_mismatch_does_not_publish_partial_file(self):
        with TemporaryDirectory() as directory:
            adapter = EphemeraAdapter(self.base_url)
            page = adapter.search(CatalogueQuery("Candide"))
            wrong = page.items[1]
            wrong = type(wrong)(
                identifier="0" * 32,
                title=wrong.title,
                authors=wrong.authors,
                filename=wrong.filename,
                format=wrong.format,
            )
            with self.assertRaises(AdapterError):
                adapter._stream_verified(
                    source=_BytesSource(BOOK_BYTES),
                    final_path=Path(directory) / "wrong.epub",
                    expected_md5=wrong.identifier,
                    chunk_size=4,
                )
            self.assertFalse((Path(directory) / "wrong.epub").exists())
            self.assertEqual([], list(Path(directory).glob("*.part")))

    def test_iso_retry_time_marks_queued_download_as_delayed(self):
        download = EphemeraAdapter._normalise_download(
            BOOK_MD5,
            {"status": "queued", "nextRetryAt": "2030-01-02T03:04:05Z"},
        )

        self.assertEqual(RemoteState.DELAYED, download.state)
        self.assertEqual(1893553445.0, download.next_retry_at)

    def test_cancel_is_persisted_and_recorded(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteAcquisitionQueue(root / "state.db")
            coordinator = AcquisitionCoordinator(
                repository,
                EphemeraAdapter(self.base_url),
                root / "staging",
                poll_interval_seconds=0,
            )
            request = coordinator.submit(
                CatalogueQuery("Candide"), CandidateIntent("Candide", ("Voltaire",))
            )
            queued = coordinator.process_next()

            cancelled = coordinator.cancel_request(queued.identifier)

            self.assertEqual(AcquisitionState.CANCELLED, cancelled.state)
            self.assertEqual("request_cancelled", repository.events(request.identifier)[-1]["event"])


class _BytesSource:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def read(self, size):
        chunk = self.data[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class _ReplyAdapter(EphemeraAdapter):
    def __init__(self, reply):
        super().__init__("http://fixture.invalid")
        self.reply = reply

    def _request_json(self, method, path, *, query=None, payload=None):
        return dict(self.reply)
