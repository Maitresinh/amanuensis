# Contributing

Amanuensis is built around small, testable workflows rather than opaque global
cleanup operations.

## Contribution rules

- Keep domain decisions independent of a particular deployment or filesystem.
- Add integrations through ports and adapters.
- Record metadata provenance and confidence.
- Include dry-run behavior for destructive operations.
- Add an end-to-end fixture whenever a workflow crosses provider, staging, and
  library boundaries.
- Do not commit downloaded books, covers, provider caches, credentials, personal
  catalogues, or production database snapshots.
- Respect provider rate limits, attribution requirements, and terms of service.

## Development

The bootstrap domain package uses Python 3.12 and the standard library:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The implementation stack may expand as Ephemera compatibility and the web client
are migrated. Architecture decisions that change public contracts should be
documented before broad implementation.
