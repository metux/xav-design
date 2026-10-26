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

## Normative State Transitions

The following transitions are normative:

- Successful creation: public view is `LIVE`; internal state is `ACTIVE`.
- Rejected destroy request: no change to public state, internal state, dependent command-buffer states, or ownership.
- Successful ordinary destruction: the public view becomes `INVALID` in the same request. If no internal references or backend accesses remain, the object may transition directly to `RELEASED`; otherwise it transitions to `DESTROY_PENDING`.
- `DESTROY_PENDING` → `RELEASED`: only after all internal references are released, no backend access remains possible, and backend destruction has completed.
- Device-wide cascading invalidation on successful `DestroyDevice` or client disconnect: all associated public XIDs become `INVALID`. Objects with remaining internal references or backend accesses remain `DESTROY_PENDING`; other objects may become `RELEASED`. Device loss alone does not invalidate public XIDs: the lost logical device and its resources remain addressable until explicitly destroyed, where the relevant request contracts permit status queries or logical cleanup. In particular, `GetFenceStatus` and `DestroyDevice` remain usable after device loss. For accepted presentations, internal terminal states and safe backend cleanup MUST complete even when lifecycle rules suppress delivery of presentation events. An open `AcquireNextImage` request is terminalized with `DEVICE_DESTROYED` by `DestroyDevice`, unless its result was already terminally serialized; on disconnect, the registration is removed without a reply.

An object in `DESTROY_PENDING` cannot be addressed or destroyed again using its old XID. A reused XID identifies a new internal resource identity and MUST NOT inherit references to the old object. `RELEASED` is terminal.

Internal references are tracked separately for recorded command buffers, accepted submissions, buffer handles in descriptor slots, parent-child ownership, and active server operations. Removing a public XID does not automatically remove references held by an accepted submission. On successful ordinary destruction, all required command-buffer invalidations and internal reference updates MUST occur atomically with public invalidation.

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
- Pipeline ↔ Pipeline Layout
- Pipeline ↔ Shader Module während der Erstellung
- Pipeline Layout ↔ Descriptor Set Layout während der Erstellung
- Command buffer ↔ resources used by recorded commands

The implementation MUST NOT assume that every object whose handle was used to create another object must remain alive indefinitely. The applicable Vulkan lifetime rules determine the required lifetime.

## Destruction Matrix

| Resource | Public Destruction | Rule for Pending Use |
|---|---|---|
| Device | Invalidates device and children immediately | Internal cleanup is deferred |
| CommandPool | Atomically invalidates the pool and child command buffers | Reject while any child is pending |
| CommandBuffer | XID becomes invalid | Reject while pending |
| DescriptorPool | Atomically invalidates the pool and all child sets | Reject if any child set is pending or referenced by a `RECORDING` command buffer |
| DescriptorSet | XID becomes invalid | Reject while pending or referenced by a `RECORDING` command buffer; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |
| Buffer | XID becomes invalid | Reject while referenced by a `RECORDING` command buffer or used directly/indirectly by accepted work; on successful destruction, non-pending `EXECUTABLE` command buffers with this reference become `INVALID`. Defer internal release while server operations or descriptor slots still reference the object |
| Memory | Invalidated only after successful validation | Reject `FreeMemory` while any buffer remains bound to it or accepted work uses the allocation |
| Pipeline | XID becomes invalid | Reject while referenced by a `RECORDING` command buffer or used by accepted work; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |
| PipelineLayout | XID becomes invalid | Reject while referenced by a `RECORDING` command buffer or used by accepted work; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |
| ShaderModule | May be destroyed independently after successful pipeline creation | Vulkan lifetime rules remain authoritative |
| DescriptorSetLayout | May be destroyed independently after successful pipeline-layout creation | Vulkan lifetime rules remain authoritative |
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
- Pipeline and pipeline layout: references from a `RECORDING` command buffer prevent destruction; pending use also prevents it. On successful destruction, non-pending `EXECUTABLE` command buffers with matching references become `INVALID`.
- Shader Module und Descriptor Set Layout: Nach Ende ihrer erforderlichen Erstellungs-/Pipeline-Layout-Abhängigkeit gelten die jeweiligen Vulkan-Lebensdauerregeln.

Jede Ablehnung ist atomar und lässt die öffentliche XID, interne Lebensdauerzustände und abhängige Command-Buffer-Zustände unverändert. Bei Erfolg wird die öffentliche XID im Request sofort ungültig; interne Objekte bleiben bis zum Ende aller erforderlichen Referenzen und Backend-Zugriffe erhalten. Die Device-weite Kaskadeninvalidierung bei `DestroyDevice` oder Client-Disconnect bleibt davon unberührt. Device Loss allein invalidiert keine öffentlichen XIDs; er terminalisiert angenommene Arbeit und verändert die betroffenen Ressourcen- und Synchronisationszustände gemäß den nachfolgenden Regeln.

## Dedicated destruction requests

`DestroyDevice`, `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets` und `FreeMemory` bleiben eigene Requests, weil sie eigene Ownership-, Kaskaden- oder Speicherfreigaberegeln besitzen. `DestroyFence` und `DestroySemaphore` sind ebenfalls dedizierte Requests; sie sind ausdrücklich **nicht** über `DestroyResource` aufrufbar. Das verhindert zwei Wire-Pfade mit unterschiedlichen Zustandsprüfungen für dasselbe Synchronisationsobjekt.

`FreeMemory` invalidiert die Memory-XID nur bei Erfolg. Gebundene Buffer führen zu `BadMatch`; angenommene GPU-Arbeit, die auf die Allokation zugreift, führt zu `INVALID_SYNCHRONIZATION_STATE`. XAverius v0.1 kennt kein Unbind/Rebind, daher müssen alle gebundenen Buffer zuerst zerstört werden.

## Device Destruction and Client Disconnect

Bei erfolgreichem `DestroyDevice` oder Client-Disconnect werden die öffentlichen XIDs des logischen Devices und seiner Ressourcen ungültig; danach sind sie für neue Requests nicht mehr adressierbar. Die Kaskadeninvalidierung darf nicht an normalen Pending-Use-Ablehnungen scheitern. Sie ändert aber nicht rückwirkend bereits angenommene Arbeit: Bei normalem Teardown muss diese Arbeit ihren tatsächlichen terminalen Ausgang erreichen, und interne Vulkan-Objekte bleiben bis zum Ende aller Backend-Zugriffe erhalten.

A client disconnect ends event delivery for that X11 connection only. The server MUST mark the connection as unable to receive events and remove its event selections and public XID mappings from active connection state. Asynchronous backend completions MUST NOT enqueue events to a closed connection or deliver them through another connection. Event associations MUST be bound to the specific X11 connection and internal resource identity, not only to a numeric XID. For `ASYNC_ERROR`, a resource XID that has since been destroyed or reused MUST NOT be emitted as `resource_xid`; if the public resource XID is no longer live at the linearization point, `resource_xid = 0` is serialized. The server MUST NOT resolve an XID again from the current table to construct a delayed event. Accepted work still reaches its actual internal terminal outcome; disconnect neither requires successful completion nor indefinite waiting for GPU progress. Resources that the backend may still access remain alive until those accesses are proven to have ended, or are handled under the Device-Loss-Regeln quarantänisiert.

**Identität asynchroner Abschlüsse:** Jeder beim Backend registrierte Callback oder Completion-Datensatz muss die unveränderliche interne Identität der konkreten Submission beziehungsweise Ressource und die Identität der ursprünglichen X11-Verbindung mitführen. Beim Abschluss darf der Server die Zielressource nicht anhand einer numerischen XID erneut aus der aktuellen XID-Tabelle auflösen. Vor einer Event-Einreihung muss er prüfen, dass genau die ursprüngliche Verbindung noch aktiv und zustellbar ist und dass die Lifecycle-Regeln der mitgeführten internen Device-Identität die Zustellung noch erlauben. Eine geschlossene Verbindung, eine zerstörte Device-Identität oder eine inzwischen wiederverwendete XID darf niemals auf ein neues Objekt oder eine andere Verbindung umgebogen werden. Das Verwerfen einer unzustellbaren Completion betrifft nur die Zustellung; interne Submission-, Fence-/Semaphore- und Backend-Aufräumzustände müssen trotzdem genau einmal terminalisiert werden.

Offene serverseitige Host-Waits der getrennten Verbindung werden abgebrochen und aus den Wait-Registrierungen entfernt; da die Verbindung geschlossen ist, wird dafür kein Reply erzeugt. Das Abbrechen eines Host-Waits bricht keine bereits angenommene GPU-Submission ab und verändert weder deren terminalen Ausgang noch Semaphore-/Fence-Zustände. Referenzen, die ausschließlich der abgebrochenen Wait-Registrierung dienten, werden freigegeben, sobald der Abbruch atomar feststeht; Referenzen laufender Backend-Operationen bleiben nach den normalen Lebensdauerregeln bestehen.

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

`FreeDescriptorSets` folgt denselben Regeln für die ausgewählten Sets: pending Verwendung oder Referenz durch einen `RECORDING`-Command-Buffer führt zur atomaren Ablehnung. Bei Erfolg werden die ausgewählten Sets invalidiert und nicht-pending `EXECUTABLE`-Command-Buffer, die sie referenzieren, `INVALID`. Die logische Freigabe bleibt auch nach Device Loss zulässig, sofern die Pending-/Recording-Regeln erfüllt sind; interne Backend-Referenzen bleiben bis zur sicheren Quieszenz erhalten. Ein Set darf nicht gleichzeitig über einen expliziten Free-Request und die Pool-Kaskade freigegeben werden; eine bereits invalidierte Set-XID ist für weitere Free-Requests ungültig.

## Pipelines and Synchronization Objects

`DestroyResource` auf eine Pipeline oder ein Pipeline Layout wird abgewiesen, solange eine angenommene Submission die jeweilige Ressource verwendet. Ohne Pending-Use gelten die allgemeinen Regeln für aufgezeichnete Referenzen: Referenzen aus `RECORDING`-Command-Buffer verhindern die Zerstörung; referenzierende nicht-pending `EXECUTABLE`-Command-Buffer werden bei erfolgreicher Zerstörung `INVALID`.

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
