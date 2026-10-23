# Specification index

The chapters are ordered here; filenames intentionally do not repeat chapter numbers.

1. [Overview and architecture](overview.md)
2. [X11 wire protocol and common wire types](wire-protocol.md)
3. [Device discovery and logical devices](devices.md)
4. [Memory and buffers](memory-buffers.md)
5. [Shaders, descriptor layouts, and pipelines](shaders-pipelines.md)
6. [Command pools, command buffers, and command streams](command-recording.md)
7. [Queue submission and ordering](queue-submission.md)
8. [Synchronization objects](synchronization.md)
9. [Asynchronous events](events.md)
10. [Resource lifetime and ownership](resource-lifetime.md)
11. [Errors and error mapping](errors.md)
12. [Reference workflow and conformance](conformance.md)
13. [On-screen presentation in X11 windows](presentation.md) — server-side presentation architecture; request layouts not yet allocated.
14. [Open issues](open-issues.md)

## Audit records

- [Request catalogue and wire-contract audit](request-audit.md) — reviewed inventory, cross-chapter consistency result, and remaining exclusions.

## Central registries

- [Request subopcode registry](../registries/request-subopcodes.md) — inventory and stable numeric assignments for currently defined requests.
- [Feature-ID registry](../registries/feature-ids.md) and [device-extension registry](../registries/device-extensions.md) — the v0.1 optional sets are intentionally empty.
- [Physical-device property registry](../registries/physical-device-properties.md) — canonical Atom names, property types, value formats, and availability rules.
- [Command-buffer entry registry](../registries/command-entries.md) — numeric IDs and support status for v0.1 command entries.

## Editorial conventions

- Define generic framing, byte order, padding, and length rules once in the wire-protocol chapter.
- Request descriptions focus on request-specific payload and behavior; describe generic headers once.
- Do not list offsets when field order and explicit types make them unambiguous.
- Keep unresolved choices visibly marked as open or provisional.
- Preserve technical content during structural moves; semantic changes require explicit review.
