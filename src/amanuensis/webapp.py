"""Small dependency-free HTTP application for selected-corpus passage search."""

from __future__ import annotations

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .search import PassageQuery, ResultOrder
from .search_engine import PassageSearchEngine


class SearchWebApplication:
    def __init__(self, engine: PassageSearchEngine) -> None:
        self.engine = engine
        asset_dir = Path(__file__).with_name("web")
        self._assets = {
            "/": ("text/html; charset=utf-8", asset_dir.joinpath("search.html")),
            "/assets/search.css": ("text/css; charset=utf-8", asset_dir.joinpath("search.css")),
            "/assets/search.js": (
                "text/javascript; charset=utf-8",
                asset_dir.joinpath("search.js"),
            ),
        }

    def handle(self, method: str, target: str, body: bytes = b"") -> tuple[int, str, bytes]:
        path = urlparse(target).path
        if method == "GET" and path in self._assets:
            content_type, asset_path = self._assets[path]
            return 200, content_type, asset_path.read_bytes()
        if method == "GET" and path == "/api/catalogue":
            return self._json(200, self._catalogue())
        if method == "POST" and path == "/api/search":
            try:
                request = json.loads(body.decode("utf-8"))
                return self._json(200, self._search(request))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                return self._json(400, {"error": str(exc)})
        return self._json(404, {"error": "not found"})

    def _catalogue(self) -> dict[str, Any]:
        books = self.engine.books()
        return {
            "corpora": self.engine.corpus_ids(),
            "books": [
                {
                    "book_id": book.book_id,
                    "title": book.title,
                    "format": book.format,
                    "status": book.status,
                    "message": book.message,
                    "unit_count": book.unit_count,
                    "corpus_ids": book.corpus_ids,
                }
                for book in books
            ],
        }

    def _search(self, request: dict[str, Any]) -> dict[str, Any]:
        text = str(request["query"]).strip()
        corpus_id = _optional_text(request.get("corpus_id"))
        raw_book_ids = request.get("book_ids", [])
        if not isinstance(raw_book_ids, list):
            raise ValueError("book_ids must be a list")
        scope = self.engine.store.resolve_scope(
            book_ids=(str(item) for item in raw_book_ids),
            corpus_id=corpus_id,
        )
        order = ResultOrder(str(request.get("order", ResultOrder.RELEVANCE.value)))
        limit = int(request.get("limit", 20))
        query = PassageQuery(text=text, scope=scope, limit=limit, order=order)
        excerpts = self.engine.search(query)
        titles = {book.book_id: book.title for book in self.engine.books()}
        return {
            "query": text,
            "scope": {
                "corpus_id": scope.corpus_id,
                "book_ids": sorted(scope.book_ids),
            },
            "count": len(excerpts),
            "excerpts": [
                {
                    **asdict(excerpt),
                    "book_title": titles.get(excerpt.book_id, excerpt.book_id),
                }
                for excerpt in excerpts
            ],
        }

    @staticmethod
    def _json(status: int, value: object) -> tuple[int, str, bytes]:
        return (
            status,
            "application/json; charset=utf-8",
            json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"),
        )


def serve_search_app(
    app: SearchWebApplication,
    *,
    host: str = "127.0.0.1",
    port: int = 8122,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self._dispatch("POST", self.rfile.read(length))

        def _dispatch(self, method: str, body: bytes = b"") -> None:
            status, content_type, response = app.handle(method, self.path, body)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(response)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Amanuensis passage search: http://{host}:{port}")
    server.serve_forever()


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
