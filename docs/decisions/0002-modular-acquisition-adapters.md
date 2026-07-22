# ADR 0002: Separate catalogue and file acquisition adapters

- Status: accepted
- Date: 2026-07-22

## Context

Ephemera combines catalogue scraping, result persistence, candidate choice,
download queueing, retries, and post-download behavior. Its saved-request worker
selects the first search result. That coupling makes bibliographic mistakes hard
to explain and prevents one provider from being replaced without migrating the
entire workflow.

## Decision

Amanuensis owns the request, deterministic candidate selection, durable queue,
retry policy, staging transfer, and history. Catalogue search and file
acquisition use two independent ports. The initial Ephemera compatibility
adapter implements both public contracts, but the coordinator accepts different
objects for each role.

Candidate choice records title, contributor, language, format, and source
signals. Weak or ambiguous matches remain pending instead of silently choosing
the first result. Retryable failures use exponential backoff and receive a new
queue sequence. Files are streamed to a temporary file in staging, checked
against the selected MD5, and atomically renamed only after validation.

## Consequences

- Existing Ephemera deployments remain usable during migration.
- New catalogues and lawful download providers can be composed independently.
- Amanuensis can survive restarts without reconstructing its queue from a remote
  service.
- Provider-specific anti-automation controls are reported as failures and are
  not bypassed.
- Import into Grimmory remains a later, explicit stage and cannot be triggered by
  the acquisition adapter.
