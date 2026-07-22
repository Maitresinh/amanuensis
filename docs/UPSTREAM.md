# Ephemera lineage

Amanuensis continues ideas and workflows explored by Ephemera and Ephemera+.

## Recovered Ephemera provenance

The following metadata was read from the published OCI image:

| Field | Value |
| --- | --- |
| Project | Ephemera |
| Original repository | `https://github.com/OrwellianEpilogue/ephemera` |
| Image | `ghcr.io/orwellianepilogue/ephemera:latest` |
| Digest | `sha256:a10b204c43de3a8e8aec8a7fe083af6c0aa042959484f2c833fcebf1270238ca` |
| Version | `1.4.2` |
| Revision | `a9ae94919f77e7e703fb4ba7495c263795a34bd3` |
| Published licence label | `MIT` |
| Image build date | `2025-12-26T12:28:38.555Z` |

The original repository and owner account returned GitHub `404` responses during
the recovery audit on 2026-07-22. GitHub therefore cannot create or display this
repository as a native fork.

## Source recovery status

The image contains package manifests, database migrations, compiled backend
JavaScript, shared declarations, and bundled web assets. Most original TypeScript
and frontend source files are absent. Compiled or minified artifacts are not
included in the Amanuensis bootstrap commit.

Before upstream code is imported, contributors must:

1. preserve exact provenance and original notices;
2. verify that the imported file is covered by the published licence;
3. prefer recoverable source over decompiled or minified output;
4. isolate compatibility code from the new domain model;
5. add a behavior test demonstrating what the imported component provides.

Amanuensis is not presented as an official Ephemera release and is not affiliated
with its original author.
