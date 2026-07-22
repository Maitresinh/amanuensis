"""Durable acquisition queue owned by Amanuensis."""

from __future__ import annotations

from dataclasses import dataclass, replace
from contextlib import closing
from enum import StrEnum
import json
from pathlib import Path
import sqlite3
import time
from typing import Any
from uuid import uuid4

from .acquisition import (
    CandidateIntent,
    CatalogueQuery,
    SearchCandidate,
    SearchSort,
)


class AcquisitionState(StrEnum):
    WANTED = "wanted"
    SEARCHING = "searching"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DELAYED = "delayed"
    AVAILABLE = "available"
    STAGING = "staging"
    STAGED = "staged"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"
    CANCELLED = "cancelled"


ACTIVE_STATES = (
    AcquisitionState.WANTED,
    AcquisitionState.SEARCHING,
    AcquisitionState.FAILED_RETRYABLE,
    AcquisitionState.QUEUED,
    AcquisitionState.DOWNLOADING,
    AcquisitionState.DELAYED,
    AcquisitionState.AVAILABLE,
    AcquisitionState.STAGING,
)


@dataclass(frozen=True, slots=True)
class AcquisitionRecord:
    identifier: str
    query: CatalogueQuery
    intent: CandidateIntent
    state: AcquisitionState
    candidate: SearchCandidate | None = None
    remote_id: str | None = None
    attempts: int = 0
    next_attempt_at: float | None = None
    queued_sequence: int = 0
    staged_path: str | None = None
    last_error: str | None = None
    created_at: float = 0
    updated_at: float = 0


class SQLiteAcquisitionQueue:
    """Small durable queue with explicit retry ordering and event history."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialise(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS acquisition_requests (
                    id TEXT PRIMARY KEY,
                    query_json TEXT NOT NULL,
                    intent_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    candidate_json TEXT,
                    remote_id TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL,
                    queued_sequence INTEGER NOT NULL,
                    staged_path TEXT,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS acquisition_due_idx
                    ON acquisition_requests(state, next_attempt_at, queued_sequence);
                CREATE TABLE IF NOT EXISTS acquisition_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    state TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES acquisition_requests(id)
                );
                """
            )

    def create(self, query: CatalogueQuery, intent: CandidateIntent) -> AcquisitionRecord:
        now = time.time()
        with closing(self._connect()) as connection, connection:
            sequence = self._next_sequence(connection)
            record = AcquisitionRecord(
                identifier=uuid4().hex,
                query=query,
                intent=intent,
                state=AcquisitionState.WANTED,
                queued_sequence=sequence,
                created_at=now,
                updated_at=now,
            )
            self._insert(connection, record)
            self._append_event(connection, record, "request_created", {})
        return record

    def get(self, identifier: str) -> AcquisitionRecord | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM acquisition_requests WHERE id=?", (identifier,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self, *, state: AcquisitionState | None = None) -> list[AcquisitionRecord]:
        sql = "SELECT * FROM acquisition_requests"
        params: tuple[Any, ...] = ()
        if state is not None:
            sql += " WHERE state=?"
            params = (state.value,)
        sql += " ORDER BY queued_sequence, created_at"
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._from_row(row) for row in rows]

    def next_due(self, *, now: float | None = None) -> AcquisitionRecord | None:
        now = time.time() if now is None else now
        placeholders = ",".join("?" for _ in ACTIVE_STATES)
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                f"""
                SELECT * FROM acquisition_requests
                WHERE state IN ({placeholders})
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY queued_sequence, created_at
                LIMIT 1
                """,
                (*[state.value for state in ACTIVE_STATES], now),
            ).fetchone()
        return self._from_row(row) if row else None

    def save(
        self,
        record: AcquisitionRecord,
        *,
        event: str,
        detail: dict[str, Any] | None = None,
        move_to_tail: bool = False,
    ) -> AcquisitionRecord:
        updated = replace(record, updated_at=time.time())
        with closing(self._connect()) as connection, connection:
            if move_to_tail:
                updated = replace(updated, queued_sequence=self._next_sequence(connection))
            connection.execute(
                """
                UPDATE acquisition_requests SET
                    query_json=?, intent_json=?, state=?, candidate_json=?, remote_id=?,
                    attempts=?, next_attempt_at=?, queued_sequence=?, staged_path=?,
                    last_error=?, updated_at=?
                WHERE id=?
                """,
                (
                    _dump_query(updated.query),
                    _dump_intent(updated.intent),
                    updated.state.value,
                    _dump_candidate(updated.candidate) if updated.candidate else None,
                    updated.remote_id,
                    updated.attempts,
                    updated.next_attempt_at,
                    updated.queued_sequence,
                    updated.staged_path,
                    updated.last_error,
                    updated.updated_at,
                    updated.identifier,
                ),
            )
            if connection.total_changes != 1:
                raise KeyError(f"unknown acquisition request {record.identifier}")
            self._append_event(connection, updated, event, detail or {})
        return updated

    def events(self, identifier: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT event, state, detail_json, created_at
                FROM acquisition_events WHERE request_id=? ORDER BY id
                """,
                (identifier,),
            ).fetchall()
        return [
            {
                "event": row["event"],
                "state": row["state"],
                "detail": json.loads(row["detail_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _next_sequence(connection: sqlite3.Connection) -> int:
        value = connection.execute(
            "SELECT COALESCE(MAX(queued_sequence), 0) + 1 FROM acquisition_requests"
        ).fetchone()[0]
        return int(value)

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        record: AcquisitionRecord,
        event: str,
        detail: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO acquisition_events(request_id, event, state, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.identifier,
                event,
                record.state.value,
                json.dumps(detail, ensure_ascii=True, default=str, sort_keys=True),
                time.time(),
            ),
        )

    @staticmethod
    def _insert(connection: sqlite3.Connection, record: AcquisitionRecord) -> None:
        connection.execute(
            """
            INSERT INTO acquisition_requests(
                id, query_json, intent_json, state, candidate_json, remote_id,
                attempts, next_attempt_at, queued_sequence, staged_path,
                last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.identifier,
                _dump_query(record.query),
                _dump_intent(record.intent),
                record.state.value,
                None,
                None,
                record.attempts,
                record.next_attempt_at,
                record.queued_sequence,
                None,
                None,
                record.created_at,
                record.updated_at,
            ),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AcquisitionRecord:
        return AcquisitionRecord(
            identifier=row["id"],
            query=_load_query(row["query_json"]),
            intent=_load_intent(row["intent_json"]),
            state=AcquisitionState(row["state"]),
            candidate=_load_candidate(row["candidate_json"]) if row["candidate_json"] else None,
            remote_id=row["remote_id"],
            attempts=row["attempts"],
            next_attempt_at=row["next_attempt_at"],
            queued_sequence=row["queued_sequence"],
            staged_path=row["staged_path"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _dump_query(query: CatalogueQuery) -> str:
    return json.dumps(
        {
            "text": query.text,
            "page": query.page,
            "sort": query.sort.value,
            "descending": query.descending,
            "content_types": query.content_types,
            "formats": query.formats,
            "languages": query.languages,
            "sources": query.sources,
            "author": query.author,
            "title": query.title,
        },
        sort_keys=True,
    )


def _load_query(value: str) -> CatalogueQuery:
    data = json.loads(value)
    data["sort"] = SearchSort(data["sort"])
    for key in ("content_types", "formats", "languages", "sources"):
        data[key] = tuple(data.get(key) or ())
    return CatalogueQuery(**data)


def _dump_intent(intent: CandidateIntent) -> str:
    return json.dumps(
        {
            "title": intent.title,
            "authors": intent.authors,
            "preferred_languages": intent.preferred_languages,
            "preferred_formats": intent.preferred_formats,
            "allowed_sources": intent.allowed_sources,
        },
        sort_keys=True,
    )


def _load_intent(value: str) -> CandidateIntent:
    data = json.loads(value)
    for key in ("authors", "preferred_languages", "preferred_formats", "allowed_sources"):
        data[key] = tuple(data.get(key) or ())
    return CandidateIntent(**data)


def _dump_candidate(candidate: SearchCandidate) -> str:
    return json.dumps(
        {
            "identifier": candidate.identifier,
            "title": candidate.title,
            "authors": candidate.authors,
            "publisher": candidate.publisher,
            "description": candidate.description,
            "cover_url": candidate.cover_url,
            "filename": candidate.filename,
            "language": candidate.language,
            "format": candidate.format,
            "size": candidate.size,
            "year": candidate.year,
            "content_type": candidate.content_type,
            "source": candidate.source,
            "download_status": candidate.download_status,
            "attributes": candidate.attributes,
        },
        ensure_ascii=True,
        default=str,
        sort_keys=True,
    )


def _load_candidate(value: str) -> SearchCandidate:
    data = json.loads(value)
    data["authors"] = tuple(data.get("authors") or ())
    return SearchCandidate(**data)
