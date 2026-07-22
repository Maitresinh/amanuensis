"""SQLite storage for immutable source text and passage provenance."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
from typing import Iterable

from .extraction import ExtractionResult
from .search import IndexDocument, Passage, SearchScope, SourceUnit


@dataclass(frozen=True, slots=True)
class StoredBook:
    book_id: str
    title: str
    source_path: str
    format: str
    status: str
    message: str
    unit_count: int
    corpus_ids: tuple[str, ...]
    indexed_at: float


class SQLiteSearchStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def replace_book(
        self,
        result: ExtractionResult,
        passages: Iterable[IndexDocument],
        *,
        title: str | None = None,
        corpus_ids: frozenset[str] = frozenset(),
    ) -> None:
        documents = list(passages)
        with self._connection() as connection:
            connection.execute("DELETE FROM corpus_books WHERE book_id = ?", (result.book_id,))
            connection.execute("DELETE FROM source_units WHERE book_id = ?", (result.book_id,))
            connection.execute(
                """
                INSERT INTO books (
                    book_id, title, source_path, format, status, message, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id) DO UPDATE SET
                    title = excluded.title,
                    source_path = excluded.source_path,
                    format = excluded.format,
                    status = excluded.status,
                    message = excluded.message,
                    indexed_at = excluded.indexed_at
                """,
                (
                    result.book_id,
                    title or result.path.stem,
                    str(result.path),
                    result.format,
                    result.status.value,
                    result.message,
                    time.time(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO source_units (book_id, unit_id, unit_order, label, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (unit.book_id, unit.unit_id, unit.order, unit.label, unit.text)
                    for unit in result.units
                ],
            )
            connection.executemany(
                """
                INSERT INTO passages (
                    passage_id, book_id, unit_id, ordinal, start_offset, end_offset
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.passage.passage_id,
                        item.passage.book_id,
                        item.passage.unit_id,
                        item.passage.ordinal,
                        item.passage.start,
                        item.passage.end,
                    )
                    for item in documents
                ],
            )
            connection.executemany(
                "INSERT INTO corpus_books (corpus_id, book_id) VALUES (?, ?)",
                [(corpus_id, result.book_id) for corpus_id in sorted(corpus_ids)],
            )

    def units_for_books(self, book_ids: frozenset[str]) -> list[SourceUnit]:
        if not book_ids:
            return []
        placeholders = ",".join("?" for _ in book_ids)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT book_id, unit_id, unit_order, label, text
                FROM source_units
                WHERE book_id IN ({placeholders})
                ORDER BY book_id, unit_order
                """,
                tuple(sorted(book_ids)),
            ).fetchall()
        return [SourceUnit(row[0], row[1], row[2], row[3], row[4]) for row in rows]

    def passages_for_books(self, book_ids: frozenset[str]) -> list[Passage]:
        if not book_ids:
            return []
        placeholders = ",".join("?" for _ in book_ids)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT passage_id, book_id, unit_id, ordinal, start_offset, end_offset
                FROM passages
                WHERE book_id IN ({placeholders})
                ORDER BY book_id, unit_id, ordinal
                """,
                tuple(sorted(book_ids)),
            ).fetchall()
        return [Passage(*row) for row in rows]

    def books(self, *, corpus_id: str | None = None) -> list[StoredBook]:
        parameters: tuple[object, ...] = ()
        where = ""
        if corpus_id:
            where = "WHERE EXISTS (SELECT 1 FROM corpus_books cb WHERE cb.book_id = b.book_id AND cb.corpus_id = ?)"
            parameters = (corpus_id,)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT b.book_id, b.title, b.source_path, b.format, b.status, b.message,
                       COUNT(DISTINCT u.unit_id), b.indexed_at
                FROM books b
                LEFT JOIN source_units u ON u.book_id = b.book_id
                {where}
                GROUP BY b.book_id
                ORDER BY b.title COLLATE NOCASE, b.book_id
                """,
                parameters,
            ).fetchall()
            corpus_rows = connection.execute(
                "SELECT book_id, corpus_id FROM corpus_books ORDER BY corpus_id"
            ).fetchall()
        memberships: dict[str, list[str]] = {}
        for book_id, member_corpus_id in corpus_rows:
            memberships.setdefault(book_id, []).append(member_corpus_id)
        return [
            StoredBook(
                book_id=row[0],
                title=row[1],
                source_path=row[2],
                format=row[3],
                status=row[4],
                message=row[5],
                unit_count=row[6],
                corpus_ids=tuple(memberships.get(row[0], ())),
                indexed_at=row[7],
            )
            for row in rows
        ]

    def corpus_ids(self) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT corpus_id FROM corpus_books ORDER BY corpus_id COLLATE NOCASE"
            ).fetchall()
        return [row[0] for row in rows]

    def resolve_scope(
        self,
        *,
        book_ids: Iterable[str] = (),
        corpus_id: str | None = None,
    ) -> SearchScope:
        selected = {item.strip() for item in book_ids if item.strip()}
        with self._connection() as connection:
            if corpus_id:
                rows = connection.execute(
                    "SELECT book_id FROM corpus_books WHERE corpus_id = ?",
                    (corpus_id,),
                ).fetchall()
                corpus_books = {row[0] for row in rows}
                selected = selected & corpus_books if selected else corpus_books
            if selected:
                placeholders = ",".join("?" for _ in selected)
                existing = {
                    row[0]
                    for row in connection.execute(
                        f"SELECT book_id FROM books WHERE book_id IN ({placeholders})",
                        tuple(sorted(selected)),
                    ).fetchall()
                }
                selected &= existing
        return SearchScope(frozenset(selected), corpus_id=corpus_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS books (
                    book_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    format TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    indexed_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_units (
                    book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
                    unit_id TEXT NOT NULL,
                    unit_order INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    text TEXT NOT NULL,
                    PRIMARY KEY (book_id, unit_id)
                );
                CREATE TABLE IF NOT EXISTS passages (
                    passage_id TEXT PRIMARY KEY,
                    book_id TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    FOREIGN KEY (book_id, unit_id)
                        REFERENCES source_units(book_id, unit_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS corpus_books (
                    corpus_id TEXT NOT NULL,
                    book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
                    PRIMARY KEY (corpus_id, book_id)
                );
                CREATE INDEX IF NOT EXISTS idx_passages_book ON passages(book_id);
                CREATE INDEX IF NOT EXISTS idx_corpus_books_book ON corpus_books(book_id);
                """
            )
