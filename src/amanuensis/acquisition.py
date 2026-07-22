"""Provider-neutral contracts for catalogue search and acquisition."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum
import re
import unicodedata
from typing import Any, Iterable


class SearchSort(StrEnum):
    RELEVANT = "relevant"
    NEWEST = "newest"
    OLDEST = "oldest"
    LARGEST = "largest"
    SMALLEST = "smallest"
    NEWEST_ADDED = "newest_added"
    OLDEST_ADDED = "oldest_added"
    RANDOM = "random"


class ProviderError(RuntimeError):
    """A provider operation failed permanently or returned invalid data."""


class RetryableProviderError(ProviderError):
    """A provider operation can reasonably be retried later."""


class RemoteState(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DELAYED = "delayed"
    AVAILABLE = "available"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RemoteDownload:
    identifier: str
    state: RemoteState
    progress: float = 0.0
    error: str | None = None
    next_retry_at: float | None = None
    filename: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CatalogueQuery:
    text: str = ""
    page: int = 1
    sort: SearchSort = SearchSort.RELEVANT
    descending: bool = False
    content_types: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    author: str | None = None
    title: str | None = None

    def __post_init__(self) -> None:
        if not any((self.text.strip(), self.author, self.title)):
            raise ValueError("a catalogue query needs text, an author, or a title")
        if self.page < 1:
            raise ValueError("page must be positive")


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    identifier: str
    title: str
    authors: tuple[str, ...] = ()
    publisher: str | None = None
    description: str | None = None
    cover_url: str | None = None
    filename: str | None = None
    language: str | None = None
    format: str | None = None
    size: str | None = None
    year: str | None = None
    content_type: str | None = None
    source: str | None = None
    download_status: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        identifier = self.identifier.strip().lower()
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise ValueError("candidate identifier must be a 32-character MD5")
        if not self.title.strip():
            raise ValueError("candidate title must not be empty")
        object.__setattr__(self, "identifier", identifier)


@dataclass(frozen=True, slots=True)
class SearchPage:
    items: tuple[SearchCandidate, ...]
    page: int = 1
    total: int | None = None
    total_pages: int | None = None


@dataclass(frozen=True, slots=True)
class CandidateIntent:
    title: str
    authors: tuple[str, ...] = ()
    preferred_languages: tuple[str, ...] = ("fr",)
    preferred_formats: tuple[str, ...] = ("epub", "pdf")
    allowed_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("candidate intent title must not be empty")


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    candidate: SearchCandidate
    score: float
    evidence: tuple[str, ...]
    rejected: bool = False


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    selected: SearchCandidate | None
    assessments: tuple[CandidateAssessment, ...]
    reason: str


def _normalise(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    words = "".join(char if char.isalnum() else " " for char in without_marks.casefold())
    return " ".join(words.split())


def _similarity(left: str | None, right: str | None) -> float:
    a = _normalise(left)
    b = _normalise(right)
    if not a or not b:
        return 0.0
    sequence = SequenceMatcher(None, a, b).ratio()
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    token_overlap = len(a_tokens & b_tokens) / max(len(a_tokens | b_tokens), 1)
    return max(sequence, token_overlap)


def assess_candidate(intent: CandidateIntent, candidate: SearchCandidate) -> CandidateAssessment:
    """Score a result using deterministic, inspectable bibliographic signals."""

    evidence: list[str] = []
    rejected = False
    title_similarity = _similarity(intent.title, candidate.title)
    score = title_similarity * 60
    evidence.append(f"title_similarity={title_similarity:.3f}")

    if intent.authors:
        author_similarity = max(
            (_similarity(expected, actual) for expected in intent.authors for actual in candidate.authors),
            default=0.0,
        )
        score += author_similarity * 20
        evidence.append(f"author_similarity={author_similarity:.3f}")
        if author_similarity < 0.35:
            score -= 15
            evidence.append("author_mismatch=-15")

    language = _normalise(candidate.language)
    preferred_languages = {_normalise(item) for item in intent.preferred_languages}
    if language and preferred_languages:
        if language in preferred_languages:
            score += 10
            evidence.append("preferred_language=+10")
        else:
            score -= 12
            evidence.append("language_mismatch=-12")

    candidate_format = _normalise(candidate.format)
    preferred_formats = [_normalise(item) for item in intent.preferred_formats]
    if candidate_format and preferred_formats:
        if candidate_format in preferred_formats:
            rank = preferred_formats.index(candidate_format)
            bonus = max(3, 10 - rank * 3)
            score += bonus
            evidence.append(f"preferred_format=+{bonus}")
        else:
            score -= 8
            evidence.append("format_mismatch=-8")

    if intent.allowed_sources:
        allowed = {_normalise(item) for item in intent.allowed_sources}
        if _normalise(candidate.source) not in allowed:
            rejected = True
            evidence.append("source_not_allowed")
        else:
            score += 5
            evidence.append("allowed_source=+5")

    return CandidateAssessment(
        candidate=candidate,
        score=round(max(0.0, min(100.0, score)), 2),
        evidence=tuple(evidence),
        rejected=rejected,
    )


def select_candidate(
    intent: CandidateIntent,
    candidates: Iterable[SearchCandidate],
    *,
    minimum_score: float = 58.0,
    ambiguity_margin: float = 4.0,
) -> CandidateSelection:
    """Select a credible result, refusing weak or bibliographically ambiguous matches."""

    assessments = [assess_candidate(intent, candidate) for candidate in candidates]
    assessments.sort(key=lambda item: (-item.score, item.candidate.identifier))
    viable = [item for item in assessments if not item.rejected]
    if not viable:
        return CandidateSelection(None, tuple(assessments), "no allowed candidate")

    best = viable[0]
    if best.score < minimum_score:
        return CandidateSelection(None, tuple(assessments), "best candidate is below threshold")

    if len(viable) > 1 and best.score - viable[1].score < ambiguity_margin:
        first_identity = (_normalise(best.candidate.title), tuple(map(_normalise, best.candidate.authors)))
        second_identity = (
            _normalise(viable[1].candidate.title),
            tuple(map(_normalise, viable[1].candidate.authors)),
        )
        if first_identity != second_identity:
            return CandidateSelection(None, tuple(assessments), "top candidates are ambiguous")

    return CandidateSelection(best.candidate, tuple(assessments), "selected by deterministic score")
