# Vision

Amanuensis should do for books and periodicals what a good media acquisition
manager does for albums: turn an intent into a complete, verified, organized,
and discoverable library item without requiring routine manual intervention.

## Users should be able to

- search for a work, contributor, series, collection, or periodical;
- inspect editions and metadata evidence before choosing an item;
- follow a creator or series, or request a specific publication;
- understand why a request is queued, active, delayed, failed, or complete;
- let retryable failures return to the end of the queue automatically;
- review new files in a staging area before they enter the library;
- apply deterministic repairs globally or by confidence level;
- reconstruct fragmented series and publication runs;
- identify missing volumes or issues without confusing them with duplicates;
- extract structured contents from magazines, anthologies, and collections;
- search inside one selected book or an explicit corpus;
- receive exact, navigable passages assembled by proximity and relevance, without
  a generated answer, summary, or interpretation.

## Publication model

The catalogue must distinguish at least:

- abstract works from files and editions;
- novels, essays, comics, game books, magazines, fanzines, and anthologies;
- numbered series from unnumbered universes, product lines, and collections;
- publication runs from issue numbers;
- authors, editors, translators, illustrators, and other contributor roles;
- container publications from their stories, articles, scenarios, interviews,
  reviews, and portfolios.

## Automation model

Each background job exposes:

- enabled state and schedule;
- a run-now action;
- explicit scope and policy;
- progress, start time, duration, and current item;
- findings grouped by confidence;
- dry-run and apply modes when mutation is involved;
- a durable history and evidence trail.

## AI boundary

Local models are useful for cover comparison, contents classification, entity
linking, natural-language query understanding, embeddings, and reranking. They
must not silently invent metadata or rewrite source passages. Content search ends
with retrieval: the displayed text is always copied from the indexed source.

Text-bearing EPUB and PDF files are the primary indexing path. Image-only files
are reported as unavailable for content search; OCR is an optional future adapter,
not a prerequisite or a silent fallback.

## Non-goals

- Replacing Grimmory's reader and library interface.
- Depending on a particular host operating system or storage layout.
- Shipping credentials or private provider configuration.
- Treating a language model as an authoritative catalogue.
- Moving unverified downloads directly into a production library.
