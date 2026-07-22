# Acquisition test report

Date: 2026-07-22

## Automated gate

The end-to-end fixture starts a real local HTTP server implementing the observed
Ephemera routes. It deliberately returns a misleading result before the correct
publication, then exercises queueing, progress polling, binary transfer, MD5
verification, atomic staging, cancellation, and persistent event history.

The suite also verifies that:

- a weak or disallowed candidate is not selected;
- a retryable failure moves behind work already in the queue;
- requests and history survive a SQLite repository reopen;
- a checksum mismatch leaves neither a final file nor a partial file;
- passage-search scope and verbatim assembly tests continue to pass;
- public sources contain no private deployment address or path.

## Compatibility smoke test

A live Ephemera 1.4.2 service successfully returned filtered French EPUB search
results and accepted a public-domain test request. Its upstream slow-download
path then encountered a provider challenge that the configured helper could not
solve on the first attempt. Amanuensis preserved the request, recorded the
provider error and next retry time, and left it behind other work. The provider
eventually made the file available. Amanuensis retrieved it into the isolated
test staging role, verified its 32-character MD5, and left no partial file. No
library import integration was enabled.

This distinguishes a functioning Amanuensis adapter from a temporarily
unavailable remote delivery path. Both the fixture and compatibility smoke tests
validate the complete protocol without evading provider controls or writing into
a real library.
