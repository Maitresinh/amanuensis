"""Application service for search, queueing, retry, and isolated staging."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import time
from typing import Protocol

from .acquisition import (
    CandidateIntent,
    CatalogueQuery,
    ProviderError,
    RemoteDownload,
    RemoteState,
    RetryableProviderError,
    SearchCandidate,
    SearchPage,
    select_candidate,
)
from .queue import AcquisitionRecord, AcquisitionState, SQLiteAcquisitionQueue


class CatalogueAdapter(Protocol):
    def search(self, query: CatalogueQuery) -> SearchPage: ...


class DownloadAdapter(Protocol):

    def queue(self, candidate: SearchCandidate) -> RemoteDownload: ...

    def status(self, identifier: str) -> RemoteDownload: ...

    def retry(self, identifier: str) -> RemoteDownload: ...

    def cancel(self, identifier: str) -> RemoteDownload: ...

    def retrieve(self, candidate: SearchCandidate, destination: Path) -> Path: ...


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    maximum_attempts: int = 12
    base_delay_seconds: float = 300
    maximum_delay_seconds: float = 6 * 60 * 60

    def delay(self, attempts: int) -> float:
        return min(self.maximum_delay_seconds, self.base_delay_seconds * (2 ** max(0, attempts - 1)))


class AcquisitionCoordinator:
    def __init__(
        self,
        repository: SQLiteAcquisitionQueue,
        catalogue_adapter: CatalogueAdapter,
        staging_directory: Path | str,
        *,
        download_adapter: DownloadAdapter | None = None,
        retry_policy: RetryPolicy | None = None,
        poll_interval_seconds: float = 15,
        clock=time.time,
    ) -> None:
        self.repository = repository
        self.catalogue_adapter = catalogue_adapter
        self.download_adapter = download_adapter or catalogue_adapter
        self.staging_directory = Path(staging_directory)
        self.retry_policy = retry_policy or RetryPolicy()
        self.poll_interval_seconds = poll_interval_seconds
        self.clock = clock

    def submit(self, query: CatalogueQuery, intent: CandidateIntent) -> AcquisitionRecord:
        return self.repository.create(query, intent)

    def cancel_request(self, identifier: str) -> AcquisitionRecord:
        record = self.repository.get(identifier)
        if record is None:
            raise KeyError(f"unknown acquisition request {identifier}")
        if record.remote_id and record.state not in {
            AcquisitionState.STAGED,
            AcquisitionState.FAILED_FINAL,
            AcquisitionState.CANCELLED,
        }:
            self.download_adapter.cancel(record.remote_id)
        return self.repository.save(
            replace(record, state=AcquisitionState.CANCELLED, next_attempt_at=None),
            event="request_cancelled",
        )

    def retry_request(self, identifier: str) -> AcquisitionRecord:
        record = self.repository.get(identifier)
        if record is None:
            raise KeyError(f"unknown acquisition request {identifier}")
        if record.state not in {
            AcquisitionState.FAILED_RETRYABLE,
            AcquisitionState.FAILED_FINAL,
            AcquisitionState.CANCELLED,
        }:
            raise ValueError(f"request cannot be retried from {record.state.value}")
        return self.repository.save(
            replace(
                record,
                state=AcquisitionState.FAILED_RETRYABLE,
                attempts=0,
                next_attempt_at=self.clock(),
                last_error=None,
            ),
            event="manual_retry_requested",
            move_to_tail=True,
        )

    def process_next(self) -> AcquisitionRecord | None:
        record = self.repository.next_due(now=self.clock())
        if record is None:
            return None
        try:
            if record.state in {AcquisitionState.WANTED, AcquisitionState.SEARCHING}:
                return self._search_and_queue(record)
            if record.state == AcquisitionState.FAILED_RETRYABLE:
                if record.candidate and record.remote_id:
                    return self._retry_remote(record)
                return self._search_and_queue(record)
            if record.state in {
                AcquisitionState.QUEUED,
                AcquisitionState.DOWNLOADING,
                AcquisitionState.DELAYED,
            }:
                return self._synchronise(record)
            if record.state == AcquisitionState.AVAILABLE:
                return self._stage(record)
            if record.state == AcquisitionState.STAGING:
                return self._stage(record)
            return record
        except RetryableProviderError as exc:
            return self._reschedule(record, str(exc))
        except ProviderError as exc:
            return self._fail(record, str(exc))
        except OSError as exc:
            return self._reschedule(record, f"staging I/O failed: {exc}")

    def run_due(self, *, maximum_steps: int = 100) -> list[AcquisitionRecord]:
        processed: list[AcquisitionRecord] = []
        for _ in range(maximum_steps):
            record = self.process_next()
            if record is None:
                break
            processed.append(record)
        return processed

    def _search_and_queue(self, record: AcquisitionRecord) -> AcquisitionRecord:
        searching = self.repository.save(
            replace(record, state=AcquisitionState.SEARCHING, last_error=None),
            event="search_started",
        )
        page = self.catalogue_adapter.search(searching.query)
        selection = select_candidate(searching.intent, page.items)
        detail = {
            "result_count": len(page.items),
            "selection_reason": selection.reason,
            "top": [
                {
                    "identifier": item.candidate.identifier,
                    "title": item.candidate.title,
                    "authors": item.candidate.authors,
                    "score": item.score,
                    "evidence": item.evidence,
                }
                for item in selection.assessments[:5]
            ],
        }
        if selection.selected is None:
            return self._reschedule(searching, f"candidate selection failed: {selection.reason}", detail)
        remote = self.download_adapter.queue(selection.selected)
        queued = replace(
            searching,
            candidate=selection.selected,
            remote_id=remote.identifier,
            state=_state_from_remote(remote),
            next_attempt_at=self._next_poll(remote),
            last_error=remote.error,
        )
        queued = self.repository.save(queued, event="candidate_queued", detail=detail)
        if queued.state == AcquisitionState.AVAILABLE:
            return self._stage(queued)
        if queued.state in {AcquisitionState.FAILED_RETRYABLE, AcquisitionState.FAILED_FINAL}:
            return self._reschedule(queued, remote.error or "remote queue rejected candidate")
        return queued

    def _retry_remote(self, record: AcquisitionRecord) -> AcquisitionRecord:
        assert record.remote_id is not None
        remote = self.download_adapter.retry(record.remote_id)
        if remote.state in {RemoteState.ERROR, RemoteState.CANCELLED, RemoteState.UNKNOWN}:
            return self._reschedule(record, remote.error or f"remote retry is {remote.state.value}")
        updated = replace(
            record,
            state=_state_from_remote(remote),
            next_attempt_at=self._next_poll(remote),
            last_error=remote.error,
        )
        return self.repository.save(updated, event="remote_retry_started")

    def _synchronise(self, record: AcquisitionRecord) -> AcquisitionRecord:
        if not record.remote_id:
            return self._reschedule(record, "remote identifier is missing")
        remote = self.download_adapter.status(record.remote_id)
        state = _state_from_remote(remote)
        if state == AcquisitionState.AVAILABLE:
            available = self.repository.save(
                replace(record, state=state, next_attempt_at=None, last_error=None),
                event="download_available",
                detail={"progress": remote.progress},
            )
            return self._stage(available)
        if state in {AcquisitionState.FAILED_RETRYABLE, AcquisitionState.CANCELLED}:
            return self._reschedule(record, remote.error or f"remote state is {remote.state.value}")
        updated = replace(
            record,
            state=state,
            next_attempt_at=self._next_poll(remote),
            last_error=remote.error,
        )
        return self.repository.save(
            updated,
            event="download_status",
            detail={"remote_state": remote.state.value, "progress": remote.progress},
        )

    def _stage(self, record: AcquisitionRecord) -> AcquisitionRecord:
        if not record.candidate:
            return self._fail(record, "candidate is missing at staging time")
        staging = self.repository.save(
            replace(record, state=AcquisitionState.STAGING, next_attempt_at=None),
            event="staging_started",
        )
        path = self.download_adapter.retrieve(staging.candidate, self.staging_directory)
        return self.repository.save(
            replace(
                staging,
                state=AcquisitionState.STAGED,
                staged_path=str(path),
                next_attempt_at=None,
                last_error=None,
            ),
            event="file_staged",
            detail={"path": str(path), "md5": staging.candidate.identifier},
        )

    def _reschedule(
        self,
        record: AcquisitionRecord,
        error: str,
        detail: dict[str, object] | None = None,
    ) -> AcquisitionRecord:
        attempts = record.attempts + 1
        if attempts >= self.retry_policy.maximum_attempts:
            return self._fail(replace(record, attempts=attempts), error)
        delay = self.retry_policy.delay(attempts)
        updated = replace(
            record,
            state=AcquisitionState.FAILED_RETRYABLE,
            attempts=attempts,
            next_attempt_at=self.clock() + delay,
            last_error=error,
        )
        payload = {"error": error, "attempts": attempts, "retry_in_seconds": delay}
        payload.update(detail or {})
        return self.repository.save(
            updated,
            event="retry_scheduled",
            detail=payload,
            move_to_tail=True,
        )

    def _fail(self, record: AcquisitionRecord, error: str) -> AcquisitionRecord:
        return self.repository.save(
            replace(
                record,
                state=AcquisitionState.FAILED_FINAL,
                next_attempt_at=None,
                last_error=error,
            ),
            event="request_failed",
            detail={"error": error, "attempts": record.attempts},
        )

    def _next_poll(self, remote: RemoteDownload) -> float | None:
        if remote.state == RemoteState.AVAILABLE:
            return None
        return remote.next_retry_at or self.clock() + self.poll_interval_seconds


def _state_from_remote(remote: RemoteDownload) -> AcquisitionState:
    return {
        RemoteState.QUEUED: AcquisitionState.QUEUED,
        RemoteState.DOWNLOADING: AcquisitionState.DOWNLOADING,
        RemoteState.DELAYED: AcquisitionState.DELAYED,
        RemoteState.AVAILABLE: AcquisitionState.AVAILABLE,
        RemoteState.ERROR: AcquisitionState.FAILED_RETRYABLE,
        RemoteState.CANCELLED: AcquisitionState.CANCELLED,
        RemoteState.UNKNOWN: AcquisitionState.FAILED_RETRYABLE,
    }[remote.state]
