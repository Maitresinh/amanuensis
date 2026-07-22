"""Command-line entry point for the modular acquisition pipeline."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time

from .acquisition import CandidateIntent, CatalogueQuery, ProviderError
from .adapters.ephemera import EphemeraAdapter
from .queue import AcquisitionState, SQLiteAcquisitionQueue
from .workflow import AcquisitionCoordinator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amanuensis", description="Amanuensis acquisition engine")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("EPHEMERA_API_URL", "http://ephemera:8286/api"),
        help="Ephemera compatibility API URL",
    )
    parser.add_argument(
        "--state-db",
        type=Path,
        default=Path(os.environ.get("AMANUENSIS_STATE_DB", "var/amanuensis.db")),
    )
    parser.add_argument(
        "--staging",
        type=Path,
        default=Path(os.environ.get("AMANUENSIS_STAGING_DIR", "var/staging")),
    )
    parser.add_argument(
        "--search-db",
        type=Path,
        default=Path(os.environ.get("AMANUENSIS_SEARCH_DB", "var/search.db")),
        help="SQLite source-text and passage metadata store",
    )
    parser.add_argument(
        "--qdrant-url",
        default=os.environ.get("QDRANT_URL", "http://localhost:6333"),
    )
    parser.add_argument(
        "--qdrant-collection",
        default=os.environ.get("QDRANT_COLLECTION", "amanuensis_passages"),
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("AMANUENSIS_EMBEDDING_MODEL", "BAAI/bge-m3"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="search the configured catalogue")
    _query_arguments(search)
    search.add_argument("--json", action="store_true")

    request = subparsers.add_parser("request", help="add a title to the durable acquisition queue")
    _query_arguments(request)
    request.add_argument("--requested-title", required=True)
    request.add_argument("--requested-author", action="append", default=[])
    request.add_argument("--preferred-language", action="append", default=[])
    request.add_argument("--preferred-format", action="append", default=[])
    request.add_argument("--run", action="store_true", help="start processing immediately")

    run = subparsers.add_parser("run", help="process due queue items")
    run.add_argument("--steps", type=int, default=100)
    run.add_argument("--wait", action="store_true", help="poll until no active item remains")
    run.add_argument("--timeout", type=float, default=1800)

    queue = subparsers.add_parser("queue", help="show acquisition requests")
    queue.add_argument("--state", choices=[state.value for state in AcquisitionState])
    queue.add_argument("--json", action="store_true")

    history = subparsers.add_parser("history", help="show one request history")
    history.add_argument("request_id")
    history.add_argument("--json", action="store_true")

    cancel = subparsers.add_parser("cancel", help="cancel one request")
    cancel.add_argument("request_id")

    retry = subparsers.add_parser("retry", help="put a failed request back at the end of the queue")
    retry.add_argument("request_id")

    index_text = subparsers.add_parser(
        "index-text",
        help="extract and index a text-bearing EPUB, PDF, or text file",
    )
    index_text.add_argument("book_id")
    index_text.add_argument("path", type=Path)
    index_text.add_argument("--title")
    index_text.add_argument("--corpus", action="append", default=[])
    index_text.add_argument("--json", action="store_true")

    content_search = subparsers.add_parser(
        "content-search",
        help="retrieve verbatim passages from selected books",
    )
    content_search.add_argument("query")
    content_search.add_argument("--book-id", action="append", default=[])
    content_search.add_argument("--corpus-id")
    content_search.add_argument("--limit", type=int, default=20)
    content_search.add_argument("--order", choices=["relevance", "reading"], default="relevance")
    content_search.add_argument("--json", action="store_true")

    serve = subparsers.add_parser(
        "serve-content-search",
        help="serve the selected-corpus passage search screen",
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8122)
    return parser


def _query_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("query")
    parser.add_argument("--author")
    parser.add_argument("--title")
    parser.add_argument("--language", action="append", default=[])
    parser.add_argument("--format", action="append", default=[])
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--content", action="append", default=[])


def _query(args: argparse.Namespace) -> CatalogueQuery:
    return CatalogueQuery(
        text=args.query,
        author=args.author,
        title=args.title,
        languages=tuple(args.language),
        formats=tuple(args.format),
        sources=tuple(args.source),
        content_types=tuple(args.content),
    )


def _coordinator(args: argparse.Namespace) -> AcquisitionCoordinator:
    return AcquisitionCoordinator(
        SQLiteAcquisitionQueue(args.state_db),
        EphemeraAdapter(args.api_url),
        args.staging,
    )


def _search_engine(args: argparse.Namespace):
    from qdrant_client import QdrantClient

    from .adapters.qdrant import QdrantHybridPassageIndex
    from .hybrid import BGEM3Encoder
    from .search_engine import PassageSearchEngine
    from .search_store import SQLiteSearchStore

    client = (
        QdrantClient(":memory:")
        if args.qdrant_url == ":memory:"
        else QdrantClient(url=args.qdrant_url)
    )
    index = QdrantHybridPassageIndex(
        client,
        BGEM3Encoder(args.embedding_model),
        collection_name=args.qdrant_collection,
    )
    return PassageSearchEngine(SQLiteSearchStore(args.search_db), index)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "search":
            page = EphemeraAdapter(args.api_url).search(_query(args))
            rows = [_candidate_dict(item) for item in page.items]
            if args.json:
                _print_json({"page": page.page, "total": page.total, "items": rows})
            else:
                for row in rows:
                    print(f"{row['md5']}  {row['title']}  [{row['format'] or '?'} / {row['language'] or '?'}]")
                    if row["authors"]:
                        print(f"  {', '.join(row['authors'])}")
            return 0

        if args.command in {"index-text", "content-search", "serve-content-search"}:
            engine = _search_engine(args)
            if args.command == "index-text":
                report = engine.index_file(
                    args.book_id,
                    args.path,
                    title=args.title,
                    corpus_ids=frozenset(args.corpus),
                )
                if args.json:
                    _print_json(asdict(report))
                else:
                    print(
                        f"{report.book_id}: {report.status.value}, "
                        f"{report.units} unite(s), {report.passages} passage(s)"
                    )
                    if report.message:
                        print(report.message)
                return 0
            if args.command == "content-search":
                from .search import PassageQuery, ResultOrder

                scope = engine.store.resolve_scope(
                    book_ids=args.book_id,
                    corpus_id=args.corpus_id,
                )
                excerpts = engine.search(
                    PassageQuery(
                        args.query,
                        scope,
                        limit=args.limit,
                        order=ResultOrder(args.order),
                    )
                )
                if args.json:
                    _print_json([asdict(item) for item in excerpts])
                else:
                    for item in excerpts:
                        print(f"{item.book_id} - {item.unit_label} [{item.start}:{item.end}]")
                        print(item.text)
                        print()
                return 0

            from .webapp import SearchWebApplication, serve_search_app

            serve_search_app(
                SearchWebApplication(engine),
                host=args.host,
                port=args.port,
            )
            return 0

        repository = SQLiteAcquisitionQueue(args.state_db)
        coordinator = AcquisitionCoordinator(repository, EphemeraAdapter(args.api_url), args.staging)
        if args.command == "request":
            record = coordinator.submit(
                _query(args),
                CandidateIntent(
                    title=args.requested_title,
                    authors=tuple(args.requested_author),
                    preferred_languages=tuple(args.preferred_language) or ("fr",),
                    preferred_formats=tuple(args.preferred_format) or ("epub", "pdf"),
                ),
            )
            print(f"Demande {record.identifier}: {record.intent.title} [{record.state.value}]")
            if args.run:
                updated = coordinator.process_next()
                if updated:
                    print(f"Etat: {updated.state.value}")
            return 0

        if args.command == "run":
            deadline = time.monotonic() + args.timeout
            processed = 0
            while True:
                batch = coordinator.run_due(maximum_steps=args.steps)
                processed += len(batch)
                if not args.wait or not repository.list() or time.monotonic() >= deadline:
                    break
                active = [item for item in repository.list() if item.state not in {
                    AcquisitionState.STAGED, AcquisitionState.FAILED_FINAL, AcquisitionState.CANCELLED
                }]
                if not active:
                    break
                due_times = [item.next_attempt_at for item in active if item.next_attempt_at]
                if not batch and due_times:
                    time.sleep(max(0.1, min(5.0, min(due_times) - time.time())))
                elif not batch:
                    break
            print(f"{processed} transition(s) traitee(s)")
            return 0

        if args.command == "queue":
            state = AcquisitionState(args.state) if args.state else None
            records = repository.list(state=state)
            rows = [_record_dict(item) for item in records]
            if args.json:
                _print_json(rows)
            else:
                for row in rows:
                    print(f"{row['id']}  {row['state']:<18} {row['title']}")
                    print(f"  mis a jour {row['updated_at']}  {row['error'] or ''}")
            return 0

        if args.command == "cancel":
            record = coordinator.cancel_request(args.request_id)
            print(f"Demande {record.identifier}: {record.state.value}")
            return 0

        if args.command == "retry":
            record = coordinator.retry_request(args.request_id)
            print(f"Demande {record.identifier}: {record.state.value}")
            return 0

        events = repository.events(args.request_id)
        if args.json:
            _print_json(events)
        else:
            for event in events:
                stamp = datetime.fromtimestamp(event["created_at"]).astimezone().isoformat(timespec="seconds")
                print(f"{stamp}  {event['state']:<18} {event['event']}")
        return 0
    except (OSError, ProviderError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2


def _candidate_dict(candidate) -> dict[str, object]:
    return {
        "md5": candidate.identifier,
        "title": candidate.title,
        "authors": candidate.authors,
        "format": candidate.format,
        "language": candidate.language,
        "source": candidate.source,
        "status": candidate.download_status,
    }


def _print_json(value: object) -> None:
    """Emit portable machine output even on legacy Windows console encodings."""

    print(json.dumps(value, ensure_ascii=True, default=str, sort_keys=True))


def _record_dict(record) -> dict[str, object]:
    return {
        "id": record.identifier,
        "state": record.state.value,
        "title": record.intent.title,
        "candidate": record.candidate.title if record.candidate else None,
        "attempts": record.attempts,
        "next_attempt_at": record.next_attempt_at,
        "staged_path": record.staged_path,
        "error": record.last_error,
        "created_at": datetime.fromtimestamp(record.created_at).astimezone().isoformat(timespec="seconds"),
        "updated_at": datetime.fromtimestamp(record.updated_at).astimezone().isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
