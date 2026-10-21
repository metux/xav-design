# Specification chapters

The chapter files below are a navigable split of the consolidated draft. Their content is not automatically frozen or fully reconciled.

1. [Overview and architecture](00-overview.md)
2. [X11 wire format and common types](01-wire-format.md)
3. [Device discovery and logical devices](02-devices.md)
4. [Memory and buffers](03-memory-buffers.md)
5. [Shaders, descriptor layouts, and pipelines](04-shaders-pipelines.md)
6. [Command pools, command buffers, and command streams](05-commands.md)
7. [Submission and synchronization](06-submission-synchronization.md)
8. [Resource lifetime and errors](07-lifecycle-errors.md)
9. [Events, reference workflow, tests, and open issues](08-reference-tests-open-issues.md)

## Editorial conventions

- Define generic framing, byte order, padding, and length rules once in the wire-format chapter.
- Request descriptions should focus on request-specific payload fields; avoid repeating generic headers.
- Do not list offsets when field order and explicit field types make them unambiguous, except where offsets are needed to clarify a nonstandard layout.
- Keep unresolved choices visibly marked as open or provisional.
