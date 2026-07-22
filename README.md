# Amanuensis

**Acquisition, curation, and discovery for Grimmory and compatible digital libraries.**

Amanuensis is a self-hosted assistant for building and maintaining a digital
library. It brings discovery, watchlists, acquisition, a controlled staging
workspace, metadata repair, periodical indexing, and library import into one
observable workflow.

> Project status: early development. The acquisition core, durable queue, and
> Ephemera compatibility adapter are implemented. Grimmory import and the web
> client remain separate milestones.

## Why Amanuensis?

Book acquisition is only the first step. Files must still be identified,
deduplicated, checked, enriched, grouped into coherent series, and imported
without damaging the library. Magazines, anthologies, fanzines, comics, and
role-playing publications also need issue-aware metadata and structured tables
of contents that ordinary book managers rarely provide.

Amanuensis treats this as one auditable pipeline:

```text
discover -> watch/wish -> acquire -> stage -> identify -> review/repair -> import -> audit
```

## Product scope

- Search across pluggable bibliographic and catalogue providers.
- Follow authors, series, collections, and periodicals without downloading them.
- Maintain a wishlist for books, complete series, and future issues.
- Queue downloads with retries, backoff, provider rotation, and visible history.
- Hold every new file in a staging workspace before library import.
- Rank formats and editions, detect duplicates, and quarantine uncertain files.
- Normalize titles, contributors, identifiers, series, issue numbers, and tags.
- Model magazines and anthologies as first-class publications with contents.
- Send validated items to Grimmory through its API and import workflow.
- Run recurring jobs with progress, findings, review queues, and traceable actions.
- Search a selected book or corpus and assemble relevant, verbatim passages with
  exact source locations. No generated answer or synthesis is part of this path.

## Design principles

1. **Deterministic first.** Identifiers, hashes, manifests, filenames, and trusted
   catalogues are evaluated before heuristic or model-based decisions.
2. **Evidence over guesses.** AI may interpret covers, contents, and queries, but
   every proposed correction must retain its evidence and confidence.
3. **Staging before mutation.** Downloads are never treated as library-ready.
4. **Safe automation.** Destructive actions are reviewable, reversible where
   possible, and restricted by confidence and policy.
5. **Adapters, not assumptions.** Grimmory is the primary library integration,
   while acquisition and metadata sources remain replaceable.
6. **Periodicals are not malformed books.** Issues, volumes, publication runs,
   articles, stories, scenarios, translators, and page ranges have explicit models.
7. **Local-first intelligence.** Optional local models can assist without sending
   library content to third parties.
8. **Retrieval is not authorship.** Content search ranks and assembles original
   passages; it never rewrites them into an answer.

## Documentation

- [Vision and boundaries](docs/VISION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap and test gates](docs/ROADMAP.md)
- [Ephemera lineage](docs/UPSTREAM.md)
- [Contributing](CONTRIBUTING.md)

## Acquisition CLI

The first end-to-end vertical slice is available as a standard-library Python
package. Search and file acquisition are separate adapter ports; the included
compatibility adapter implements both through an Ephemera HTTP service.

```bash
python -m pip install -e .

amanuensis --api-url http://ephemera:8286/api search "Example title" \
  --author "Example author" --language fr --format epub

amanuensis --api-url http://ephemera:8286/api request "Example title" \
  --requested-title "Example title" --requested-author "Example author" \
  --language fr --format epub

amanuensis --api-url http://ephemera:8286/api run --wait
amanuensis queue
```

`request` is the durable wishlist entry point. Amanuensis scores normalized
results instead of selecting the provider's first hit. Temporary failures are
scheduled with exponential backoff and moved behind existing work. Completed
files are streamed to the configured staging role, verified against their MD5,
and published atomically. This slice never writes to a library directory.

Configuration can be supplied with command options or the variables documented
in [.env.example](.env.example). `cancel`, `retry`, and `history` expose the
corresponding queue operations without confirmation phrases.

## Lineage

Amanuensis is an independent continuation inspired by Ephemera 1.4.2 and by the
Ephemera+ integration work. The original Ephemera repository is no longer
available on GitHub, so this repository cannot be represented as a native GitHub
fork. Its published OCI provenance is recorded in [UPSTREAM.md](docs/UPSTREAM.md).

No recovered Ephemera binary or minified artifact is included. The compatibility
adapter is an independent implementation of the public HTTP contract and can be
replaced independently for catalogue search and file acquisition.

## Responsible use

Amanuensis does not endorse or bundle access to unauthorized content. Provider
adapters are optional, deployment-specific components. Users and contributors are
responsible for complying with applicable law and provider terms.

## Licence

New Amanuensis code is released under the [MIT License](LICENSE). Third-party and
migrated components retain their own notices and licences.

---

### Resume francais

Amanuensis est un assistant auto-heberge pour Grimmory et les bibliotheques
numeriques compatibles. Il unifie recherche, suivi, wishlist, telechargements,
sas de traitement, controle qualite, metadonnees, periodiques, import et recherche
semantique fondee sur des passages cites. Le projet reste adaptable: aucune
adresse, arborescence ou infrastructure particuliere n'est imposee.
