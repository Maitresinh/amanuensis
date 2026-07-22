# Amanuensis

**Acquisition, curation, and discovery for Grimmory and compatible digital libraries.**

Amanuensis is a self-hosted assistant for building and maintaining a digital
library. It brings discovery, watchlists, acquisition, a controlled staging
workspace, metadata repair, periodical indexing, and library import into one
observable workflow.

> Project status: early development. The domain model and project boundaries are
> established; production migration from Ephemera and Ephemera+ is in progress.

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
- Add grounded semantic search that always returns passages and source locations.

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

## Documentation

- [Vision and boundaries](docs/VISION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap and test gates](docs/ROADMAP.md)
- [Ephemera lineage](docs/UPSTREAM.md)
- [Contributing](CONTRIBUTING.md)

## Lineage

Amanuensis is an independent continuation inspired by Ephemera 1.4.2 and by the
Ephemera+ integration work. The original Ephemera repository is no longer
available on GitHub, so this repository cannot be represented as a native GitHub
fork. Its published OCI provenance is recorded in [UPSTREAM.md](docs/UPSTREAM.md).

No recovered Ephemera binary or minified artifact is included in this bootstrap
commit. Code will be migrated only when its source and licensing can be audited.

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
