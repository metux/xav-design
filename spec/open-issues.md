# Open issues before v0.1 freeze

The following questions remain open; listing them here does not resolve them.

1. Future subopcode allocations as new requests are defined. The current 40 requests have stable assignments in [the central request subopcode registry](../registries/request-subopcodes.md). Existing assignments must not be renumbered.
2. Implementation-level ABI interoperability tests for `SelectEvents` and XGE framing against an X11/XGE implementation. The specification now fixes the 32-byte GenericEvent header, dynamic extension opcode, static event type IDs, event lengths, and scope-specific selection masks; see [events](events.md), [wire protocol](wire-protocol.md), and the conformance checklist.
3. Future property additions must be registered append-only; the four v0.1 properties and their wire representations are defined.
4. Future feature IDs and device extensions must be registered append-only; the v0.1 optional sets are intentionally empty.
5. Future semantics of `memory_properties_flags`: in v0.1 the field MUST be zero until a registry definition is explicitly assigned; see [memory properties](memory-buffers.md#52-getphysicaldevicememoryproperties).
6. Closed: `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` layouts, event-type IDs, XGE lengths, terminal-event exclusivity, and delivery behavior are specified in [events](events.md) and covered by the conformance checklist. Only implementation-level interoperability testing remains under item 2.
7. Whether future protocol versions should add fairness or bounded-progress guarantees for independent queues. In v0.1, same-queue submission order, absence of implicit cross-queue order, semaphore dependencies, and the lack of any fairness/latency promise are specified in [queue submission and ordering](queue-submission.md).
8. Ownership for future X11 resource-sharing mechanisms.
9. Physical Device UUID and Driver UUID are defined as opaque 16-byte `BYTE_ARRAY` properties; the server preserves the Vulkan-returned bytes exactly.

