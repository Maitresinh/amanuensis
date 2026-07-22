"""Ports implemented by metadata, acquisition, storage, and library adapters."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .domain import StagedItem
from .search import Passage, PassageQuery, SearchHit, SourceUnit


class MetadataProvider(Protocol):
    name: str

    def search(self, query: str) -> Iterable[StagedItem]: ...


class AcquisitionProvider(Protocol):
    name: str

    def acquire(self, item: StagedItem, destination_role: str) -> StagedItem: ...


class LibraryAdapter(Protocol):
    name: str

    def find_matches(self, item: StagedItem) -> Iterable[str]: ...

    def import_item(self, item: StagedItem) -> str: ...


class SourceTextStore(Protocol):
    def units_for_books(self, book_ids: frozenset[str]) -> Iterable[SourceUnit]: ...


class PassageIndex(Protocol):
    def index(self, passages: Iterable[Passage]) -> None: ...

    def search(self, query: PassageQuery) -> Iterable[SearchHit]: ...
