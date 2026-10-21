# Request catalogue and wire-contract audit — 2026-10-21

## Scope

This audit compares the currently defined request inventory in [the central request subopcode registry](../registries/request-subopcodes.md) with the defining chapters for wire layout, exact or formula-based request length, request kind, common framing, and request-specific error behavior. It is a cross-chapter consistency review, not a claim of complete Vulkan conformance or a frozen v0.1 protocol.

## Inventory result

- The registry contains 39 currently defined requests.
- Every registered request has a defining specification chapter.
- The registry's Reply, Void, and Void + async-events classifications agree with the chapter descriptions for the 39 registered requests.
- The common X11 framing rules specify an 8-byte request header, four-byte request-length units, zero padding, no BIG-REQUESTS in v0.1, and standard 32-byte X11 replies/errors.
- The second systematic pass found several cross-chapter discrepancies and underspecified reply fields. These are recorded below and corrected in follow-up commits; the earlier pass must not be read as a claim that every contract was already consistent.

## Cross-chapter correction made during this audit

An outdated sentence in `DECISIONS.md` incorrectly included Fence and Semaphore in the eligible targets for `DestroyResource`. The normative lifetime chapter, error mapping, conformance cases, and request registry consistently exclude those types and require `DestroyFence` and `DestroySemaphore`. The decision log now matches the normative rule. The project status next steps were also refreshed to remove an obsolete BIG-REQUESTS/64-KiB reconciliation task.

## Known exclusions and unresolved items

These are not silently treated as defined requests or settled protocol behavior:

1. Event-selection requests are not included in the 39-request inventory because their wire layouts are not specified. Existing event definitions do not imply a request opcode.
2. Numeric registries for feature IDs, device extensions, and property identifiers remain incomplete. Descriptor types, shader stages, device types, queue flags, command entries, event types, and XAverius error offsets already have dedicated registries; their v0.1 support definitions still need cross-checking against every use.
3. The exact v0.1 supported feature/extension set, `memory_properties_flags`, timeout/scheduling boundaries, final Vulkan wait-stage mapping, and behavior when event delivery is impossible remain open as listed in [open issues](open-issues.md).
4. This audit does not establish full Vulkan-spec conformance, implementation feasibility, or final v0.1 freeze.

## Subopcode allocation policy

The 39 requests in the central registry are assigned explicit values 1 through 39 in the reviewed registry order. Value 0 is reserved and MUST NOT identify a request. These numbers are stable: later requests MUST use an unused value and MUST NOT renumber an existing request. Event-selection requests receive values only after their layouts are specified; they must use unused values and do not cause existing assignments to move. The numeric assignments are recorded in the central registry in a separate change after this audit record.


## Second systematic pass: findings

The following items were identified by comparing the request inventory, defining chapters, central error rules, and conformance checklist:

1. **Descriptor support cross-check:** the current descriptor registry and conformance contract both correctly restrict v0.1 to `STORAGE_BUFFER`; uniform buffers and image descriptors remain unsupported. No registry change was needed.
2. **Shader-stage symbol mismatch:** the central wire registry names the v0.1 bit `COMPUTE`, while the initial example used `COMPUTE_SHADER`. The example must use the XAverius wire symbol, not a native Vulkan spelling.
3. **Discovery reply completeness:** `EnumeratePhysicalDevices` and `GetPhysicalDeviceQueueFamilyProperties` describe variable reply records but do not explicitly state the corresponding `reply.length` formula. `GetPhysicalDeviceProperty` names statuses without assigning numeric values.
4. **Reply/request contract precision:** the fence-status reply describes the status byte and trailing reserved bytes but leaves the standard reply fields between offsets 2 and 7 implicit. The contract should explicitly separate standard X11 header fields from reserved bytes.
5. **Error-mapping coverage:** several requests rely on the general error chapter without spelling out all Create-XID, field-value, backend-allocation, or status-reply outcomes. The central rules must be applied consistently; no Void request may silently turn a normal status into a reply.
6. **Audit metadata drift:** this audit's earlier registry-completeness statement became stale as registries were added. Its scope and unresolved list must describe the current branch rather than an earlier snapshot.

These are protocol-documentation corrections, not user-level design changes. Any newly exposed ambiguity that requires choosing new semantics remains an open issue rather than being guessed. The descriptor-type check is a confirmed consistency result, not a defect.
