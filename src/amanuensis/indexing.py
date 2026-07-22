"""Passage segmentation with stable identifiers and exact source offsets."""

from __future__ import annotations

from hashlib import sha256
import re
from typing import Iterable

from .search import IndexDocument, Passage, SourceUnit


def segment_units(
    units: Iterable[SourceUnit],
    *,
    corpus_ids: frozenset[str] = frozenset(),
    target_chars: int = 1_200,
    overlap_chars: int = 200,
) -> list[IndexDocument]:
    if target_chars < 100:
        raise ValueError("target_chars must be at least 100")
    if not 0 <= overlap_chars < target_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than target_chars")

    documents: list[IndexDocument] = []
    for unit in units:
        start = _next_non_space(unit.text, 0)
        ordinal = 0
        while start < len(unit.text):
            end = _choose_end(unit.text, start, target_chars)
            if end <= start:
                break
            ordinal += 1
            raw_id = f"{unit.book_id}\0{unit.unit_id}\0{start}\0{end}\0{unit.text[start:end]}"
            passage = Passage(
                passage_id=_uuid_text(sha256(raw_id.encode("utf-8")).hexdigest()),
                book_id=unit.book_id,
                unit_id=unit.unit_id,
                ordinal=ordinal,
                start=start,
                end=end,
            )
            documents.append(
                IndexDocument(
                    passage=passage,
                    text=unit.text[start:end],
                    corpus_ids=corpus_ids,
                )
            )
            if end >= len(unit.text):
                break
            next_start = max(start + 1, end - overlap_chars)
            start = _next_word_start(unit.text, next_start)
    return documents


def _choose_end(text: str, start: int, target_chars: int) -> int:
    hard_end = min(len(text), start + target_chars)
    if hard_end == len(text):
        return len(text)
    soft_start = start + max(1, int(target_chars * 0.6))
    window = text[soft_start:hard_end]
    candidates: list[int] = []
    for pattern in (r"\n\n", r"(?<=[.!?])\s", r"\n", r"\s"):
        matches = list(re.finditer(pattern, window))
        if matches:
            candidates.append(soft_start + matches[-1].end())
            break
    return max(start + 1, candidates[0] if candidates else hard_end)


def _next_word_start(text: str, position: int) -> int:
    if position >= len(text):
        return len(text)
    if position == 0 or text[position - 1].isspace():
        return _next_non_space(text, position)
    match = re.search(r"\s+", text[position:])
    if not match:
        return len(text)
    return _next_non_space(text, position + match.end())


def _next_non_space(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def _uuid_text(hex_digest: str) -> str:
    value = hex_digest[:32]
    return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:]}"
