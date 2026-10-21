# Request catalogue and wire-contract audit — 2026-10-21

## Scope

This audit compares the currently defined request inventory in [the central request subopcode registry](../registries/request-subopcodes.md) with the defining chapters for wire layout, exact or formula-based request length, request kind, common framing, and request-specific error behavior. It is a cross-chapter consistency review, not a claim of complete Vulkan conformance or a frozen v0.1 protocol.

## Inventory result

- The registry contains 39 currently defined requests.
- Every registered request has a defining specification chapter.
- The registry's Reply, Void, and Void + async-events classifications agree with the chapter descriptions.
- The reviewed fixed and formula-based length rules are internally consistent with their listed fields and variable-record counts.
- The common X11 framing rules consistently specify an 8-byte minimum request header, four-byte length units, zero padding, no BIG-REQUESTS in v0.1, and standard 32-byte X11 replies/errors.
- The request-specific error chapter defines the common XID, ownership, type, validation-order, and atomic-rejection rules used by the request chapters.

## Cross-chapter correction made during this audit

An outdated sentence in `DECISIONS.md` incorrectly included Fence and Semaphore in the eligible targets for `DestroyResource`. The normative lifetime chapter, error mapping, conformance cases, and request registry consistently exclude those types and require `DestroyFence` and `DestroySemaphore`. The decision log now matches the normative rule. The project status next steps were also refreshed to remove an obsolete BIG-REQUESTS/64-KiB reconciliation task.

## Known exclusions and unresolved items

These are not silently treated as defined requests or settled protocol behavior:

1. Event-selection requests are not included in the 39-request inventory because their wire layouts are not specified. Existing event definitions do not imply a request opcode.
2. Numeric registries for features, device extensions, properties/Atoms, descriptor types, shader stages, device types, queue flags, event types, and XAverius error codes remain incomplete.
3. The exact v0.1 supported feature/extension set, `memory_properties_flags`, timeout/scheduling boundaries, final Vulkan wait-stage mapping, and behavior when event delivery is impossible remain open as listed in [open issues](open-issues.md).
4. This audit does not establish full Vulkan-spec conformance, implementation feasibility, or final v0.1 freeze.

## Subopcode allocation policy

The 39 requests in the central registry are assigned explicit values 1 through 39 in the reviewed registry order. Value 0 is reserved and MUST NOT identify a request. These numbers are stable: later requests MUST use an unused value and MUST NOT renumber an existing request. Event-selection requests receive values only after their layouts are specified; they must use unused values and do not cause existing assignments to move. The numeric assignments are recorded in the central registry in a separate change after this audit record.
