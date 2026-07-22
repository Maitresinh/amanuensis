"""Deployment-independent entities for the Amanuensis staging workflow."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class MediaKind(StrEnum):
    BOOK = "book"
    COMIC = "comic"
    PERIODICAL_ISSUE = "periodical_issue"
    ANTHOLOGY = "anthology"
    RPG_PUBLICATION = "rpg_publication"
    OTHER = "other"


class StageState(StrEnum):
    QUEUED = "queued"
    ACQUIRING = "acquiring"
    ACQUIRED = "acquired"
    IDENTIFYING = "identifying"
    REVIEW_REQUIRED = "review_required"
    READY_TO_IMPORT = "ready_to_import"
    IMPORTING = "importing"
    IMPORTED = "imported"
    QUARANTINED = "quarantined"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"


ALLOWED_TRANSITIONS: dict[StageState, frozenset[StageState]] = {
    StageState.QUEUED: frozenset({StageState.ACQUIRING, StageState.FAILED_FINAL}),
    StageState.ACQUIRING: frozenset(
        {StageState.ACQUIRED, StageState.FAILED_RETRYABLE, StageState.FAILED_FINAL}
    ),
    StageState.ACQUIRED: frozenset({StageState.IDENTIFYING, StageState.QUARANTINED}),
    StageState.IDENTIFYING: frozenset(
        {
            StageState.REVIEW_REQUIRED,
            StageState.READY_TO_IMPORT,
            StageState.QUARANTINED,
            StageState.FAILED_RETRYABLE,
        }
    ),
    StageState.REVIEW_REQUIRED: frozenset(
        {StageState.READY_TO_IMPORT, StageState.QUARANTINED, StageState.FAILED_FINAL}
    ),
    StageState.READY_TO_IMPORT: frozenset(
        {StageState.IMPORTING, StageState.REVIEW_REQUIRED, StageState.QUARANTINED}
    ),
    StageState.IMPORTING: frozenset(
        {StageState.IMPORTED, StageState.FAILED_RETRYABLE, StageState.REVIEW_REQUIRED}
    ),
    StageState.FAILED_RETRYABLE: frozenset({StageState.QUEUED, StageState.FAILED_FINAL}),
    StageState.QUARANTINED: frozenset(
        {StageState.REVIEW_REQUIRED, StageState.FAILED_FINAL}
    ),
    StageState.IMPORTED: frozenset(),
    StageState.FAILED_FINAL: frozenset(),
}


class TransitionError(ValueError):
    """Raised when a workflow state change violates the domain contract."""


@dataclass(frozen=True, slots=True)
class Evidence:
    source: str
    claim: str
    confidence: float
    locator: str | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class StagedItem:
    request_id: str
    title: str
    kind: MediaKind
    state: StageState = StageState.QUEUED
    contributors: tuple[str, ...] = ()
    series: str | None = None
    issue: str | None = None
    identifiers: dict[str, str] = field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)

    def transition(self, target: StageState) -> "StagedItem":
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise TransitionError(f"cannot transition from {self.state} to {target}")
        return replace(self, state=target)

    def with_evidence(self, item: Evidence) -> "StagedItem":
        return replace(self, evidence=(*self.evidence, item))
