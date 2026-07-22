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

## Disappearance audit

No public statement from the original maintainer has been found. The evidence
available on 2026-07-22 establishes the following timeline:

- Ephemera `v2.0.0` was released from commit `3d3eaef1` on 2026-01-05.
- The [last successful Wayback Machine capture](https://web.archive.org/web/20260107041044/https://github.com/OrwellianEpilogue/ephemera)
  of the original repository was on 2026-01-07.
- [Reddit users reported](https://www.reddit.com/r/selfhosted/comments/1qbetzv/did_something_happen_to_ephemera/)
  the repository disappearing within the preceding 24 hours on 2026-01-13. The
  [maintainer's original announcement](https://www.reddit.com/r/selfhosted/comments/1ow8rrk/ephemera_a_fast_ebook_downloader_with_a_simple/)
  was also deleted by its author.
- [A project contributor reported](https://www.reddit.com/r/selfhosted/comments/1ow8rrk/ephemera_a_fast_ebook_downloader_with_a_simple/nzqlp7k/)
  that a pull request had just been merged into `dev` and that the disappearance
  was unexpected even to them.
- The original GitHub owner account disappeared with the repository. No matching
  notice was found in GitHub's public [`github/dmca`](https://github.com/github/dmca/search?q=OrwellianEpilogue&type=code)
  repository.

The exact cause is therefore **unknown**. The observations are compatible with
a voluntary withdrawal, an account suspension, or a non-public legal/platform
request. The timing overlaps legal pressure and domain disruption affecting the
archive used by Ephemera, but that correlation is not proof of causation and must
not be reported as such.

Full source history survives in detached forks. In particular,
[`Kalagaar/ephemera`](https://github.com/Kalagaar/ephemera) and
[`PatrickCVest/ephemera`](https://github.com/PatrickCVest/ephemera) retain the
`v2.0.0` commit. [`bannert1337/ephemera`](https://github.com/bannert1337/ephemera)
is now the root of GitHub's surviving fork network but its default branch is an
older 2025-11-12 snapshot. None of these repositories has been verified as an
official continuation by the original maintainer.

## Source recovery status

The image contains package manifests, database migrations, compiled backend
JavaScript, shared declarations, and bundled web assets. Most original TypeScript
and frontend source files are absent from the image, but source through `v2.0.0`
is recoverable from the detached forks above. Compiled or minified artifacts are
not included in the Amanuensis bootstrap commit.

Before upstream code is imported, contributors must:

1. preserve exact provenance and original notices;
2. verify that the imported file is covered by the published licence;
3. prefer recoverable source over decompiled or minified output;
4. isolate compatibility code from the new domain model;
5. add a behavior test demonstrating what the imported component provides.

Amanuensis is not presented as an official Ephemera release and is not affiliated
with its original author.
