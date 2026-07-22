# ADR 0001: Selected-corpus passage retrieval

Status: accepted

## Context

The primary content-search need is to locate and assemble relevant parts of books.
The system must not answer on the author's behalf, summarize the findings, or
interpret them. Searches always target one selected book or an explicit corpus.

Most indexed files already contain usable text. OCR is therefore outside the
default path and must never run as an invisible fallback.

## Decision

Build a passage retrieval pipeline with these stages:

1. Extract immutable source units from text-bearing EPUB and PDF files.
2. Segment them into overlapping passages while retaining exact offsets.
3. Resolve a selected corpus to a non-empty set of book identifiers.
4. Generate lexical and semantic candidates under that scope filter.
5. Fuse and rerank candidates without generating text.
6. Merge nearby hits using offsets in the immutable source unit.
7. Display exact source slices, locators, scores, and retrieval channels.

The application will offer relevance order and reading order. Nearby hits may be
joined with the untouched source text between them. Distant hits remain separate.

## Open-source components considered

- [Qdrant](https://github.com/qdrant/qdrant): selected as the first hybrid-search
  adapter because it supports dense, sparse, and late-interaction vectors together
  with payload filtering for book and corpus identifiers.
- [FlagEmbedding / BGE-M3](https://github.com/FlagOpen/FlagEmbedding): selected as
  the first multilingual retrieval model family. It supports dense, sparse, and
  multi-vector retrieval and covers French.
- [PyLate](https://github.com/lightonai/pylate): retained as an optional
  late-interaction reranking adapter after baseline evaluation.
- [ColBERT](https://github.com/stanford-futuredata/ColBERT): research and behavior
  reference for fine-grained passage retrieval.
- [txtai](https://github.com/neuml/txtai): useful all-in-one reference, but its
  generation and orchestration layers are broader than the required search path.
- [Readest](https://github.com/readest/readest): useful interaction reference for
  full-text ebook search and reader navigation, not the server-side retrieval core.

## Consequences

- No generative LLM is required for content search.
- Search quality can be measured independently from answer quality.
- A backend result outside the selected scope is a contract violation.
- Source units and offsets become durable data that must survive reindexing.
- Image-only files have an explicit not-indexable-without-OCR state.
- The vector and lexical implementation can change without changing the public
  result contract.

## Evaluation

A checked-in benchmark will contain natural-language queries, expected passage
identifiers, and forbidden out-of-scope identifiers. Initial metrics are recall at
20, mean reciprocal rank, scope violations, exact-text preservation, and latency.
Reranking is enabled only if it improves the passage benchmark.
