# Resource lifetime and ownership

## Client Resources

Client-created XAverius resources use valid XIDs allocatable by the client.

An invalid or already-occupied create XID results in `BadIDChoice`, unless the request defines a more specific X11 rule.

The server MUST maintain an internal identity for each resource that is distinct from its public XID. Reuse of the same XID MUST never redirect in-flight work to a new resource.

A successfully destroyed public resource is no longer addressable by new requests.

# Resource Lifetime and Destruction

## State Model

Each object has at least two distinct lifetime views:

**Public State**

- `LIVE`
- `INVALID`

**Internal State**

- `ACTIVE`
- `DESTROY_PENDING`
- `RELEASED`

The implementation SHOULD also track internal resource identity, client and device ownership, dependent objects, and outstanding submission references.

The public XID becomes invalid immediately when destruction succeeds. Actual Vulkan object destruction may be deferred.

### `DestroyDevice` cascade linearization

A successful `DestroyDevice` has one server-side linearization point. At that point, as one indivisible public-state transition, the server MUST mark the Device and every public resource owned by that exact internal Device identity invalid, remove its Device/Queue event selections, and terminalize every still-open host wait that has not already reached a terminal result. For `WaitSemaphores`, a `WAIT_ALL` registration with only partial counter satisfaction is still open and is terminalized with `DEVICE_DESTROYED`; only the complete selected predicate committed as satisfied is a prior success. A wait whose success, timeout, or Device-loss result was established first keeps that result; otherwise the processed destroy yields `DEVICE_DESTROYED`. A wait reply or error already serialized before this point remains unchanged.

A `WriteBuffer` operation that has passed synchronous validation but has not committed its successful completion is an active server operation associated with the exact internal Device, Buffer, and Memory identities. `DestroyDevice` MUST serialize against that operation at the same lifecycle boundary. If destruction wins while the write is still open, the write is terminalized with the X11 error `DEVICE_DESTROYED`; it MUST NOT begin a transfer or publish a successful reply afterward. If a backend transfer has already started, the server MUST retain its references until the transfer can no longer access the destination, and MUST NOT claim that the destination is unchanged or that the upload succeeded. If the write's successful completion was committed before the destroy linearization point, that result remains successful. A later host signal MUST NOT execute against the destroyed Device identity.

Accepted submissions are not cancelled by public invalidation. Each still-nonterminal accepted submission MUST still acquire exactly one internal terminal outcome; a Device-loss outcome MUST NOT be replaced with success. Completion callbacks racing with the cascade MUST serialize against the same lifecycle state: callbacks may finish internal state and release references exactly once, but after the destroy linearization point they MUST NOT enqueue or deliver a new event for the destroyed Device. Events already queued in the X11 output stream before that point remain valid.

Every callback and deferred cleanup operation MUST be keyed by the immutable internal Device/resource/submission identity, never by a numeric XID lookup performed at callback time. If an XID is reused after cascading invalidation, a late callback MUST NOT mutate the new resource, satisfy a new wait, release its allocation, or deliver an event naming it. Internal references and backend allocations for the old identity remain retained or quarantined until backend access is known to be impossible; public invalidation and event suppression MUST NOT be treated as proof of quiescence.

## Normative State Transitions

The following transitions are normative:

- Successful creation: public view is `LIVE`; internal state is `ACTIVE`.
- Rejected destroy request: no change to public state, internal state, dependent command-buffer states, or ownership.
- Successful ordinary destruction: the public view becomes `INVALID` in the same request. If no internal references or backend accesses remain, the object may transition directly to `RELEASED`; otherwise it transitions to `DESTROY_PENDING`.
- `DESTROY_PENDING` → `RELEASED`: only after all internal references are released, no backend access remains possible, and backend destruction has completed.
- Device-wide cascading invalidation on successful `DestroyDevice` or client disconnect: all associated public XIDs become `INVALID`. Objects with remaining internal references or backend accesses remain `DESTROY_PENDING`; other objects may become `RELEASED`. Device loss alone does not invalidate public XIDs: the lost logical device and its resources remain addressable until explicitly destroyed, where the relevant request contracts permit status queries or logical cleanup. In particular, `GetFenceStatus` and `DestroyDevice` remain usable after device loss. For accepted presentations, internal terminal states and safe backend cleanup MUST complete even when lifecycle rules suppress delivery of presentation events. An open `AcquireNextImage` request is terminalized with `DEVICE_DESTROYED` by `DestroyDevice`, unless its result was already terminally serialized; on disconnect, the registration is removed without a reply.

An object in `DESTROY_PENDING` cannot be addressed or destroyed again using its old XID. A reused XID identifies a new internal resource identity and MUST NOT inherit references to the old object. `RELEASED` is terminal.

Internal references are tracked separately for recorded command buffers, accepted submissions, buffer handles in descriptor slots, DescriptorSet-to-DescriptorSetLayout associations, Pipeline-to-PipelineLayout dependencies, parent-child ownership, and active server operations. A DescriptorSet retains the immutable layout definition and the backend layout identity needed for descriptor validation and updates until that set is freed and all backend accesses have ended. Removing a public XID does not automatically remove references held by an accepted submission or a live dependent object. On successful ordinary destruction, all required command-buffer invalidations and internal reference updates MUST occur atomically with public invalidation.

## Ownership Hierarchy

Explicit parent-child relationships:

- X11 connection → surface (connection-bound surface; not a device child)
- Surface → exact internal identity of the referenced X11 window (the window is not owned; the reference MUST NOT be replaced by resolving the numeric XID again)
- Device → all public resources owned by the device, including swapchains
- Surface → dependent swapchains (reference relationship; surface destruction is rejected while swapchains remain live)
- CommandPool → associated command buffers
- DescriptorPool → associated descriptor sets

Other relationships are dependencies, not automatic ownership relationships:

- Buffer ↔ Memory
- Pipeline → Pipeline Layout (the Pipeline retains the internal layout identity needed for its lifetime)
- Pipeline ↔ Shader Module während der Erstellung
- Pipeline Layout ↔ Descriptor Set Layout während der Erstellung
- Descriptor Set → Descriptor Set Layout (retained layout definition/backend identity for the lifetime of the allocated set)
- Command buffer ↔ resources used by recorded commands

The implementation MUST NOT assume that every object whose handle was used to create another object must remain alive indefinitely. The applicable Vulkan lifetime rules determine the required lifetime.

## Destruction Matrix

| Resource | Public Destruction | Rule for Pending Use |
|---|---|---|
| Device | Invalidates device and children immediately | Internal cleanup is deferred |
| CommandPool | Atomically invalidates the pool and child command buffers | Reject while any child is pending |
| CommandBuffer | XID becomes invalid | Reject while pending |
| DescriptorPool | Atomically invalidates the pool and all child sets; non-pending `EXECUTABLE` command buffers referencing any child set become `INVALID` | Reject if any child set is pending or referenced by a `RECORDING` command buffer |
| DescriptorSet | XID becomes invalid | Reject while pending or referenced by a `RECORDING` command buffer; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |
| Buffer | XID becomes invalid | Reject while referenced by a `RECORDING` command buffer or used directly/indirectly by accepted work; on successful destruction, non-pending `EXECUTABLE` command buffers with this reference become `INVALID`. Defer internal release while server operations or descriptor slots still reference the object |
| Memory | Invalidated only after successful validation | Reject `FreeMemory` while any buffer remains bound to it or accepted work uses the allocation |
| Pipeline | XID becomes invalid | Reject while referenced by a `RECORDING` command buffer or used by accepted work; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |
| PipelineLayout | Public XID becomes invalid; retain its internal definition/backend identity while any live Pipeline depends on it | Reject while referenced by a `RECORDING` command buffer or directly used by accepted work; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID`. Existing Pipelines remain live; no new Pipeline may be created through the destroyed XID |
| ShaderModule | May be destroyed independently after successful pipeline creation | Vulkan lifetime rules remain authoritative |
| DescriptorSetLayout | Public XID may be destroyed once no further `CreatePipelineLayout` or `AllocateDescriptorSets` request needs it; the immutable layout definition and backend identity remain internally retained while any allocated DescriptorSet depends on them | Existing sets remain valid and updateable; no new PipelineLayout or Set may be created through the destroyed XID. Release the internal layout only after all dependent sets and backend accesses have ended |
| Fence | XID becomes invalid | Reject while the fence belongs to a non-terminal submission or an open `WaitForFence` registration references that exact internal fence identity; a wait already determined to be terminal does not block destruction merely because its reply is still pending |
| Semaphore | XID becomes invalid | Reject while an accepted queue wait/signal, an open `WaitSemaphores` registration for that exact internal semaphore identity, or another active server-side host operation uses the semaphore; a wait already determined to be terminal does not block destruction merely because its reply is still pending |
| Physical Device | Cannot be destroyed by a client | Server-owned; XID is never reassigned |
| Surface (presentation profile) | XID becomes invalid after successful `DestroySurface` or connection teardown; the internal window identity/reference is released only after surface, swapchain, and backend references have safely ended | Destruction is atomically rejected while a live swapchain references the surface; window destruction marks the still-addressable surface as `SURFACE_LOST` and causes neither implicit surface destruction nor rebinding when the XID is reused |
| Swapchain (presentation profile) | XID becomes invalid; image/backend storage may be released later | Destruction is rejected while recording command buffers, pending acquires, accepted queue/presentation work, or possible backend accesses reference the images; an acquired-but-idle image alone does not block destruction. Device destruction invalidates the XID and defers internal release until quiescence |

These rules are XAverius API decisions; they do not claim that Vulkan defines identical lifetime restrictions for all resource types.

## Recorded References and Command Buffer Invalidation

For each command buffer, the server tracks resources referenced directly or indirectly by its recorded commands. These include pipelines, pipeline layouts, descriptor sets, buffers, and buffers referenced through descriptor sets. These dependencies remain while the command buffer is recording or executable. A submission takes its own internal references, which remain until the submission reaches a terminal outcome and all backend accesses have ended. Invalidating an XID MUST never redirect a backend handle to another object.

- If a resource referenced by a `RECORDING` command buffer is destroyed, destruction is rejected with `INVALID_SYNCHRONIZATION_STATE`. The client must end recording or discard the command buffer before destroying the resource.
- If a resource referenced by an `EXECUTABLE` command buffer is destroyed, those command buffers transition to `INVALID` before the destroy request completes successfully. They MUST NOT be submitted afterward; recording them again is required.
- If the resource is still in use by an accepted submission, the resource-specific pending-use rule in the destruction matrix applies. A destroy request rejected due to pending use leaves the XID and command-buffer states unchanged.
- A destroy request is atomic: if the resource-specific rule rejects destruction, neither the public XID nor command-buffer states are changed.

This also applies to indirect dependencies through descriptor set → buffer or buffer → bound memory. The server MUST NOT treat an executable command buffer as valid if one of its recorded resource dependencies has been publicly destroyed.

## `DestroyResource`

`DestroyResource` is a generic void request with a fixed total length of 12 bytes:

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `resource_xid` |

The logical device and owner are determined from the addressed resource. The request may address only a live resource owned by the calling client. There is no additional `device_xid` field, so the request cannot reinterpret a resource belonging to another client or device.

In v0.1, `DestroyResource` is defined only for buffers, shader modules, descriptor set layouts, pipeline layouts, and pipelines.

The request is not valid for physical devices, logical devices, command pools, descriptor pools, command buffers, descriptor sets, memory, fences, or semaphores. These types have their own lifetime or cascading rules and must be handled through `DestroyDevice`, `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets`, `FreeMemory`, `DestroyFence`, or `DestroySemaphore`. `DestroyResource` on an excluded type is rejected with `BadMatch`. These exclusions are normative; implementations MUST NOT silently choose another destruction path.

Eligibility for the generic request does not replace type-specific lifetime checks:

- Buffer: the pending-use rules, command-buffer invalidation, and stale descriptor-slot rules described above apply.
- Pipeline: references from a `RECORDING` command buffer or accepted pending use prevent destruction. PipelineLayout: direct references from a `RECORDING` command buffer or direct accepted pending use prevent public XID destruction; a Pipeline-held internal dependency does not block public invalidation, but retains the backend layout until that Pipeline is destroyed. On successful public invalidation, non-pending `EXECUTABLE` command buffers with direct matching references become `INVALID`.
- Shader Module und Descriptor Set Layout: Nach Ende ihrer erforderlichen Erstellungs-/Pipeline-Layout-Abhängigkeit gelten die jeweiligen Vulkan-Lebensdauerregeln.

Jede Ablehnung ist atomar und lässt die öffentliche XID, interne Lebensdauerzustände und abhängige Command-Buffer-Zustände unverändert. Bei Erfolg wird die öffentliche XID im Request sofort ungültig; interne Objekte bleiben bis zum Ende aller erforderlichen Referenzen und Backend-Zugriffe erhalten. Die Device-weite Kaskadeninvalidierung bei `DestroyDevice` oder Client-Disconnect bleibt davon unberührt. Device Loss allein invalidiert keine öffentlichen XIDs; er terminalisiert angenommene Arbeit und verändert die betroffenen Ressourcen- und Synchronisationszustände gemäß den nachfolgenden Regeln.

## Dedicated destruction requests

`DestroyDevice`, `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets` und `FreeMemory` bleiben eigene Requests, weil sie eigene Ownership-, Kaskaden- oder Speicherfreigaberegeln besitzen. `DestroyFence` und `DestroySemaphore` sind ebenfalls dedizierte Requests; sie sind ausdrücklich **nicht** über `DestroyResource` aufrufbar. Das verhindert zwei Wire-Pfade mit unterschiedlichen Zustandsprüfungen für dasselbe Synchronisationsobjekt.

`FreeMemory` invalidiert die Memory-XID nur bei Erfolg. Gebundene Buffer führen zu `BadMatch`; angenommene GPU-Arbeit, die auf die Allokation zugreift, führt zu `INVALID_SYNCHRONIZATION_STATE`. XAverius v0.1 kennt kein Unbind/Rebind, daher müssen alle gebundenen Buffer zuerst zerstört werden.

## Device Destruction and Client Disconnect

Bei erfolgreichem `DestroyDevice` oder Client-Disconnect werden die öffentlichen XIDs des logischen Devices und seiner Ressourcen ungültig; danach sind sie für neue Requests nicht mehr adressierbar. Die Kaskadeninvalidierung darf nicht an normalen Pending-Use-Ablehnungen scheitern. Sie ändert aber nicht rückwirkend bereits angenommene Arbeit: Bei normalem Teardown muss diese Arbeit ihren tatsächlichen terminalen Ausgang erreichen, und interne Vulkan-Objekte bleiben bis zum Ende aller Backend-Zugriffe erhalten.

### Cross-resource teardown and backing-memory release

Device-wide cascading invalidation is a public-state operation, not an instruction to free children in arbitrary order. The server MUST retain the old internal identity graph while draining it. Descriptor-set slots, command-buffer recorded references, accepted submissions, active server operations, Buffer-to-Memory bindings, and parent-child references are distinct edges. The server MUST retire each edge exactly once through the operation that owns it. Invalidating a DescriptorSet XID does not by itself prove that its slot-held Buffer references or backend accesses have ended.

After successful `DestroyDevice`, no child XID remains addressable, so the client cannot perform per-resource cleanup to break remaining edges. The server MUST perform that internal teardown itself: stop new work, terminalize accepted submissions and open waits under the established lifecycle rules, invalidate command buffers and descriptor sets, retire descriptor-slot and recorded-command references, and then release buffers and their memory only after submission, active-operation, and backend-access references have drained. The implementation MAY use another safe internal order, but it MUST preserve every dependency until the dependent operation is finished and MUST NOT release a bound Memory allocation before the old Buffer identity and all possible accesses are safely retired.

The same identity rule applies to ordinary resource destruction: a publicly invalidated Buffer can remain internally live because a descriptor slot or other internal owner still references it. Its binding edge to Memory remains live for that entire interval. `FreeMemory` must reject while that internal Buffer remains bound; after device-wide invalidation, internal cleanup instead drains the edge without attempting a new public `FreeMemory` request. No delayed edge retirement may resolve an XID again, since the numeric XID may already identify a different resource.

A client disconnect ends event delivery for that X11 connection only. The server MUST mark the connection as unable to receive events and remove its event selections and public XID mappings from active connection state. Asynchronous backend completions MUST NOT enqueue events to a closed connection or deliver them through another connection. Event associations MUST be bound to the specific X11 connection and internal resource identity, not only to a numeric XID. For `ASYNC_ERROR`, a resource XID that has since been destroyed or reused MUST NOT be emitted as `resource_xid`; if the public resource XID is no longer live at the linearization point, `resource_xid = 0` is serialized. The server MUST NOT resolve an XID again from the current table to construct a delayed event. Accepted work still reaches its actual internal terminal outcome; disconnect neither requires successful completion nor indefinite waiting for GPU progress. Resources that the backend may still access remain alive until those accesses are proven to have ended, or are quarantined under the Device-loss rules.

**Identity of asynchronous completions:** Every backend callback or completion record MUST carry the immutable internal identity of the specific submission or resource and the identity of the original X11 connection. When a callback completes, the server MUST NOT resolve the target resource again from the current XID table using only a numeric XID. Before queueing an event, it MUST verify that the original connection remains active and able to receive events and that the lifecycle rules for the captured internal Device identity still permit delivery. A closed connection, destroyed Device identity, or reused XID MUST NOT be redirected to a new object or another connection. Discarding an undeliverable completion affects delivery only; internal submission, Fence/Semaphore, and backend cleanup states must still be terminalized exactly once.

Open server-side host waits belonging to a disconnected connection are cancelled and removed from wait registrations; no reply is generated because the connection is closed. Cancelling a host wait does not cancel an already accepted GPU submission and does not change its terminal outcome or Semaphore/Fence state. References used only by the cancelled wait registration are released once cancellation is established atomically; references held by active backend operations remain under the normal lifetime rules.

A `WriteBuffer` operation belonging to a disconnected connection is cancelled at the disconnect linearization point if successful completion has not already been committed. No reply or XGE event is generated for that operation, and no transfer that has not yet started may begin afterward. A transfer already in progress may continue only as needed to reach safe backend quiescence; its exact Device/Buffer/Memory references MUST remain held or quarantined until backend access is impossible. Disconnect does not convert the write into a successful upload and does not cancel earlier accepted GPU submissions. Any later callback is internal cleanup only and MUST NOT publish a reply, event, or state change into another connection or a reused XID.

Konkurrierende Wait-Abschlüsse werden anhand der serialisierten serverseitigen Zustandsübergänge entschieden. Für einen offenen Wait gewinnt der erste festgestellte terminale Ausgang: bereits festgestellte Erfüllung beziehungsweise ein bereits festgestellter Timeout bleibt bestehen; zuerst erkannter Device Loss beendet den Wait mit `DEVICE_LOST`; wird `DestroyDevice` verarbeitet, solange der Wait noch offen ist und Device Loss noch nicht festgestellt wurde, endet er mit `DEVICE_DESTROYED`. Der Disconnect entfernt den Wait ohne Reply. Ein späterer Übergang darf den bereits terminalen Wait nicht überschreiben.

After successful processing of `DestroyDevice`, the server MUST NOT generate or deliver new XAverius events whose `device_xid` identifies the destroyed logical Device. This includes `DEVICE_LOST`, `DEVICE_IDLE`, `DEVICE_MEMORY_PRESSURE`, `SUBMISSION_COMPLETE`, `SUBMISSION_FAILED`, and `ASYNC_ERROR`; for `ASYNC_ERROR`, the destroyed Device XID MUST NOT be emitted as `device_xid` or `resource_xid`. Events generated and queued in the X11 output stream before `DestroyDevice` was processed remain unaffected. Suppressing delivery does not change the internal terminal outcome of accepted submissions or the requirement to retain backend references until possible accesses have ended. Device and Queue event selections are removed during cascading invalidation.

Die interne Bereinigung muss sicher und unabhängig von der öffentlichen XID-Verfügbarkeit erfolgen. Der Server darf nicht unbegrenzt auf einem hängenden oder verlorenen Device warten. Wenn das Device verloren ist, gelten die folgenden Device-Loss-Regeln; der Server darf erfolgreiche GPU-Completion nicht vortäuschen.

## Device Loss and Terminal Cleanup

Wird ein logisches Device als verloren erkannt, gilt für alle darauf angenommenen, noch nicht terminalen Submissions:

- Jede Submission endet als fehlgeschlagen mit Status `DEVICE_LOST`; sie darf nicht als erfolgreich abgeschlossen gemeldet werden.
- Zugehörige Fences wechseln nach `FAILED`, nicht nach `SIGNALED`.
- Betroffene Command Buffer wechseln nach Ende ihrer Pending-Phase nach `INVALID` und sind nicht erneut einreichbar.
- Interne Ressourcenreferenzen bleiben so lange erhalten, wie der Backend-Treiber oder die Serverbereinigung noch auf sie zugreifen kann. Ihre Freigabe darf nicht von einer GPU-Completion abhängen, die nach Device Loss nicht mehr eintreten kann.

Individual resource-specific Destroy/Free requests are not categorically forbidden after Device loss: they may proceed when their ownership, recording, and lifetime checks are satisfied. Because affected submissions and open host waits are terminalized when Device loss is detected, they MUST NOT remain blockers solely because of their former pending state. `DestroyResource`, `DestroyFence`, `DestroySemaphore`, `DestroyCommandPool`, `DestroyDescriptorPool`, and `FreeDescriptorSets` remain logical cleanup paths under their respective rules; recording references continue to block destruction wherever the request rules require it. `FreeMemory` remains blocked while an internally live Buffer is bound or backend accesses to the allocation may still occur. A logical destroy may invalidate public XIDs but MUST NOT force premature release of internal backend objects.

Öffentliche Ressourcen-XIDs dürfen bei Device-Zerstörung oder der dazugehörigen Kaskadenbereinigung invalidiert werden, auch wenn normale Pending-Use-Zerstörungen sonst abgewiesen würden. Diese Sonderregel gilt nur für die Device-weite Bereinigung; sie hebt interne Referenzpflichten nicht auf und darf keine erfolgreiche Completion vortäuschen. Der Server muss den Backend-Zustand sicher abbauen und darf interne Ressourcen erst freigeben, wenn kein Backend-Zugriff mehr möglich ist.

Nach erkanntem Device Loss schlagen Requests, die weitere Vulkan-Arbeit erfordern, mit `DEVICE_LOST` fehl. Requests zur Statusabfrage und zur logischen Bereinigung dürfen weiterhin verarbeitet werden, soweit ihr jeweiliger Vertrag dies zulässt.

Kann der Server bei Device-Zerstörung oder Device Loss nicht bestätigen, dass das Backend keine Zugriffe auf interne Ressourcen mehr ausführt, gilt das Device als verloren und wird isoliert: alle noch nicht terminalen Submissions schlagen intern mit `DEVICE_LOST` fehl; öffentliche XIDs bleiben invalidiert. Wird der Device Loss festgestellt, solange das logische Device noch öffentlich live ist und die Lifecycle-Unterdrückung noch nicht greift, wird `DEVICE_LOST` mit `reason_code = DRIVER_FAILURE` gemeldet, wenn der Auslöser ein Backend-/Treiberfehler ist, andernfalls mit dem passenden bestehenden Reason-Code. Wird der Verlust dagegen erst während oder nach der Verarbeitung von `DestroyDevice` festgestellt, wird kein neues Event für die bereits zerstörte `device_xid` erzeugt oder zugestellt; die internen Fehler- und Submission-Zustände werden dennoch korrekt terminalisiert. Diese Regel folgt der allgemeinen Lifecycle-Grenze und verhindert, dass die Pflicht zur Meldung von Device Loss die explizite Event-Unterdrückung nach `DestroyDevice` aushebelt. Interne Ressourcen und zugehörige Speicher werden in Quarantäne gehalten und weder freigegeben noch für neue Ressourcen wiederverwendet, bis das Backend nachweislich quieszent ist. Kann dieser Zustand nicht mehr sicher hergestellt werden, bleiben sie bis zum Ende des Serverprozesses quarantänisiert. Der Server darf weder auf unbestimmte Zeit auf GPU-Completion warten noch durch vorzeitiges Freigeben einen Use-after-free riskieren.

## Descriptor Pools and Sets

`DestroyDescriptorPool` ist atomar. Der Request wird abgewiesen, wenn ein enthaltenes Set pending verwendet wird oder von einem `RECORDING`-Command-Buffer referenziert wird. Bei Ablehnung bleiben Pool, Sets und Command-Buffer-Zustände unverändert. Andernfalls werden der Pool und alle enthaltenen Sets öffentlich invalidiert; nicht-pending `EXECUTABLE`-Command-Buffer, die eines dieser Sets referenzieren, werden `INVALID`.

`FreeDescriptorSets` folgt denselben Regeln für die ausgewählten Sets: wiederholte Set-XIDs innerhalb eines Requests werden mit `BadValue` vor jeder Zustandsänderung abgewiesen; pending Verwendung oder Referenz durch einen `RECORDING`-Command-Buffer führt zur atomaren Ablehnung. Bei Erfolg werden die ausgewählten Sets invalidiert und nicht-pending `EXECUTABLE`-Command-Buffer, die sie referenzieren, `INVALID`. Die logische Freigabe bleibt auch nach Device Loss zulässig, sofern die Pending-/Recording-Regeln erfüllt sind; interne Backend-Referenzen bleiben bis zur sicheren Quieszenz erhalten. Ein Set darf nicht gleichzeitig über einen expliziten Free-Request und die Pool-Kaskade freigegeben werden; eine bereits invalidierte Set-XID ist für weitere Free-Requests ungültig.

## Pipelines and Synchronization Objects

`DestroyResource` auf eine Pipeline oder ein Pipeline Layout wird abgewiesen, solange eine angenommene Submission die jeweilige Ressource direkt verwendet. Ohne Pending-Use gelten die allgemeinen Regeln für aufgezeichnete Referenzen: Referenzen aus `RECORDING`-Command-Buffer verhindern die öffentliche Zerstörung; referenzierende nicht-pending `EXECUTABLE`-Command-Buffer werden bei erfolgreicher Zerstörung `INVALID`. Ein live Pipeline-Objekt hält zusätzlich die interne Pipeline-Layout-Identität, von der es erstellt wurde. Die öffentliche PipelineLayout-XID darf invalidiert werden, ohne die bestehende Pipeline zu invalidieren; die interne Layout-Ressource bleibt bis zur Zerstörung aller davon abhängigen Pipelines und bis zum Ende sämtlicher Backend-Zugriffe erhalten. Neue Pipelines können die zerstörte XID nicht mehr verwenden.

`DestroyFence` wird abgewiesen, solange die Fence einer nicht-terminalen Submission zugeordnet ist oder eine offene `WaitForFence`-Registrierung genau diese interne Fence-Identität referenziert. `DestroySemaphore` wird abgewiesen, solange ein angenommener Queue-Wait, ein Queue-Signal, eine offene `WaitSemaphores`-Registrierung für genau diese interne Semaphore-Identität oder eine andere laufende serverseitige Host-Operation die Semaphore verwendet. Ein Host-Wait ist nicht mehr offen, sobald sein terminales Ergebnis serverseitig serialisiert festgestellt wurde; ein noch nicht versendeter Reply blockiert die Zerstörung dann nicht. Diese Ablehnungen sind atomar und verwenden `INVALID_SYNCHRONIZATION_STATE`. Wenn nach Device Loss `DestroyDevice` verarbeitet wird, darf dessen Device-weite Kaskadeninvalidierung diese normalen Ablehnungen umgehen. Device Loss allein führt keine öffentliche Kaskadeninvalidierung aus; interne Referenzen bleiben bis zum Ende möglicher Backend-Zugriffe bestehen.

## Command Buffers and Descriptor Sets

Ein pending Command Buffer darf in v0.1 nicht verändert, zurückgesetzt, freigegeben oder erneut eingereicht werden.

Ein Descriptor Set darf nicht aktualisiert oder freigegeben werden, solange eine angenommene Submission es verwenden kann. Command buffers reference the Descriptor Set object; slot contents are read from the current set at later execution time and are not frozen during recording. A successful `UpdateDescriptorSets` therefore atomically replaces the affected slot contents and updates the derived internal Buffer references of every non-pending command buffer that references the set. An `EXECUTABLE` command buffer remains executable after the update alone; later destruction of an old resource that is no longer referenced MUST NOT invalidate it because of that removed dependency.

Update-after-bind und Update-unused-while-pending werden nicht angeboten.

## Buffers and Memory

`DestroyResource` auf einen Buffer wird abgewiesen, solange ein `RECORDING`-Command-Buffer den Buffer direkt oder indirekt (einschließlich über ein referenziertes Descriptor Set) referenziert oder eine angenommene Submission ihn direkt oder über einen Descriptor Set verwendet. Bei erfolgreicher Zerstörung werden alle nicht-pending `EXECUTABLE`-Command-Buffer, die den Buffer direkt oder indirekt referenzieren, vor Abschluss des Destroy-Requests gemäß der allgemeinen Regel `INVALID`. Descriptor Sets, die den Buffer enthalten, bleiben als Objekte bestehen, gelten aber als nicht submitbar, bis alle betroffenen Descriptor-Slots mit gültigen Buffer-Referenzen aktualisiert wurden oder die Sets freigegeben wurden. Neue Submissions mit solchen ungültigen Descriptor-Inhalten werden atomar abgewiesen.

`FreeMemory` wird abgewiesen, solange irgendein Buffer an die Allokation gebunden ist oder angenommene Arbeit auf die Allokation zugreift. XAverius v0.1 bietet kein Unbind/Rebind. Der Client muss daher alle gebundenen Buffer zuerst erfolgreich zerstören und erst danach den Memory-Block freigeben. Ein gebundener Buffer führt zu `BadMatch`; ausstehende GPU-Arbeit führt zu `INVALID_SYNCHRONIZATION_STATE`. Ein abgewiesener `FreeMemory`-Request invalidiert die Memory-XID nicht. Wenn ein zerstörter Buffer noch von Descriptor-Slots referenziert wird, bleibt sein internes Objekt bis zum Überschreiben dieser Slots oder zur Freigabe der Descriptor Sets erhalten; die Buffer-XID bleibt dabei ungültig. Seine interne Bindungsreferenz auf die Memory-Allokation bleibt während dieser gesamten Zeit bestehen. Dasselbe gilt, solange ein Backend-Zugriff oder eine andere interne Referenz den Buffer noch am Leben hält. `FreeMemory` muss deshalb auch dann mit `BadMatch` abgewiesen werden, wenn die öffentliche Buffer-XID bereits invalidiert wurde, der interne Buffer aber noch an diese Allokation gebunden ist.

## Errors for Invalid Lifetime Operations

- Unknown or destroyed XAverius XID: `BadValue`
- Wrong type or incompatible resource: normally `BadMatch`
- Falsches Device: `BadMatch`
- Destroying a pending command buffer or descriptor set: `INVALID_SYNCHRONIZATION_STATE`
- Invalid fence reset: `INVALID_SYNCHRONIZATION_STATE`
- Lost device: `DEVICE_LOST`, unless the request explicitly permits logical invalidation

Successful device-wide cascading invalidation is a special rule and is not blocked by normal pending-use rejections.


Presentation lifecycle rule: an accepted present has one serialized terminal status and one internal cleanup. A later resize, Surface loss, or Device loss cannot overwrite an already terminal status. If still pending and forced to fail by OUT_OF_DATE, SURFACE_LOST, or DEVICE_LOST, its image is invalidated and IMAGE_RELEASED is not emitted. PRESENTATION_FAILED permits IMAGE_RELEASED only after backend quiescence and confirmation that the Swapchain remains usable. Event suppression never skips internal cleanup.



### Command-buffer recorded references and deferred retirement

A command buffer owns a distinct set of recorded-resource reference edges while it is RECORDING or EXECUTABLE. Successful reset detaches its recorded entries and retires those edges exactly once; successful execution preserves them when the buffer returns to EXECUTABLE. Execution failure or device loss makes the buffer INVALID, but does not permit early destruction of objects retained by an accepted submission or potentially reachable by the backend. Submission references are independent from recorded references and are retired by submission cleanup only after the terminal outcome and backend quiescence requirements are satisfied.

The reset/invalidation cleanup paths MUST be idempotent with respect to edge ownership. If invalidation retires a command buffer's recorded edges, a later reset MUST NOT retire those same edges again. If invalidation only marks the buffer invalid while an internal edge is still required for backend safety, that edge remains explicitly owned/retained until the safe cleanup point; reset may retire only the command-buffer-owned recorded edge and MUST NOT release the separate submission/backend hold. Re-recording creates a fresh reference set tied to the current internal resource identities and MUST NOT inherit stale references from the previous recording. All delayed callbacks use immutable internal identities, not re-resolved XIDs.