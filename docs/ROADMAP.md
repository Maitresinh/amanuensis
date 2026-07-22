# Roadmap

Every phase has an end-to-end test gate. A feature is not complete when only its
screen or isolated function works.

## 0. Public foundation

- Establish project identity, licence, provenance, and contribution rules.
- Define domain states and adapter contracts.
- Inventory Ephemera and Ephemera+ behavior without importing private settings.

**Gate:** tests validate legal state transitions and the repository contains no
deployment-specific addresses, paths, credentials, or cached content.

## 1. Selected-corpus passage search

- Parse text-bearing EPUB and PDF files into immutable source units.
- Preserve book, chapter/page, block, and character-offset provenance.
- Retrieve lexical and semantic candidates inside an explicit book scope.
- Rerank passages and merge only adjacent or overlapping source spans.
- Display exact excerpts with expandable context and reader navigation.
- Report image-only files as unindexed; do not invoke OCR implicitly.

**Gate:** benchmark queries over one book and a selected multi-book corpus retrieve
the expected passages, never leak results from outside the scope, preserve source
text byte-for-byte after decoding, and return no generated prose.

## 2. Acquisition core

- Search API with normalized provider results.
- Follow list and wishlist as distinct request modes.
- Durable queue, retry/backoff, provider rotation, cancellation, and history.
- Detailed download progress and actionable failure reasons.

**Gate:** a fixture publication can be searched, requested, downloaded through a
test provider, retried after failure, and placed in staging exactly once.

## 3. Staging and Grimmory

- File validation, hashing, format inspection, and quarantine.
- Metadata manifest and deterministic destination planning.
- Grimmory adapter, BookDrop/import flow, and confirmation polling.

**Gate:** a downloaded fixture moves through every state and appears once in a
test Grimmory instance with its file and metadata linked.

## 4. Metadata and periodicals

- Pluggable bibliographic providers with cache and provenance.
- Contributor, title, identifier, series, and issue normalization.
- Publication-run model for magazines and unnumbered RPG product lines.
- Structured contents for anthologies, magazines, and game publications.

**Gate:** representative novel, anthology, magazine issue, and unnumbered RPG
publication are identified and imported without being forced into the same model.

## 5. Library maintenance

- Full-library duplicate scan with edition- and format-aware policies.
- Broken metadata, cover, orphan, and fragmented-series jobs.
- Confidence-based review and batch application.
- Merge plans that preserve the strongest metadata before file deletion.

**Gate:** seeded duplicates and damaged records are all found; dry-run output
matches applied results; unrelated records remain unchanged.

## 6. Release engineering

- Reproducible containers and migrations.
- Upgrade and rollback tests.
- Provider compatibility matrix and observability guidance.
- Stable API documentation and extension examples.

**Gate:** a clean deployment passes smoke, migration, restore, and end-to-end
tests without any environment-specific source changes.
