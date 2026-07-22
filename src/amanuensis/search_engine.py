"""Application service for indexing files and retrieving verbatim excerpts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .extraction import ExtractionStatus, extract_text
from .indexing import segment_units
from .ports import PassageIndex
from .search import AssembledExcerpt, PassageQuery, assemble_passages
from .search_store import SQLiteSearchStore, StoredBook


@dataclass(frozen=True, slots=True)
class IndexReport:
    book_id: str
    status: ExtractionStatus
    units: int
    passages: int
    message: str = ""


class PassageSearchEngine:
    def __init__(self, store: SQLiteSearchStore, index: PassageIndex) -> None:
        self.store = store
        self.index = index

    def index_file(
        self,
        book_id: str,
        path: Path | str,
        *,
        title: str | None = None,
        corpus_ids: frozenset[str] = frozenset(),
    ) -> IndexReport:
        result = extract_text(book_id, path)
        documents = segment_units(result.units, corpus_ids=corpus_ids) if result.units else []
        self.index.delete_books(frozenset({book_id}))
        if documents:
            self.index.index(documents)
        self.store.replace_book(
            result,
            documents,
            title=title,
            corpus_ids=corpus_ids,
        )
        return IndexReport(
            book_id=book_id,
            status=result.status,
            units=len(result.units),
            passages=len(documents),
            message=result.message,
        )

    def search(self, query: PassageQuery) -> list[AssembledExcerpt]:
        hits = list(self.index.search(query))
        units = self.store.units_for_books(query.scope.book_ids)
        source_map = {(unit.book_id, unit.unit_id): unit for unit in units}
        return assemble_passages(query, hits, source_map)

    def books(self, *, corpus_id: str | None = None) -> list[StoredBook]:
        return self.store.books(corpus_id=corpus_id)

    def corpus_ids(self) -> list[str]:
        return self.store.corpus_ids()
