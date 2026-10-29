# Errors and error mapping

Error codes are offsets relative to the X11 extension's `first_error` value. The absolute X11 error code is `first_error + offset`; implementations must use the central values in [the error registry](../registries/errors.md), not allocate values ad hoc.

The error registry's offsets and event-local status values are separate numeric namespaces. In particular, `EXECUTION_FAILED` is error offset 3, while `SUBMISSION_FAILED.failure_class = EXECUTION_FAILED` is the event-local value 0; `WaitForFence` also has its own reply-status value for execution failure. Likewise, `DEVICE_LOST` has error offset 1, while the `WaitForFence` reply status is 3 and the `DEVICE_LOST` event's `reason_code` is a separate enum (for example, `VULKAN_DEVICE_LOST = 3`). Implementations MUST use the value from the field's defining registry, never a same-named value from another namespace.

For an accepted `QueueSubmit`, an execution failure is reported through the submission terminal event and synchronization state, with `ASYNC_ERROR` available for diagnostics. It MUST NOT be reported as a delayed X11 request error. The `EXECUTION_FAILED` error offset is not a substitute for the event-local `failure_class` or `WaitForFence` status.

XAverius errors use the standard 32-byte X11 error packet and add no XAverius-specific payload bytes. The packet carries the extension major opcode and the sequence number of the request that caused the error. The resource field identifies the affected resource when meaningful; otherwise it is zero. For v0.1, the X11 request-header `data` byte MUST be zero; XAverius `subopcode` is carried at offset 4, and the error packet's `minorCode` is the zero-extended `subopcode`. The error packet's `majorCode` is the extension major opcode.

## General Error Classes

| Situation | Result |
|---|---|
| Inconsistent request length or count | `BadLength` |
| Invalid field value, reserved bits, or flags | `BadValue` |
| Invalid or already occupied create XID | `BadIDChoice` |
| Wrong resource type or cross-device combination | normally `BadMatch` |
| XID does not identify a live XAverius resource or is unknown in this resource context | `BadValue` |
| Invalid Atom XID | `BadAtom` |
| Live XID has a resource type other than the expected type | `BadMatch` |
| Live resource belongs to another client and no sharing path is defined | `BadMatch` |
| Device unavailable | `DEVICE_UNAVAILABLE` |
| Device lost | `DEVICE_LOST` |
| Logical device normally destroyed while a host wait is open (`WaitSemaphores`) | `DEVICE_DESTROYED` as an X11 error; `WaitForFence` instead uses the normal reply status `DEVICE_DESTROYED = 4` |
| Invalid synchronization state | `INVALID_SYNCHRONIZATION_STATE` |
| Synchronous transfer failure | `TRANSFER_FAILED` |
| Synchronous allocation failure | `ALLOCATION_FAILED` |
| Invalid dependency prevents acceptance | `DEPENDENCY_FAILED` |
| Unexpected server error | `INTERNAL_SERVER_ERROR` |

## Normative XID Error Rule

The following baseline mapping applies to all XAverius requests unless a request defines an explicitly narrower rule:

- A required XAverius XID that does not identify a live resource in the XAverius resource space results in `BadValue`. This includes unknown, destroyed, and no-longer-public XIDs. XAverius resources use extension-specific resource types, so there is no corresponding core error such as `BadWindow` or `BadPixmap`.
- An XID that identifies a live resource but not the expected resource type results in `BadMatch`.
- A live resource owned by another client, with no explicit sharing path defined, results in `BadMatch`. The same applies to cross-device use.
- An invalid `ATOM` value results in `BadAtom`, not `BadValue`.
- An invalid or already-occupied create XID results in `BadIDChoice`; this differs from an invalid input XID.
- For server-assigned physical-device XIDs, an unknown or no-longer-valid XID also results in `BadValue`; a live resource of the wrong type results in `BadMatch`.

This mapping also applies when a request contains multiple XIDs: the server validates wire structure first, then field values, then XIDs in the field order specified by the request chapter. The first invalid XID determines the reported resource error. The request remains atomic.

### Create XIDs and Chunk-Based Creation

The target XID of a create request is not an input XID to be resolved as an existing resource. An invalid or occupied target XID therefore results in `BadIDChoice`; it MUST NOT be treated as an ordinary unknown input XID producing `BadValue`. For atomic batch creation, the entire request is rejected if any target XID is invalid, already occupied, or duplicated within the same request; no subset remains live.

This rule applies in particular to target XIDs for `CreatePipelineLayout`, `CreateComputePipeline`, and descriptor sets requested by `AllocateDescriptorSets`. It also applies to `ShaderModuleData` and `CommandBufferData` when the `CREATE` flag is set. For `ShaderModuleData`, a successful CREATE chunk reserves the target XID for the upload assembly; a second CREATE or an already-live target XID results in `BadIDChoice`.

For `ShaderModuleData` without `CREATE`, a matching upload assembly MUST exist. If the XID identifies a live resource of another type, the result is `BadMatch`; otherwise, a missing assembly results in `INVALID_SYNCHRONIZATION_STATE`, even if no public shader-module object exists yet. For `CommandBufferData` without `CREATE`, the target XID MUST identify a live command buffer: unknown or non-live XIDs result in `BadValue`, a live resource of the wrong type results in `BadMatch`, and a command buffer outside `RECORDING` results in `INVALID_SYNCHRONIZATION_STATE`. All checks occur before any state change.


## `CreateDevice`: Feature and Extension Requirements

Error mapping distinguishes invalid input from valid but unsupported requirements:

- `feature_id` is not defined in the XAverius feature registry: `BadValue`.
- `feature_id` is registered but is not supported by the selected physical device: `BadMatch`.
- A feature record with `enabled != 1` or a duplicate feature ID: `BadValue`.
- An extension name that is empty, longer than 255 bytes, or syntactically invalid: `BadValue`.
- An extension name that is syntactically valid but unknown to the XAverius extension registry or unsupported by the physical device: `BadMatch`.
- Duplicate extension names: `BadValue`.
- All requirements MUST be checked before device creation. On any failure, the requested `device_xid` remains unallocated; the server MUST NOT silently omit features or extensions.

The following error precedence applies to `CreateDevice` and refines the general XID rule for this request. It MUST match the ordered phases in [Device Discovery and Logical Devices](devices.md):

1. Validate complete request framing using checked arithmetic and the exact variable-length formula. Truncation, trailing bytes, or arithmetic overflow returns `BadLength`.
2. Validate wire-level and scalar fields: reserved fields and padding are zero; queue counts are positive; queue-family entries, feature IDs, and extension names are unique; priorities are finite and in [0,1]; `enabled = 1`; and extension names have valid ASCII Vulkan-name syntax and length 1–255. Violations return `BadValue`. Because no optional feature IDs are assigned in v0.1, every feature ID is unknown and returns `BadValue` here. A syntactically valid extension name is not rejected merely because it is unregistered.
3. Validate create-XID `device_xid`; an invalid or occupied target returns `BadIDChoice`.
4. Resolve `physical_device_xid`; an unknown or non-live XID returns `BadValue`.
5. Validate that the resolved XID is a Physical-Device resource and that its ownership/association is valid for this connection; wrong type or invalid ownership/association returns `BadMatch`.
6. Require successful XGE 1.0-or-later negotiation through `GEQueryVersion`; otherwise return `BadMatch`.
7. Check Physical-Device availability; an unavailable device returns `DEVICE_UNAVAILABLE`.
8. Validate queue-family indices and requested queue counts; an out-of-range family index returns `BadValue`, while a valid family unable to supply the requested count returns `BadMatch`.
9. Validate registered feature support and extension registration/support. This phase is reached only after earlier validation; if future versions register a feature, an unsupported registered feature returns `BadMatch`. A syntactically valid but unregistered or unsupported extension returns `BadMatch`.
10. Only after all validation succeeds may backend creation begin. Backend failures use the defined allocation/device error, and no logical Device or child resources may be published.

A later phase MUST NOT override an error from an earlier phase. In particular, malformed framing takes precedence over scalar errors; scalar errors (including unknown feature IDs) take precedence over XID errors; target-XID validation precedes physical-device lookup; resource type/ownership checks precede XGE negotiation; and XGE negotiation precedes device availability. All feature and extension records must be validated before creation, and every failure leaves `device_xid` unallocated with no partial Device or Queue objects.

## Request-specific error mapping

### `WriteBuffer`

Normative precedence: (1) total length with checked count/overflow arithmetic and the X11 request limit (`BadLength`); (2) positive `data_length` and zero padding (`BadValue`); (3) `device_xid`, then `buffer_xid` in wire order (`BadValue` for unknown/non-live XIDs); (4) live resource type, client ownership, and Device association (`BadMatch`); (5) Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (6) Buffer binding, `TRANSFER_DST`, and range (`BadMatch`); (7) transfer/synchronization work.

- Request-Gesamtlänge mit Überlauf oder oberhalb des für die Verbindung geltenden X11-Limits: `BadLength`
- Incorrect request length: `BadLength`
- Zero length, nonzero padding, or invalid reserved fields: `BadValue`
- Unknown/non-live XAverius XID: `BadValue`
- Wrong type, wrong Device, unbound Buffer, missing `TRANSFER_DST`, or range outside the Buffer: `BadMatch`
- Unavailable/lost Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchronous transfer failure: `TRANSFER_FAILED`
- Staging allocation failure: `ALLOCATION_FAILED`
- Detected dependency cycle while waiting for earlier GPU work: `DEPENDENCY_FAILED`

### `ReadBuffer`

Normative precedence: (1) exact 28-byte length (`BadLength`); (2) positive `data_length` (`BadValue`); (3) `device_xid`, then `buffer_xid` in wire order (`BadValue` for unknown/non-live XIDs); (4) live resource type, client ownership, and Device association (`BadMatch`); (5) Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (6) Buffer binding, `TRANSFER_SRC`, and range (`BadMatch`); (7) snapshot/transfer work.

- Incorrect request length: `BadLength`
- Zero length or invalid reserved fields: `BadValue`
- Unknown/non-live XAverius XID: `BadValue`
- Wrong type, wrong Device, unbound Buffer, missing `TRANSFER_SRC`, or range outside the Buffer: `BadMatch`
- Unavailable/lost Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchronous transfer failure: `TRANSFER_FAILED`
- Staging allocation failure: `ALLOCATION_FAILED`
- Detected dependency cycle before capturing the data snapshot: `DEPENDENCY_FAILED`

### `ShaderModuleData`

- Incorrect request length or mismatched payload size: `BadLength`
- Zero `data_length` for a data chunk, nonzero `data_length` for ABORT, nonzero padding, or an invalid flag combination: `BadValue`
- Invalid/non-live `device_xid`: `BadValue`; a live resource of the wrong Device type: `BadMatch`. With `CREATE`, an invalid/occupied `shader_module_xid` results in `BadIDChoice`. Without `CREATE`, the request requires a matching upload assembly; if none exists, the result is `INVALID_SYNCHRONIZATION_STATE`.
- `ABORT` without a matching active upload assembly: `INVALID_SYNCHRONIZATION_STATE`
- Invalid SPIR-V or a SPIR-V module that does not satisfy the v0.1 validation rules: `BadValue`; no Shader Module remains live, and the assembly is discarded
- Vulkan creation failure: the specific backend error, such as `DEVICE_LOST`, `ALLOCATION_FAILED`, or `INTERNAL_SERVER_ERROR`; no Shader Module remains live, and the assembly is discarded
- A malformed chunk discards the entire associated assembly. The X11 error for that chunk is synchronous and leaves no partial Shader Module. Errors during `ShaderModuleData` upload MUST NOT generate `ASYNC_ERROR`; Device loss is reported only through the general Device-loss path, not through an additional upload-specific event.

### Device discovery and Device creation

- `EnumeratePhysicalDevices`: an incorrect request length (`!= 8` bytes) results in `BadLength`; the reply payload consists only of complete `PHYSICALDEVICEINFO` records. An incomplete record MUST NOT be emitted. If no Physical Devices are available, an empty successful reply with `reply.length = 0` is permitted.
- `GetPhysicalDeviceProperty`: incorrect request length results in `BadLength`; an invalid Atom results in `BadAtom`; an unknown/non-live Device XID results in `BadValue`; when status is not `SUCCESS`, `property_type`, `value_length`, and the reply payload MUST be zero.
- `GetPhysicalDeviceQueueFamilyProperties` and `GetPhysicalDeviceMemoryProperties`: request length is exactly 12 bytes; an unknown/non-live Physical-Device XID returns `BadValue`.
- `CreateDevice`: falsche Länge `BadLength`; `queue_family_request_count = 0`, `queue_count = 0`, doppelte Queue-Family-Records, nicht-null reserviertes Feld, ungültige Priorität, `enabled` ungleich 1, doppelte Feature-/Extension-Einträge, unbekannte Feature-ID oder formal ungültiger Extension-Name `BadValue`; ungültige/belegte `device_xid` `BadIDChoice`; unbekannte/nicht-live Physical-Device-XID `BadValue`; falscher live Ressourcentyp, Queue-Family-Anforderung mit nicht verfügbarer oder nicht unterstützter Queue-Anzahl, registriertes aber nicht unterstütztes Feature, unbekannte oder nicht unterstützte formal gültige Extension oder Cross-Device-Zugriff `BadMatch`; ein nicht verfügbares Physical Device `DEVICE_UNAVAILABLE`. Die Prüfung ist atomar und veröffentlicht kein logisches Device bei Fehler.
- `CreateDefaultDevice`: incorrect length returns `BadLength`; a zero count, nonzero reserved field, or invalid priority returns `BadValue`; an invalid/occupied `device_xid` returns `BadIDChoice`; missing XGE negotiation returns `BadMatch`; no suitable device returns `DEVICE_UNAVAILABLE`.

  Normative precedence for `CreateDefaultDevice`: (1) exact/formula-based request length using checked arithmetic (`BadLength`); (2) `queue_count`, reserved field, and all priorities (`BadValue`); (3) target XID `device_xid` (`BadIDChoice`); (4) successful XGE 1.0 negotiation (`BadMatch`); (5) selection of a suitable Physical Device and compute queue (`DEVICE_UNAVAILABLE`). All checks occur before publishing a logical Device; on any error, the target XID remains unallocated.
- Both requests are void requests; success produces no normal reply.
- `DestroyDevice`: incorrect length returns `BadLength`; an unknown/non-live XAverius XID returns `BadValue`; foreign Device ownership returns `BadMatch`.

### `SelectEvents`

Normative validation precedence, matching [Event Selection](events.md#event-selection-selectevents): (1) exact 32-byte request length (`BadLength`); (2) scope, unused fields, reserved fields, and profile-legal mask bits (`BadValue`); (3) for `DEVICE` and `QUEUE` scope, resolve `device_xid` (`BadValue` if unknown/non-live); (4) validate live type and client ownership (`BadMatch`); (5) require successful XGE 1.0-or-later negotiation through `GEQueryVersion` (`BadMatch` otherwise); (6) for `QUEUE` scope, validate the queue-family/index tuple (`BadValue` if it does not identify an existing queue); (7) atomically replace the selected mask.

A later phase MUST NOT override an earlier error. In particular, malformed framing and scalar errors take precedence over XID errors, and XID/type/ownership errors take precedence over the XGE prerequisite and queue existence check. For `CONNECTION` scope, the device XID and queue tuple are not resolved because their required values are zero. Every error leaves the previous event selection unchanged.

The following individual mappings are retained as explicit error summaries and MUST be interpreted according to the ordered phases above:
- An incorrect request length results in `BadLength`.
- If the client has not successfully negotiated at least XGE 1.0 with `GEQueryVersion`, the request results in `BadMatch`.
- An unknown scope, nonzero flags/reserved fields, invalid mask bits, or nonzero fields outside the selected scope results in `BadValue`.
- An unknown or non-live Device XID, or an invalid queue-family/queue index, results in `BadValue`; a live resource of the wrong type or foreign client ownership results in `BadMatch`.
- An error leaves the previous event selection unchanged; a successful request atomically replaces only the selection for the specified scope.

### `CreateDescriptorSetLayout`

- An incorrect request length or a payload inconsistent with `binding_count` returns `BadLength`.
- Nonzero `flags`, reserved/invalid field values, unknown or unsupported stage bits, an unsupported descriptor type, or invalid binding records return `BadValue`.
- An invalid or already allocated create XID returns `BadIDChoice`.
- An unknown/non-live Device XID returns `BadValue`; a live resource of the wrong type, foreign Device ownership, or a cross-Device resource returns `BadMatch`.
- An unavailable/lost Device returns `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; a synchronous backend allocation failure returns `ALLOCATION_FAILED`.
- Every error leaves the Descriptor Set Layout uncreated; partial results are not permitted.

### `CreateCommandPool`

- An incorrect request length results in `BadLength`.
- Unknown pool flags or nonzero reserved bits result in `BadValue`; an invalid or already allocated pool XID results in `BadIDChoice`.
- An unknown or non-live Device XID results in `BadValue`; a live resource of the wrong type or foreign Device ownership results in `BadMatch`.
- A queue-family index outside the Device profile, or a queue family without command-buffer support, results in `BadValue`.
- An unavailable or lost Device results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`, respectively; backend allocation failure results in `ALLOCATION_FAILED`.
- On rejection, the pool XID remains unallocated.

### `CommandPool` and `CommandBufferData`

- An incorrect request length, an entry whose declared length exceeds the request boundary, or an incomplete entry header results in `BadLength`.
- Reserved bits/fields, invalid flag combinations, malformed padding, unknown command IDs, or invalid entry lengths (especially zero or less than the entry header) result in `BadValue`.
- After successful wire-structure validation, `CommandBufferData` validates the target XID before the pool XID, following field order. With `CREATE`, an invalid or already allocated target XID results in `BadIDChoice`; without `CREATE`, an unknown or non-live Buffer XID results in `BadValue`, and a live resource of the wrong type results in `BadMatch`.
- An unknown or non-live pool XID results in `BadValue`; a live resource of the wrong type, foreign client ownership, cross-device association, or incorrect pool association results in `BadMatch`. The specified pool MUST match the Buffer's parent pool even for `ABORT`.
- Without `CREATE`, the Buffer must be in `RECORDING`, otherwise `INVALID_SYNCHRONIZATION_STATE` is returned. For CREATE, append, and FINAL, this state check occurs only after successful XID/type/ownership validation and the Device-state check: an unavailable or lost Device returns `DEVICE_UNAVAILABLE` or `DEVICE_LOST` and takes precedence over an incompatible Buffer state. `ABORT` is the explicit logical exception: after structure, field, XID, type, and ownership validation, the `RECORDING` state is checked even if the Device is unavailable or lost; for a valid live Buffer/pool pair with matching parent pool, ABORT remains permitted after Device loss and starts no Vulkan work.
- `ResetCommandBuffer` with an incorrect request length results in `BadLength`; unknown or non-live Device/Buffer XIDs result in `BadValue`; a live resource of the wrong type, foreign ownership, or cross-device use results in `BadMatch`.
- After successful XID/ownership validation, an unavailable or lost logical Device returns `DEVICE_UNAVAILABLE` or `DEVICE_LOST` before the pool reset flag or Buffer state is checked.
- `ResetCommandBuffer` without the `RESET_COMMAND_BUFFER` pool flag or with a pending Buffer is rejected with `INVALID_SYNCHRONIZATION_STATE`.

### Presentation-only `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` (provisional command entry)

These rules apply only to the presentation-capable profile; `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` is assigned command-entry ID 5 in the central registry. Error precedence is: (1) Command-Entry-Struktur, exakte Entry-Länge, `entry_length` und reservierte Felder; (2) entry-lokale Feldsyntax, insbesondere Vierbyte-Ausrichtung von `buffer_offset` und die Regel, dass `row_length`/`image_height` entweder null oder positive Werte sein müssen; (3) Buffer-XID und danach Swapchain-XID auflösen (`BadValue` für unbekannte/nicht-live XIDs); (4) Typ, Client-/Device-Ownership und Cross-Device-Zugehörigkeit (`BadMatch`); (5) ressourcenabhängige Werte prüfen: `image_index` außerhalb der Swapchain, effektive Zeilenlänge/-höhe kleiner als die Swapchain-Ausdehnung oder ein Quellbereich außerhalb des Buffers ergeben `BadValue`; (6) Nutzungsflags prüfen: Buffer ohne `TRANSFER_SRC` oder Swapchain ohne `TRANSFER_DST` ergibt `BadMatch`; (7) Device-/Submission-Zustand und Image-State prüfen. Diese Reihenfolge verhindert, dass XID-abhängige Prüfungen ohne aufgelöste Ressource ausgeführt werden, während entry-lokale Syntaxfehler nicht durch einen ungültigen XID verdeckt werden. Die Image-State-Prüfung erfolgt atomar bei Submission-Annahme: ist das Image dann nicht `ACQUIRED` oder konkurriert der Submit mit einer Present-Transition, ergibt sich `INVALID_SYNCHRONIZATION_STATE`. Die Prüfung berücksichtigt alle zuvor in X11-Request-Reihenfolge angenommenen Zustandsübergänge: ein Copy-Submit nach einer bereits angenommenen `QueuePresent`-Transition auf `PRESENT_PENDING` wird abgewiesen; ein zuvor angenommener Submit bleibt dagegen gültig und behält seine internen Referenzen. Die Request-Reihenfolge ersetzt keine GPU-Synchronisation. Die Ablehnung darf weder den Command-Buffer teilweise annehmen noch Image-, Referenz- oder Semaphore-Zustände verändern. Ein Swapchain-Destroy bleibt abgewiesen, solange ein Recording-Command-Buffer darauf referenziert; nach erfolgreichem Destroy wird ein nicht-pending ausführbarer Command-Buffer mit dieser Referenz invalidiert.

### Einheitliche XID- und Zustandszuordnung für ausgewählte Requests

Die Prüfung erfolgt in dieser Reihenfolge: Wire-Länge und strukturelle Integrität; Feldwerte und reservierte Felder; Auflösung jeder erforderlichen XID; Ressourcentyp und Ownership; request-spezifische Zustands- und Backend-Prüfungen. Ein Fehler beendet den Request ohne Teiländerungen. Ein als `0` definierter optionaler XID-Wert wird nicht aufgelöst.

| Request / Condition | Error |
|---|---|
| `DestroyResource`: falsche Länge | `BadLength` |
| `DestroyResource`: XID löst keine live Ressource auf | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `DestroyResource`: Ressourcentyp ist nicht für den generischen Request zugelassen oder Ressource gehört einem anderen Client | `BadMatch` |
| `DestroyResource`: Ressource wird von einem `RECORDING`-Command-Buffer referenziert oder ihre typabhängige Pending-Regel verbietet die Zerstörung | `INVALID_SYNCHRONIZATION_STATE` |
| `BindBufferMemory`: falsche Länge | `BadLength` |
| `BindBufferMemory`: ungültige Feldwerte oder nicht-null reservierte Felder, sofern vorhanden | `BadValue` |
| `BindBufferMemory`: Device-, Buffer- oder Memory-XID ist ungültig/nicht live | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `BindBufferMemory`: falscher Ressourcentyp oder Client-/Device-Ownership passt nicht | `BadMatch` |
| `BindBufferMemory`: Device ist nicht verfügbar/verloren, nach XID-/Typ-/Ownership-Prüfung und vor bindungsabhängigen Zustands-/Backend-Prüfungen | `DEVICE_UNAVAILABLE` / `DEVICE_LOST` |
| `BindBufferMemory`: Buffer bereits gebunden, Memory-Type nicht erlaubt, Alignment falsch oder Allocation zu klein | `BadMatch` |
| `UpdateDescriptorSets`: falsche Gesamtlänge oder Payload passt nicht zu `write_count` | `BadLength` |
| `UpdateDescriptorSets`: `write_count = 0`, reservierte Felder ungleich null, doppelte Writes desselben Slots, ungültige Werte/Flags oder nicht zugewiesener `descriptor_type` | `BadValue` |
| `UpdateDescriptorSets`: ungültige/nicht-live Device-, Set- oder Buffer-XID | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `UpdateDescriptorSets`: falscher live Typ, fremde Client-/Device-Ownership, Layout/Binding/Array-Slot oder registrierter Descriptor-Typ inkompatibel, Buffer ungebunden oder Bereich/Alignment ungültig | `BadMatch` |
| `UpdateDescriptorSets`: Device ist nicht verfügbar/verloren, nach XID-/Typ-/Ownership-Prüfung und vor Layout-/Binding-/Pending-Zustandsprüfungen | `DEVICE_UNAVAILABLE` / `DEVICE_LOST` |
| `UpdateDescriptorSets`: Layout-/Binding-/Slot-Inkompatibilität oder betroffenes Set wird von angenommener Arbeit verwendet | `BadMatch` / `INVALID_SYNCHRONIZATION_STATE` gemäß Bedingung |
| `QueueSubmit`: falsche Länge, inkonsistente Counts oder Längenberechnung läuft über | `BadLength` |
| `QueueSubmit`: Token ist null oder auf derselben Verbindung bereits verwendet; reservierte Felder, syntaktisch ungültige Wait-Stage-Maske (0 oder reservierte Bits), ungültige typunabhängige Feldwerte, doppelte rohe Wait-/Signal-Semaphore-XIDs oder dieselbe Semaphore in beiden Arrays | `BadValue` |
| `QueueSubmit`: Device-, Command-Buffer-, Semaphore- oder nicht-null Fence-XID ungültig/nicht live | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `QueueSubmit`: falscher Ressourcentyp, fremde Client-/Device-Ownership oder angegebene Queue wurde nicht für dieses Device erstellt | `BadMatch` |
| `QueueSubmit`: Device unavailable/lost after successful XID/type/ownership/queue validation and before mutable submission-state checks | `DEVICE_UNAVAILABLE` / `DEVICE_LOST` |
| `QueueSubmit`: type-dependent Binary value is nonzero or Timeline signal value is not greater than the observable counter, after XID, type, and Device-state checks | `BadValue` |
| `QueueSubmit`: Timeline signal value exceeds the observable counter but conflicts with an already reserved pending GPU signal value | `INVALID_SYNCHRONIZATION_STATE` |
| `QueueSubmit`: a Command Buffer is not `EXECUTABLE`, a Fence is not submit-eligible, a Semaphore state is invalid, or a syntactically valid wait-stage mask contains a stage unsupported by the addressed queue family | `INVALID_SYNCHRONIZATION_STATE` |
| `QueueSubmit`: Abhängigkeit verhindert die Annahme, ohne dass eine speziellere Zustandsregel greift | `DEPENDENCY_FAILED` |
| `QueueSubmit`: synchronous error before acceptance | no state changes; the token remains unused, command buffers remain `EXECUTABLE`, Fence/Semaphore states and internal references remain unchanged; no submission event or `ASYNC_ERROR` is emitted |
| `ResetFence`: falsche Länge | `BadLength` |
| `ResetFence`: Device- oder Fence-XID ungültig/nicht live | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `ResetFence`: falscher Ressourcentyp oder Fence gehört zu einem anderen Client/Device | `BadMatch` |
| `ResetFence`: Fence ist weder `SIGNALED` noch `FAILED` | `INVALID_SYNCHRONIZATION_STATE` |
| `ResetFence`: Device verloren | `DEVICE_LOST` |

`ResetFence` serializes its state check and reset atomically against submission completion and new `QueueSubmit` acceptance. A reset of `PENDING` is rejected without mutation; a terminal state committed first may be reset. Each accepted submission captures the Fence's internal identity and use generation. Completion/failure callbacks may mutate Fence state only when their terminal transition wins and the captured identity, generation, and current submission association still match. Reset and reuse invalidate stale callback authority; delayed/duplicate callbacks from older submissions cannot overwrite a newer `PENDING`, `SIGNALED`, `FAILED`, or reset state.

Für alle fünf Requests gilt: Fehler vor Annahme werden synchron als X11-Fehler gemeldet; der Request darf keine Teiländerungen hinterlassen. Nach angenommener `QueueSubmit` werden Ausführungsfehler ausschließlich über die Submission-Terminalereignisse und zugehörige Zustände gemeldet, nicht als nachträglicher X11-Fehler. Ein nicht verfügbarer Zustand wird nur dann gemeldet, wenn der Request tatsächlich weitere Backend-Arbeit benötigt; rein logische Bereinigung nach Device Loss folgt den jeweiligen Lebensdauerregeln.

### Synchronization Requests

- `CreateSemaphore`: incorrect length `BadLength`; invalid type, value, flags, or reserved fields `BadValue`; invalid or already allocated create XID `BadIDChoice`; unknown or non-live Device XID `BadValue`; wrong live resource type or foreign Device ownership `BadMatch`; unavailable or lost Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; backend allocation failure `ALLOCATION_FAILED`. On rejection, the target XID remains unallocated.
- `CreateFence`: incorrect length `BadLength`; invalid flags or reserved fields `BadValue`; invalid or already allocated create XID `BadIDChoice`; unknown or non-live Device XID `BadValue`; wrong live resource type or foreign Device ownership `BadMatch`; unavailable or lost Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; backend allocation failure `ALLOCATION_FAILED`. On rejection, the target XID remains unallocated.
- `GetSemaphoreCounterValue`: normative precedence: exact 16-byte length (`BadLength`); resolve Device then Semaphore XID (`BadValue`); validate live type, ownership, and Device association (`BadMatch`); check Device state (`DEVICE_LOST`); require Timeline semaphore (`BadMatch`). Earlier phases win. The Device-state check is serialized with the counter snapshot: established Device Loss returns `DEVICE_LOST`; otherwise the counter is returned as of the query's linearization point.
- `SignalSemaphore`: normative precedence: incorrect length `BadLength`; resolve Device XID, then Semaphore XID (`BadValue` for unknown or non-live XIDs); validate resource type, ownership, and cross-device use (`BadMatch`); check Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); finally validate semaphore type and signal-value/reservation rules. A Binary semaphore returns `BadMatch`; a timeline `signal_value` not greater than the observable counter returns `BadValue`; a value that exceeds the counter but crosses or violates an already reserved GPU signal value returns `INVALID_SYNCHRONIZATION_STATE`. A synchronous rejection performs no partial host signal and leaves counters and reservations unchanged.
- `WaitSemaphores`: normative precedence: length and overflow `BadLength`; then zero count, invalid wait mode, or duplicate Semaphore XIDs `BadValue`; then resolve Device and Semaphore XIDs in array order (`BadValue` for unknown or non-live XIDs); validate type, ownership, and cross-device use (`BadMatch`); check Device state (`DEVICE_LOST`); finally require every Semaphore to be `TIMELINE` (`BadMatch`). These errors occur before wait registration and leave state unchanged. Device loss of an already registered wait is terminal and reported as X11 error `DEVICE_LOST`; `DestroyDevice` terminates an open wait with `DEVICE_DESTROYED` unless Device loss was already terminally established. `TIMEOUT` is only a normal reply status. For nonzero timeouts, the initial condition check and registration are atomic with counter publication; a racing signal is either observed by the check or triggers reevaluation of the installed registration. Timeout zero performs a single check without registering. This prevents lost wakeups.
- `GetFenceStatus`: normative precedence: exact 16-byte length (`BadLength`); resolve Device then Fence XID (`BadValue`); validate live types, ownership, and Device association (`BadMatch`); atomically snapshot the stored Fence state. Device Loss is not an error for this state-only query; the result reflects the state at its linearization point.
- `ResetFence`: incorrect length `BadLength`; unknown or non-live Device or Fence XIDs `BadValue`; wrong live resource type, foreign ownership, or cross-device use `BadMatch`. After valid XID, type, and ownership checks, `DEVICE_LOST` takes precedence over the Fence state. Only when the Device is available may `SIGNALED` and `FAILED` be reset; other states return `INVALID_SYNCHRONIZATION_STATE`.
- `WaitForFence`: normative precedence: exact 24-byte length (`BadLength`); resolve Device XID, then Fence XID (`BadValue`); validate live types, client ownership, and Device association (`BadMatch`); then determine the wait outcome. Device loss returns normal reply status `DEVICE_LOST`, even if the stored Fence state is `FAILED`; timeout, execution failure, and `DestroyDevice` also use normal reply statuses, not X11 errors. If Device Loss has already been detected and established as terminal, it takes precedence over a later `DestroyDevice`; otherwise processing `DestroyDevice` while the wait remains open returns `DEVICE_DESTROYED`. Rejected requests do not register a wait or retain wait-only references.
- `DestroyFence`: normative precedence: exact 16-byte length (`BadLength`); resolve Device XID, then Fence XID (`BadValue`); validate live types, client ownership, and Device association (`BadMatch`); finally check lifetime blockers (`INVALID_SYNCHRONIZATION_STATE` while the Fence is `PENDING` or an open `WaitForFence` registration references that exact internal Fence identity). Device Loss alone is not an error for this logical cleanup request. A terminally established wait no longer blocks destruction, even if its reply has not yet been sent. Rejection leaves the XID and Fence state unchanged.
- `DestroySemaphore`: incorrect length `BadLength`; unknown or non-live Device or Semaphore XIDs `BadValue`; wrong live type, foreign client ownership, or cross-device use `BadMatch`; `INVALID_SYNCHRONIZATION_STATE` while an accepted queue wait, queue signal, an open `WaitSemaphores` registration for that exact internal Semaphore identity, or another active host operation uses the Semaphore. A terminally established wait no longer blocks destruction, even if its reply has not yet been sent. Rejection leaves the XID and synchronization state unchanged. Device loss alone does not invalidate public XIDs; subsequent `DestroyDevice` cascade invalidation may bypass these ordinary rejection rules.

### `DestroyResource`

- Falsche Request-Länge: `BadLength`
- Ungültige oder nicht mehr live XID: `BadValue` für eine unbekannte/nicht-live XAverius-XID
- Ressourcentyp, der nicht für den generischen Request zugelassen ist (insbesondere Fence und Semaphore), oder falsche Ownership: `BadMatch`
- Verstoß gegen die typabhängigen Recording-/Pending-Lebensdauerregeln: `INVALID_SYNCHRONIZATION_STATE`
- Ablehnung lässt XID, interne Lebensdauerzustände und abhängige Command-Buffer-Zustände unverändert.
- Verbindliche Präzedenz: (1) exakte Request-Länge (`BadLength`); (2) Auflösung der `resource_xid` (`BadValue` bei unbekannt/nicht live); (3) erlaubter Ressourcentyp und Client-Ownership (`BadMatch`); (4) typabhängige Recording-/Pending-Lebensdauerregeln (`INVALID_SYNCHRONIZATION_STATE`). Die Prüfungen und die öffentliche Invalidierung bilden einen atomaren Übergang. Device Loss allein ist kein zusätzlicher Ablehnungsgrund und darf nicht pauschal `DEVICE_LOST` für `DestroyResource` erzeugen. Bereits terminalisierte GPU-Arbeit blockiert nicht mehr allein wegen ihres früheren Pending-Zustands; tatsächliche Recording-Referenzen und typabhängige noch aktive Verwendungen bleiben maßgeblich. Interne Objekte und Backend-Referenzen werden bis zur sicheren Quieszenz erhalten oder quarantänisiert. `DestroyDevice` darf anschließend die definierte Kaskadeninvalidierung durchführen.

### Ressourcenzerstörung und Memory-Freigabe

- Destroy einer Ressource, die von einem `RECORDING`-Command-Buffer referenziert wird: `INVALID_SYNCHRONIZATION_STATE`.
- Destroy eines pending Command Buffers, Descriptor Sets, Buffers, einer Pipeline oder eines Pipeline Layouts: `INVALID_SYNCHRONIZATION_STATE`.
- `DestroyCommandPool`: `INVALID_SYNCHRONIZATION_STATE`, wenn mindestens ein Kind-Command-Buffer pending ist.
- `DestroyDescriptorPool` oder `FreeDescriptorSets`: `INVALID_SYNCHRONIZATION_STATE`, wenn ein betroffenes Set pending verwendet oder von einem `RECORDING`-Command-Buffer referenziert wird.
- `DestroyFence`: `INVALID_SYNCHRONIZATION_STATE`, solange die Fence einer nicht-terminalen Submission zugeordnet ist oder eine offene `WaitForFence`-Registrierung genau diese interne Fence-Identität referenziert.
- `DestroySemaphore`: `INVALID_SYNCHRONIZATION_STATE`, solange ein angenommener Queue-Wait/-Signal, eine offene `WaitSemaphores`-Registrierung für genau diese interne Semaphore-Identität oder eine andere laufende Host-Operation die Semaphore verwendet.
- Bei beiden Requests blockiert ein Host-Wait die Zerstörung nicht mehr, sobald sein terminales Ergebnis serverseitig serialisiert festgestellt wurde; ein noch nicht versendeter Reply ist kein Hindernis. Device loss alone does not invalidate public XIDs. If `DestroyDevice` is subsequently processed, its device-wide cascading invalidation may bypass these ordinary rejections.
- `FreeMemory`: `BadMatch`, solange irgendein intern noch lebender Buffer an die Allokation gebunden ist, auch wenn dessen öffentliche XID bereits invalidiert wurde; `INVALID_SYNCHRONIZATION_STATE`, solange angenommene Arbeit auf die Allokation zugreift.
- A destroy request rejected by lifetime rules leaves all public XIDs and command-buffer states unchanged.
- Die Device-weite Kaskadeninvalidierung durch `DestroyDevice` ist von diesen normalen Pending-Use-Ablehnungen ausgenommen; Device Loss allein invalidiert keine öffentlichen XIDs. Interne Referenzen müssen in jedem Fall sicher erhalten bleiben.

### Buffer- und Memory-Requests

- `CreateBuffer`: falsche feste Länge `BadLength`; nicht-positive Größe, unbekannte Usage-Bits oder nicht-null reservierte Felder `BadValue`; ungültige oder bereits belegte Create-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp oder fremdes Device `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; fehlgeschlagene Backend-Erstellung wegen Speicherknappheit `ALLOCATION_FAILED`; kein Buffer bleibt bei Ablehnung live. Präzedenz: Länge, skalare Felder, Ziel-XID, Device-XID, Typ/Ownership, Device-Zustand, Backend-Erstellung.
- `GetBufferMemoryRequirements`: falsche Länge `BadLength`; unbekannte/nicht-live Buffer-/Device-XID `BadValue`; falscher Ressourcentyp oder Cross-Device-Zugriff `BadMatch`. Präzedenz: (1) exakte 16-Byte-Länge; (2) Device-XID, dann Buffer-XID in Wire-Reihenfolge; (3) Ressourcentyp, Ownership und Device-Zuordnung; (4) gespeicherte Requirements zurückgeben. Die Abfrage startet keine Backend-Arbeit und bleibt bei Device Loss zulässig, solange die öffentlichen XIDs gültig sind.
- `AllocateMemory`: incorrect length `BadLength`; invalid size, memory-type index, or reserved field `BadValue`; invalid or occupied create XID `BadIDChoice`; unknown or non-live Device XID `BadValue`; live resource of the wrong type or foreign Device ownership `BadMatch`; unavailable or lost Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; backend allocation failure `ALLOCATION_FAILED`; on rejection, the target XID remains unallocated. Precedence: length, scalar fields, target XID, Device XID, type/ownership, Device state, backend allocation.
- `FreeMemory`: siehe die Lebensdauerregeln unten; bei Ablehnung bleibt die Allokation öffentlich gültig.
- `BindBufferMemory`: siehe die spezifische Zuordnung unten.

### Descriptor-Pool- und Pipeline-Requests

- `CreateDescriptorPool`: falsche Länge oder nicht zum `pool_size_count` passende Payload `BadLength`; ungültige Counts, doppelte Pool-Size-Typen, nicht unterstützte Descriptor-Typen oder nicht-null reservierte Felder `BadValue`; ungültige/belegte Pool-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Backend-Allokationsfehler `ALLOCATION_FAILED`; bei Ablehnung bleibt die Pool-XID unangelegt.
- `AllocateDescriptorSets`: Länge/Entry-Struktur `BadLength`; Count/reservierte Felder `BadValue`; Ziel-Set-XIDs in Array-Reihenfolge `BadIDChoice`; danach Eingabe-XIDs in Wire-Reihenfolge (Device, Pool, Layouts) `BadValue`; falsche live Typen/Ownership `BadMatch`; Device-Zustand `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Pool-/Layout-Inkompatibilität `BadMatch`; Kapazitäts-/Backend-Allokationsfehler `ALLOCATION_FAILED`. Präzedenz und Batch-Atomarität sind im Request-Kapitel normativ festgelegt; keine Teilmenge bleibt live.
- `FreeDescriptorSets`: falsche Länge `BadLength`; Count null oder nicht-null reservierte Felder `BadValue`; unbekannte/nicht-live Device-, Pool- oder Set-XID `BadValue`; falsche live Ressourcentypen, fremde Ownership oder Set gehört nicht zum angegebenen Pool/Device `BadMatch`; pending oder RECORDING-Referenz `INVALID_SYNCHRONIZATION_STATE`. Nach Device Loss bleibt die logische Freigabe zulässig und erfordert keine neue Vulkan-Arbeit; interne Referenzen bleiben bis zur sicheren Quieszenz erhalten. Keine Teilfreigabe bei Ablehnung.
- `DestroyDescriptorPool`: falsche Request-Länge `BadLength`; unbekannte/nicht-live Pool-XID `BadValue`; falscher live Ressourcentyp oder fremde Client-/Device-Ownership `BadMatch`; wenn ein Kind-Set pending verwendet oder von einem `RECORDING`-Command-Buffer referenziert wird, `INVALID_SYNCHRONIZATION_STATE`. Device Loss allein ist kein Ablehnungsgrund für die logische Bereinigung; die Pending-/Recording-Prüfungen bleiben bestehen. Die Ablehnung ist atomar: Pool, Sets und Referenzen bleiben unverändert.
- `CreatePipelineLayout`: Wire-Länge `BadLength`; feldlokale Stage-/Range-/Reserved-Fehler `BadValue`; Ziel-XID `BadIDChoice`; Device-/Set-Layout-XIDs `BadValue`; falsche live Typen/Ownership/Cross-Device `BadMatch`; Device-Zustand `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; danach geräteabhängige Limits/Kompatibilität und Backend-Allokation. Kein Pipeline Layout bleibt bei Ablehnung live.
- `CreateComputePipeline`: Wire-Länge `BadLength`; Entry-Point-/Padding-/Reserved-Feldfehler `BadValue`; Ziel-XID `BadIDChoice`; Device-/Layout-/Shader-XIDs `BadValue`; falsche live Typen/Ownership/Cross-Device `BadMatch`; Device-Zustand `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; danach Backend-Erstellung/Allokation. Kein Pipeline-Objekt bleibt bei Ablehnung live.

### Command Pool requests

- `CreateCommandPool`: falsche Länge `BadLength`; unbekannte Flags oder nicht-null reservierte Felder `BadValue`; ungültige/belegte Pool-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`; Queue-Family-Index außerhalb des Device-Profils oder ohne Command-Buffer-Unterstützung `BadValue`.
- `DestroyCommandPool`: falsche Länge `BadLength`; unbekannte/nicht-live XID `BadValue`; falscher Typ oder Cross-Device-Ownership `BadMatch`; mindestens ein pending Kind-Command-Buffer `INVALID_SYNCHRONIZATION_STATE`. Device Loss allein ist kein Ablehnungsgrund; sobald betroffene Submissions terminalisiert und ihre Command Buffer nicht mehr pending sind, bleibt die logische Pool-Bereinigung zulässig. Ablehnung ist atomar.

### Synchronization requests

- `CreateSemaphore` und `CreateFence`: falsche Länge `BadLength`; ungültige Typen, Werte, Flags oder reservierte Felder `BadValue`; ungültige/belegte Create-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Backend-Allokationsfehler `ALLOCATION_FAILED`; bei Ablehnung bleibt die jeweilige Ziel-XID unangelegt.
- `GetSemaphoreCounterValue`: normative Präzedenz: exakt 16 Byte (`BadLength`); Device- und danach Semaphore-XID auflösen (`BadValue`); live Typ, Ownership und Device-Zuordnung prüfen (`BadMatch`); Device-Zustand prüfen (`DEVICE_LOST`); Timeline-Semaphor verlangen (`BadMatch`). Frühere Phasen haben Vorrang. Zustandsprüfung und Counter-Snapshot sind gegen Device Loss serialisiert.
- `SignalSemaphore`: verbindliche Präzedenz: falsche Länge `BadLength`; Device-XID, dann Semaphore-XID (`BadValue` bei unbekannt/nicht-live); Ressourcentyp/Ownership/Cross-Device (`BadMatch`); Device-Zustand (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); zuletzt Semaphore-Typ und Signalwert-/Reservierungsprüfung (Binary `BadMatch`; `signal_value` kleiner oder gleich dem beobachtbaren Counter `BadValue`; ein Wert oberhalb des Counters, der eine bestehende GPU-Signalreservierung kreuzt oder verletzt, `INVALID_SYNCHRONIZATION_STATE`). Bei synchroner Ablehnung wird kein Host-Signal teilweise ausgeführt und Counter sowie Reservierungen bleiben unverändert.
- `WaitSemaphores`: verbindliche Präzedenz: Länge/Überlauf `BadLength`; danach Count null, ungültiger Wait-Modus oder doppelte Semaphore-XIDs `BadValue`; dann Device-XID und Semaphore-XIDs in Array-Reihenfolge (`BadValue` bei unbekannt/nicht-live); danach Typ/Ownership/Cross-Device (`BadMatch`); danach Device-Zustand (`DEVICE_LOST`); zuletzt muss jeder Semaphore-Typ `TIMELINE` sein (`BadMatch`). Alle diese Fehler treten vor Wait-Registrierung auf und verändern keinen Zustand. Device Loss eines bereits registrierten Waits ist ein terminaler Ausgang und wird als X11-Fehler `DEVICE_LOST` gemeldet; `DestroyDevice` beendet einen noch offenen Wait mit `DEVICE_DESTROYED`, sofern nicht zuvor Device Loss terminal festgestellt wurde. `TIMEOUT` ist ausschließlich ein normaler Reply-Status.
- `GetFenceStatus`: normative Präzedenz: exakt 16 Byte (`BadLength`); Device- und danach Fence-XID auflösen (`BadValue`); live Typen, Ownership und Device-Zuordnung prüfen (`BadMatch`); gespeicherten Fence-Zustand atomar abfragen. Device Loss ist für diese reine Zustandsabfrage kein Fehler.
- `ResetFence`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Fence-XIDs `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Verwendung `BadMatch`; nach gültigen XIDs/Typ/Ownership hat `DEVICE_LOST` Vorrang vor dem Fence-Zustand; nur bei verfügbarem Device dürfen ausschließlich `SIGNALED` und `FAILED` zurückgesetzt werden, andere Zustände ergeben `INVALID_SYNCHRONIZATION_STATE`.
- `DestroyFence`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Fence-XID `BadValue`; falscher live Typ, fremde Client-Ownership oder Cross-Device-Verwendung `BadMatch`; `INVALID_SYNCHRONIZATION_STATE`, solange die Fence `PENDING` ist oder eine offene `WaitForFence`-Registrierung genau diese interne Fence-Identität referenziert. Eine bereits terminal festgestellte Wait-Registrierung blockiert die Zerstörung nicht, auch wenn der Reply noch nicht gesendet wurde. Jede Ablehnung lässt XID und Fence-Zustand unverändert.
- `DestroySemaphore`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Semaphore-XID `BadValue`; falscher live Typ, fremde Client-Ownership oder Cross-Device-Verwendung `BadMatch`; `INVALID_SYNCHRONIZATION_STATE`, solange ein angenommener Queue-Wait, Queue-Signal, eine offene `WaitSemaphores`-Registrierung für genau diese interne Semaphore-Identität oder eine andere laufende Host-Operation die Semaphore verwendet. Eine bereits terminal festgestellte Wait-Registrierung blockiert die Zerstörung nicht, auch wenn der Reply noch nicht gesendet wurde. Jede Ablehnung lässt XID und Synchronisationszustand unverändert. Device Loss allein invalidiert keine öffentlichen XIDs; wenn anschließend `DestroyDevice` verarbeitet wird, darf dessen Kaskadeninvalidierung diese normalen Ablehnungen umgehen.
- Die verbindliche XID-Zuordnung steht im Abschnitt „Verbindliche XID-Fehlerregel“: unbekannte/nicht-live XAverius-XIDs ergeben `BadValue`, falsche live Ressourcentypen `BadMatch`, ungültige Atoms `BadAtom`.

### Memory allocation and binding

- `GetBufferMemoryRequirements`: falsche Request-Länge `BadLength`; unbekannte/nicht-live Device- oder Buffer-XID `BadValue`; falscher live Ressourcentyp oder Buffer eines anderen Devices `BadMatch`.
- `AllocateMemory`: falsche Request-Länge `BadLength`; nicht-positive Allokationsgröße, reserviertes Feld ungleich null oder nicht existierender Memory-Type-Index `BadValue`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Backend-Allokationsfehler `ALLOCATION_FAILED`. Bei jedem Fehler bleibt die angeforderte `memory_xid` unangelegt.
- `FreeMemory`: falsche Request-Länge `BadLength`; unbekannte/nicht-live Device- oder Memory-XID `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Nutzung `BadMatch`; irgendein intern noch lebender, gebundener Buffer `BadMatch` (auch bei bereits invalidierter Buffer-XID); angenommene GPU-Arbeit mit Zugriff auf die Allokation `INVALID_SYNCHRONIZATION_STATE`. Bei Ablehnung bleibt die Allokation unverändert.
- `BindBufferMemory`: falsche Request-Länge `BadLength`; unbekannte/nicht-live Device-, Buffer- oder Memory-XID `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Nutzung `BadMatch`; inkompatibler Memory-Type, bereits gebundener Buffer, ungültiges Alignment oder unzureichende Allokationsgrenzen `BadMatch`. Bei Ablehnung bleibt der Buffer ungebunden.

### `BindBufferMemory`

The complete XID, ownership, field-value, and Device error mapping is defined in the unified table above. Cross-Device use, an already-bound Buffer, invalid alignment, insufficient allocation size, or an incompatible memory type results in `BadMatch`.

### `UpdateDescriptorSets`

The complete XID, ownership, field-value, and Device error mapping is defined in the unified table above. The request is atomic on every error.

Jeder Request muss vor Implementierungsfreigabe eine vollständige, konkrete Fehlerzuordnung besitzen.

### Presentation requests (presentation-capable profile)

These rules apply to the presentation-capable profile only. The central request registry assigns `CreateSurface` through `QueuePresent` append-only subopcodes 41–47. This assignment does not make the presentation profile part of the compute-only v0.1 baseline; a compute-only server rejects these requests with core `BadRequest` before payload parsing or XID resolution.

- All presentation requests validate the exact fixed or formula-based request length first; a mismatch or overflow in `40 + 4 * wait_semaphore_count` is `BadLength`. Non-zero reserved fields, invalid enum/flag values, zero presentation tokens, duplicate wait semaphore XIDs, and malformed count/field combinations are `BadValue`. Reuse of a token from an already accepted presentation is a stateful acceptance check, not scalar syntax.
- `CreateSurface`: invalid/already allocated target `surface_xid` is `BadIDChoice`; an unknown, destroyed, or non-Window core X11 `window_xid` is core X11 `BadWindow`; a live Window owned by another X11 client is `BadMatch`. A failed create leaves the target XID unallocated and retains no window reference.
- `DestroySurface`: unknown/non-live Surface XID is `BadValue`; a live XID of another type or a Surface owned by another connection is `BadMatch`; any live Swapchain still referencing the Surface causes atomic rejection with `INVALID_SYNCHRONIZATION_STATE`. The only request-level lifetime blocker is a live Swapchain reference. Internal Window-identity tombstones and already-retained backend/notification references do not by themselves block destruction; after successful public invalidation they remain retained internally until quiescent. The checks and public invalidation are serialized atomically against Window lifecycle notifications and connection teardown: Window destruction first leaves the Surface `SURFACE_LOST`, which remains explicitly destroyable once no live Swapchain references it; successful `DestroySurface` first invalidates the public XID so later notifications cannot affect a reused XID. A rejected destroy leaves the Surface and its references unchanged.
- `GetSurfaceCapabilities`: unknown/non-live Device or Surface XID is `BadValue`; a live wrong type or foreign connection ownership is `BadMatch`. A Surface is not Device-owned, so querying the same live Surface with different owned Devices is valid; the reply reports each Device/Surface pair's support independently and does not migrate resources. `SUCCESS`, `TEMPORARILY_NOT_PRESENTABLE`, `SURFACE_LOST`, and `DEVICE_LOST` are normal reply statuses, not X11 errors. Status-dependent zero fields and the reply-length formula remain mandatory.
- `CreateSwapchain`: invalid/already allocated target `swapchain_xid` is `BadIDChoice`; unknown/non-live Device or Surface XID is `BadValue`; wrong live type, foreign ownership, or cross-device combination is `BadMatch`; zero image count or dimensions, unknown format/color-space/present-mode identifiers, unassigned usage bits, or non-zero reserved fields are `BadValue`. A syntactically valid but unsupported configuration returns `UNSUPPORTED_CONFIGURATION`; a zero-sized Surface or requested extent outside current bounds returns `OUT_OF_DATE`, except that a requested width or height of zero is rejected earlier as `BadValue` during scalar validation. `SURFACE_LOST`, `DEVICE_LOST`, and `ALLOCATION_FAILED` are normal reply statuses. On every non-success status the target XID remains unallocated. After wire-length and scalar-field validation, XID validation follows request field order: resolve `device_xid`, validate the target `swapchain_xid` as a create-XID, then resolve `surface_xid`. Capability/status checks occur only after these XID, type, ownership, and Device-state checks.
- `DestroySwapchain`: unknown/non-live Swapchain XID is `BadValue`; a live wrong type or foreign ownership is `BadMatch`; a recording command buffer, pending acquire registration, accepted queue work, accepted presentation, or possible backend access causes atomic rejection with `INVALID_SYNCHRONIZATION_STATE`; non-pending executable command buffers referencing the Swapchain are invalidated atomically on successful destruction. An acquired-but-idle image alone does not block destruction.
- `AcquireNextImage`: unknown/non-live Device or Swapchain XID is `BadValue`; wrong live type, foreign ownership, or cross-device use is `BadMatch`; a supplied semaphore/fence with wrong type, ownership, or device is `BadMatch`; an ineligible semaphore/fence state or conflicting pending acquisition is `INVALID_SYNCHRONIZATION_STATE`. `TIMEOUT`, `NOT_READY`, `OUT_OF_DATE`, `SURFACE_LOST`, `DEVICE_LOST`, and `DEVICE_DESTROYED` are normal reply statuses and must not signal either synchronization object or change image state. `DestroyDevice` terminalizes any still-open acquire with `DEVICE_DESTROYED`; a previously serialized terminal result wins.
- `QueuePresent`: unknown/non-live Device, Swapchain, or wait-semaphore XID is `BadValue`; wrong live type, foreign ownership, or cross-device use between the Device, Swapchain, and wait semaphores is `BadMatch`; nonexistent queue-family/index or image index outside the Swapchain is `BadValue`; a valid queue family whose capability record has `present_supported = 0` for the target Surface is `BadMatch`; an image not in `ACQUIRED`, or a wait semaphore that cannot be legally consumed because of an incompatible pending wait/state, is `INVALID_SYNCHRONIZATION_STATE`; a wait semaphore already marked `UNTRUSTED` is rejected with `DEPENDENCY_FAILED`. A zero token, duplicate wait XID, or reuse of a token reserved by an earlier accepted presentation is `BadValue`. `OUT_OF_DATE`, `SURFACE_LOST`, and `DEVICE_LOST` are normal reply statuses with the precedence defined below. Any rejected `QueuePresent` leaves the image state as it was immediately before that request, leaves wait-semaphore state unchanged, and does not reserve its presentation token. If an independent Device-loss transition has already invalidated the image, rejection does not restore it to `ACQUIRED`. Token uniqueness is checked against previously accepted presentations and recorded atomically with acceptance.
- For all seven requests, validation is atomic: no partial object, reference, image-state, synchronization-state, or token change attributable to the request may remain after a synchronous error or a non-success status. Independent asynchronous lifecycle transitions (especially Device loss) still take effect and are not rolled back by a rejected request. An accepted `QueuePresent` cannot later produce an X11 request error; its terminal result is reported through the presentation events and image/Swapchain state.

### Normative validation precedence for the seven presentation requests

The following order is normative and applies before any externally visible state change. It supplements the request-specific error mapping above; a later stage MUST NOT run before an earlier stage has succeeded.

1. Validate exact/fixed or formula-derived wire length using checked wide arithmetic. A length mismatch or arithmetic overflow is `BadLength`.
2. Validate scalar syntax and reserved fields, including nonzero `presentation_token`, legal `wait_semaphore_count`, unique wait-semaphore XIDs, and create-request scalar values. Invalid scalar syntax is `BadValue`. For variable `QueuePresent`, compute `40 + 4 * wait_semaphore_count` with checked arithmetic before reading the wait array. Do not test whether a nonzero presentation token was previously accepted at this stage; that depends on mutable server state.
3. Resolve request XIDs in wire-field order. For create requests, validate the target XID at its defined create-XID position; `CreateSurface` checks `surface_xid` before resolving `window_xid`, while `CreateSwapchain` checks `device_xid`, then target `swapchain_xid`, then `surface_xid`. Unknown/non-live XAverius resource XIDs are `BadValue`; an unknown, destroyed, or non-Window core X11 `window_xid` is `BadWindow`.
4. Validate live resource types, connection ownership, Device ownership, and cross-device relationships. A live wrong type or ownership mismatch is `BadMatch`. For `CreateSurface`, a live Window belonging to another X11 client is `BadMatch`.
5. For requests with a Device, check Device availability after valid XIDs/types/ownership. If the reply has a defined `DEVICE_LOST` status (`GetSurfaceCapabilities`, `CreateSwapchain`, `AcquireNextImage`, `QueuePresent`), return that status; otherwise use the request's established Device error. Device loss takes precedence over Surface loss and all later mutable-state checks.
6. Validate request-specific indices and immutable constraints: queue-family/index existence, image-index bounds, and syntactic format/mode/usage identifiers. Failures use the request-specific X11 error mapping. A valid but unsupported configuration is not a syntax error and is handled by the normal status rules below.
7. Resolve lifecycle/capability outcomes before mutable image/semaphore eligibility: `GetSurfaceCapabilities` returns `SURFACE_LOST` for a lost Surface; `CreateSwapchain` returns `SURFACE_LOST` for a lost Surface and `OUT_OF_DATE` for a zero-sized Surface or a requested extent outside current bounds; `AcquireNextImage` returns `SURFACE_LOST` or `OUT_OF_DATE` before evaluating availability/timeout; `QueuePresent` returns `SURFACE_LOST` before `OUT_OF_DATE`. A valid `QueuePresent` queue-family tuple with no presentation support is `BadMatch` before the image-state check. A valid but unsupported swapchain configuration returns `UNSUPPORTED_CONFIGURATION` only after the higher-priority lifecycle statuses have been ruled out.
8. Validate mutable state and synchronization eligibility, then commit all state changes atomically. For `QueuePresent`, after higher-priority XID, Device, queue/index, lifecycle, and presentation-support checks, reject reuse of a token from an earlier accepted presentation with `BadValue`; then check image state, and if it is `ACQUIRED`, validate wait semaphores in array order. For each wait, `UNTRUSTED` yields `DEPENDENCY_FAILED`; another incompatible state or pending-wait conflict yields `INVALID_SYNCHRONIZATION_STATE`. A state failure leaves all object/image/semaphore state, references, and token reservations unchanged by that request; it does not roll back an independent asynchronous lifecycle transition. On successful `QueuePresent` acceptance, reserve the token and all semaphore wait slots and transition the image to `PRESENT_PENDING` as one indivisible commit.

For a new `AcquireNextImage` evaluation, after the preceding validation stages, `DEVICE_LOST` takes precedence over `SURFACE_LOST`, which takes precedence over `OUT_OF_DATE`; these outcomes precede mutable synchronization-state checks and timeout polling. Once lifecycle checks pass, validate every supplied semaphore/fence for acquisition-signal eligibility and absence of a conflicting pending acquire before polling or registering the wait; an ineligible object or conflicting registration returns `INVALID_SYNCHRONIZATION_STATE` even if no image is available or the timeout is zero. Only a usable swapchain with eligible synchronization objects reaches the timeout decision. A zero timeout then returns `NOT_READY` if no image is immediately available; a finite timeout returns `TIMEOUT` only when it expires. `DEVICE_DESTROYED` applies only when `DestroyDevice` terminalizes an already-pending acquire registration; the first terminal result serialized by the server wins, and `DestroyDevice` cannot overwrite an earlier terminal result.

For `QueuePresent`, status replies (`OUT_OF_DATE`, `SURFACE_LOST`, `DEVICE_LOST`) and synchronous X11 errors are pre-acceptance outcomes: the rejected request itself consumes no semaphore, reserves no token, and makes no image-state change. The image remains in its pre-request state; a separate lifecycle transition such as Device loss may already have invalidated it. Token reuse is a `BadValue` only if that token belongs to a previously accepted presentation; a token used only by a rejected attempt remains available. A zero token is always `BadValue`.

## Synchronous versus Asynchronous Errors

An error before acceptance is reported by an X11 error or the explicitly defined normal error reply. The request MUST NOT leave partial state.

An error after acceptance is reported through XAverius events and synchronization state. A delayed X11 error for an already accepted request is prohibited.
