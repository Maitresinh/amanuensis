"""Passage retrieval contracts and deterministic excerpt assembly."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping


class ResultOrder(StrEnum):
    RELEVANCE = "relevance"
    READING = "reading"


@dataclass(frozen=True, slots=True)
class SearchScope:
    """A resolved, explicit set of books selected by the user."""

    book_ids: frozenset[str]
    corpus_id: str | None = None

    def __post_init__(self) -> None:
        cleaned = frozenset(item.strip() for item in self.book_ids if item.strip())
        if not cleaned:
            raise ValueError("search scope must contain at least one selected book")
        object.__setattr__(self, "book_ids", cleaned)


@dataclass(frozen=True, slots=True)
class PassageQuery:
    text: str
    scope: SearchScope
    limit: int = 20
    order: ResultOrder = ResultOrder.RELEVANCE

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("search query must not be empty")
        if not 1 <= self.limit <= 200:
            raise ValueError("search limit must be between 1 and 200")


@dataclass(frozen=True, slots=True)
class SourceUnit:
    """Addressable source text, normally a chapter, page, or document section."""

    book_id: str
    unit_id: str
    order: int
    label: str
    text: str


@dataclass(frozen=True, slots=True)
class Passage:
    """An indexed window whose offsets refer to one immutable source unit."""

    passage_id: str
    book_id: str
    unit_id: str
    ordinal: int
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("passage offsets must describe a non-empty source span")


@dataclass(frozen=True, slots=True)
class IndexDocument:
    """Text and payload indexed for one exact passage."""

    passage: Passage
    text: str
    corpus_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("indexed passage text must not be empty")
        if len(self.text) != self.passage.end - self.passage.start:
            raise ValueError("indexed text length must match passage offsets")


@dataclass(frozen=True, slots=True)
class SearchHit:
    passage: Passage
    score: float
    channels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AssembledExcerpt:
    """One verbatim source span supported by one or more retrieval hits."""

    book_id: str
    unit_id: str
    unit_label: str
    unit_order: int
    start: int
    end: int
    text: str
    score: float
    passage_ids: tuple[str, ...]
    channels: tuple[str, ...]


@dataclass(slots=True)
class _ExcerptBuilder:
    unit: SourceUnit
    start: int
    end: int
    score: float
    passage_ids: list[str]
    channels: set[str]


def assemble_passages(
    query: PassageQuery,
    hits: Iterable[SearchHit],
    source_units: Mapping[tuple[str, str], SourceUnit],
    *,
    merge_gap_chars: int = 240,
) -> list[AssembledExcerpt]:
    """Merge nearby hits and return exact source slices.

    This function performs no generation, summarization, translation, or text
    cleanup. A backend result outside the selected scope is rejected instead of
    being silently exposed.
    """

    if merge_gap_chars < 0:
        raise ValueError("merge_gap_chars must not be negative")

    checked: list[tuple[SearchHit, SourceUnit]] = []
    for hit in hits:
        passage = hit.passage
        if passage.book_id not in query.scope.book_ids:
            raise ValueError(
                f"search backend returned out-of-scope book {passage.book_id!r}"
            )
        key = (passage.book_id, passage.unit_id)
        try:
            unit = source_units[key]
        except KeyError as exc:
            raise ValueError(f"source unit is missing for passage {passage.passage_id!r}") from exc
        if unit.book_id != passage.book_id or unit.unit_id != passage.unit_id:
            raise ValueError(f"source unit identity mismatch for {passage.passage_id!r}")
        if passage.end > len(unit.text):
            raise ValueError(f"passage {passage.passage_id!r} exceeds source text")
        checked.append((hit, unit))

    checked.sort(
        key=lambda item: (
            item[1].book_id,
            item[1].order,
            item[0].passage.start,
            item[0].passage.end,
        )
    )

    builders: list[_ExcerptBuilder] = []
    for hit, unit in checked:
        passage = hit.passage
        previous = builders[-1] if builders else None
        if (
            previous is not None
            and previous.unit.book_id == unit.book_id
            and previous.unit.unit_id == unit.unit_id
            and passage.start <= previous.end + merge_gap_chars
        ):
            previous.end = max(previous.end, passage.end)
            previous.score = max(previous.score, hit.score)
            previous.passage_ids.append(passage.passage_id)
            previous.channels.update(hit.channels)
            continue
        builders.append(
            _ExcerptBuilder(
                unit=unit,
                start=passage.start,
                end=passage.end,
                score=hit.score,
                passage_ids=[passage.passage_id],
                channels=set(hit.channels),
            )
        )

    excerpts = [
        AssembledExcerpt(
            book_id=item.unit.book_id,
            unit_id=item.unit.unit_id,
            unit_label=item.unit.label,
            unit_order=item.unit.order,
            start=item.start,
            end=item.end,
            text=item.unit.text[item.start : item.end],
            score=item.score,
            passage_ids=tuple(item.passage_ids),
            channels=tuple(sorted(item.channels)),
        )
        for item in builders
    ]

    if query.order == ResultOrder.RELEVANCE:
        excerpts.sort(
            key=lambda item: (-item.score, item.book_id, item.unit_order, item.start)
        )
    else:
        excerpts.sort(key=lambda item: (item.book_id, item.unit_order, item.start))
    return excerpts[: query.limit]
