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
- Command Buffer ↔ Ressourcen, die in aufgezeichneten Commands verwendet werden

The implementation MUST NOT assume that every object whose handle was used to create another object must remain alive indefinitely. The applicable Vulkan lifetime rules determine the required lifetime.

## Destruction Matrix

| Resource | Public Destruction | Rule for Pending Use |
|---|---|---|
| Device | Invalidates device and children immediately | Internal cleanup is deferred |
| CommandPool | Atomically invalidates the pool and child command buffers | Reject while any child is pending |
| CommandBuffer | XID becomes invalid | Reject while pending |
| DescriptorPool | Invalidiert Pool und alle Kind-Sets atomar | Abweisen, wenn ein Kind-Set pending ist oder ein Kind-Set von einem `RECORDING`-Command-Buffer referenziert wird |
| DescriptorSet | XID wird ungültig | Abweisen, solange pending oder von einem `RECORDING`-Command-Buffer referenziert; bei Erfolg werden referenzierende nicht-pending `EXECUTABLE`-Command-Buffer `INVALID` |
| Buffer | XID wird ungültig | Abweisen, solange ein `RECORDING`-Command-Buffer ihn referenziert oder angenommene Arbeit ihn direkt/indirekt verwendet; bei erfolgreichem Destroy werden nicht-pending `EXECUTABLE`-Command-Buffer mit dieser Referenz `INVALID`. Interne Freigabe verzögern, solange Serveroperationen oder Descriptor-Slots das Objekt noch referenzieren |
| Memory | Nur bei erfolgreicher Prüfung invalidiert | `FreeMemory` wird abgewiesen, solange irgendein Buffer daran gebunden ist oder angenommene Arbeit die Allokation verwendet |
| Pipeline | XID wird ungültig | Abweisen, solange ein `RECORDING`-Command-Buffer sie referenziert oder angenommene Arbeit sie verwendet; bei Erfolg werden referenzierende nicht-pending `EXECUTABLE`-Command-Buffer `INVALID` |
| PipelineLayout | XID wird ungültig | Abweisen, solange ein `RECORDING`-Command-Buffer es referenziert oder angenommene Arbeit es verwendet; bei Erfolg werden referenzierende nicht-pending `EXECUTABLE`-Command-Buffer `INVALID` |
| ShaderModule | Nach erfolgreicher Pipeline-Erstellung unabhängig zerstörbar | Vulkan-Lebensdauerregeln bleiben maßgeblich |
| DescriptorSetLayout | Nach erfolgreicher Pipeline-Layout-Erstellung unabhängig zerstörbar | Vulkan-Lebensdauerregeln bleiben maßgeblich |
| Fence | XID wird ungültig | Abweisen, solange die Fence einer nicht-terminalen Submission zugeordnet ist oder eine offene `WaitForFence`-Registrierung genau diese interne Fence-Identität referenziert; terminal festgestellte Waits blockieren nicht nur wegen eines noch ausstehenden Reply |
| Semaphore | XID wird ungültig | Abweisen, solange ein angenommener Queue-Wait/-Signal, eine offene `WaitSemaphores`-Registrierung für genau diese interne Semaphore-Identität oder eine andere laufende Server-Host-Operation die Semaphore verwendet; terminal festgestellte Waits blockieren nicht nur wegen eines noch ausstehenden Reply |
| Physical Device | Nicht durch Client zerstörbar | Server-Ownership; XID wird nie neu zugewiesen |
| Surface (presentation profile) | XID wird bei erfolgreichem `DestroySurface` oder Connection-Teardown ungültig; die interne Window-Identität/Referenz wird erst freigegeben, wenn Surface-, Swapchain- und Backend-Referenzen sicher beendet sind | Zerstörung wird atomar abgewiesen, solange eine live Swapchain darauf verweist; Window-Zerstörung markiert die weiterhin adressierbare Surface als `SURFACE_LOST` und erzeugt weder implizite Surface-Zerstörung noch Rebinding bei XID-Wiederverwendung |
| Swapchain (presentation profile) | XID wird ungültig; Image-/Backend-Speicher ggf. verzögert freigegeben | Zerstörung wird abgewiesen, solange Recording-Command-Buffer, pending Acquires, angenommene Queue-/Präsentationsarbeit oder mögliche Backend-Zugriffe die Images referenzieren; ein acquired-but-idle Image allein blockiert nicht. Device-Zerstörung invalidiert die XID und verzögert interne Freigabe bis Quieszenz |

Die Regeln sind XAverius-API-Entscheidungen und keine Behauptung, dass Vulkan für alle Ressourcentypen identische Lebensdauerbeschränkungen definiert.

## Recorded References and Command Buffer Invalidation

Der Server verfolgt für jeden Command Buffer die Ressourcen, auf die seine aufgezeichneten Commands direkt oder indirekt verweisen. Dazu gehören insbesondere Pipelines, Pipeline Layouts, Descriptor Sets, Buffer und die über Descriptor Sets referenzierten Buffer. Diese Abhängigkeiten bleiben bestehen, solange der Command Buffer aufgezeichnet oder ausführbar ist. Eine Submission übernimmt eigene interne Referenzen, die bis zum terminalen Submission-Ausgang und bis zum Ende aller Backend-Zugriffe bestehen bleiben. Ein XID-Invalidieren darf nie einen Backend-Handle auf ein anderes Objekt umleiten.

- Wird eine Ressource zerstört, auf die ein `RECORDING`-Command-Buffer verweist, wird die Zerstörung mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen. Der Client muss die Aufzeichnung beenden oder den Command Buffer verwerfen, bevor er die Ressource zerstört.
- Wird eine Ressource zerstört, auf die ein `EXECUTABLE`-Command-Buffer verweist, werden diese Command Buffer vor erfolgreichem Abschluss des Destroy-Requests in `INVALID` überführt. Sie dürfen danach nicht eingereicht werden; eine erneute Aufzeichnung ist erforderlich.
- Ist die Ressource in einer angenommenen Submission noch in Verwendung, gilt die ressourcenspezifische Pending-Regel aus der Zerstörungsmatrix. Ein Destroy-Request, der wegen Pending-Use abgewiesen wird, lässt XID und Command-Buffer-Zustände unverändert.
- Ein Destroy-Request ist atomar: Wenn die ressourcenspezifische Regel die Zerstörung ablehnt, werden weder die öffentliche XID invalidiert noch Command-Buffer-Zustände geändert.

Das gilt auch für indirekte Abhängigkeiten, die über Descriptor Set → Buffer oder Buffer → gebundenen Memory verlaufen. Der Server darf einen ausführbaren Command Buffer nicht als gültig behandeln, wenn eine seiner aufgezeichneten Ressourcenabhängigkeiten öffentlich zerstört wurde.

## `DestroyResource`

`DestroyResource` ist ein generischer Void-Request mit fester Gesamtlänge von 12 Bytes:

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `resource_xid` |

Das logische Device und der Eigentümer werden aus der adressierten Ressource ermittelt. Der Request darf nur eine live Ressource adressieren, die dem aufrufenden Client gehört. Es gibt kein zusätzliches `device_xid`-Feld; dadurch kann der Request keine Ressource eines anderen Clients oder Devices umdeuten.

In v0.1 ist `DestroyResource` ausschließlich für Buffer, Shader Module, Descriptor Set Layout, Pipeline Layout und Pipeline vorgesehen.

Der Request ist nicht für Physical Devices, logische Devices, Command Pools, Descriptor Pools, Command Buffers, Descriptor Sets, Memory, Fences oder Semaphores zulässig. Diese Typen besitzen eigene Lebensdauer- beziehungsweise Kaskadenregeln und müssen über `DestroyDevice`, `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets`, `FreeMemory`, `DestroyFence` oder `DestroySemaphore` behandelt werden. Ein `DestroyResource` auf einem ausgeschlossenen Typ wird mit `BadMatch` abgewiesen. Diese Ausschlüsse sind normativ; Implementierungen dürfen nicht stillschweigend einen anderen Destroy-Pfad wählen.

Die Eignung für den generischen Request ersetzt keine typabhängigen Lebensdauerprüfungen:

- Buffer: Pending-Use-Regeln, Command-Buffer-Invalidierung und stale Descriptor-Slots gelten wie oben beschrieben.
- Pipeline und Pipeline Layout: Referenzen aus einem `RECORDING`-Command-Buffer verhindern die Zerstörung; Pending-Use verhindert sie ebenfalls. Bei erfolgreicher Zerstörung werden nicht-pending `EXECUTABLE`-Command-Buffer mit entsprechenden Referenzen `INVALID`.
- Shader Module und Descriptor Set Layout: Nach Ende ihrer erforderlichen Erstellungs-/Pipeline-Layout-Abhängigkeit gelten die jeweiligen Vulkan-Lebensdauerregeln.

Jede Ablehnung ist atomar und lässt die öffentliche XID, interne Lebensdauerzustände und abhängige Command-Buffer-Zustände unverändert. Bei Erfolg wird die öffentliche XID im Request sofort ungültig; interne Objekte bleiben bis zum Ende aller erforderlichen Referenzen und Backend-Zugriffe erhalten. Die Device-weite Kaskadeninvalidierung bei `DestroyDevice` oder Client-Disconnect bleibt davon unberührt. Device Loss allein invalidiert keine öffentlichen XIDs; er terminalisiert angenommene Arbeit und verändert die betroffenen Ressourcen- und Synchronisationszustände gemäß den nachfolgenden Regeln.

## Dedicated destruction requests

`DestroyDevice`, `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets` und `FreeMemory` bleiben eigene Requests, weil sie eigene Ownership-, Kaskaden- oder Speicherfreigaberegeln besitzen. `DestroyFence` und `DestroySemaphore` sind ebenfalls dedizierte Requests; sie sind ausdrücklich **nicht** über `DestroyResource` aufrufbar. Das verhindert zwei Wire-Pfade mit unterschiedlichen Zustandsprüfungen für dasselbe Synchronisationsobjekt.

`FreeMemory` invalidiert die Memory-XID nur bei Erfolg. Gebundene Buffer führen zu `BadMatch`; angenommene GPU-Arbeit, die auf die Allokation zugreift, führt zu `INVALID_SYNCHRONIZATION_STATE`. XAverius v0.1 kennt kein Unbind/Rebind, daher müssen alle gebundenen Buffer zuerst zerstört werden.

## Device Destruction and Client Disconnect

Bei erfolgreichem `DestroyDevice` oder Client-Disconnect werden die öffentlichen XIDs des logischen Devices und seiner Ressourcen ungültig; danach sind sie für neue Requests nicht mehr adressierbar. Die Kaskadeninvalidierung darf nicht an normalen Pending-Use-Ablehnungen scheitern. Sie ändert aber nicht rückwirkend bereits angenommene Arbeit: Bei normalem Teardown muss diese Arbeit ihren tatsächlichen terminalen Ausgang erreichen, und interne Vulkan-Objekte bleiben bis zum Ende aller Backend-Zugriffe erhalten.

Ein Client-Disconnect beendet die Event-Zustellung für genau diese X11-Verbindung. Der Server muss die Verbindung als nicht mehr zustellbar behandeln und ihre Event-Auswahlen sowie die öffentlichen XID-Zuordnungen aus dem aktiven Verbindungszustand entfernen. Asynchrone Backend-Abschlüsse dürfen weder Events in eine geschlossene Verbindung einreihen noch über eine andere Verbindung zugestellt werden. Die Event-Zuordnung muss an die konkrete X11-Verbindung und interne Ressourcenidentität gebunden bleiben, nicht nur an eine numerische XID. Bei `ASYNC_ERROR` darf eine inzwischen zerstörte oder wiederverwendete Ressourcen-XID nicht als `resource_xid` ausgegeben werden; ist die öffentliche Ressourcen-XID beim Linearisierungspunkt nicht mehr live, wird `resource_xid = 0` serialisiert. Der Server darf eine XID nicht aus der aktuellen Tabelle neu auflösen, um ein verspätetes Event zu bauen. Bereits angenommene Arbeit wird unabhängig davon intern bis zu ihrem tatsächlichen terminalen Ausgang abgewickelt; der Disconnect verlangt weder eine erfolgreiche Completion noch unbegrenztes Warten auf GPU-Fortschritt. Ressourcen, auf die das Backend möglicherweise noch zugreift, bleiben bis zum nachweislichen Ende dieser Zugriffe erhalten oder werden nach den Device-Loss-Regeln quarantänisiert.

**Identität asynchroner Abschlüsse:** Jeder beim Backend registrierte Callback oder Completion-Datensatz muss die unveränderliche interne Identität der konkreten Submission beziehungsweise Ressource und die Identität der ursprünglichen X11-Verbindung mitführen. Beim Abschluss darf der Server die Zielressource nicht anhand einer numerischen XID erneut aus der aktuellen XID-Tabelle auflösen. Vor einer Event-Einreihung muss er prüfen, dass genau die ursprüngliche Verbindung noch aktiv und zustellbar ist und dass die Lifecycle-Regeln der mitgeführten internen Device-Identität die Zustellung noch erlauben. Eine geschlossene Verbindung, eine zerstörte Device-Identität oder eine inzwischen wiederverwendete XID darf niemals auf ein neues Objekt oder eine andere Verbindung umgebogen werden. Das Verwerfen einer unzustellbaren Completion betrifft nur die Zustellung; interne Submission-, Fence-/Semaphore- und Backend-Aufräumzustände müssen trotzdem genau einmal terminalisiert werden.

Offene serverseitige Host-Waits der getrennten Verbindung werden abgebrochen und aus den Wait-Registrierungen entfernt; da die Verbindung geschlossen ist, wird dafür kein Reply erzeugt. Das Abbrechen eines Host-Waits bricht keine bereits angenommene GPU-Submission ab und verändert weder deren terminalen Ausgang noch Semaphore-/Fence-Zustände. Referenzen, die ausschließlich der abgebrochenen Wait-Registrierung dienten, werden freigegeben, sobald der Abbruch atomar feststeht; Referenzen laufender Backend-Operationen bleiben nach den normalen Lebensdauerregeln bestehen.

Konkurrierende Wait-Abschlüsse werden anhand der serialisierten serverseitigen Zustandsübergänge entschieden. Für einen offenen Wait gewinnt der erste festgestellte terminale Ausgang: bereits festgestellte Erfüllung beziehungsweise ein bereits festgestellter Timeout bleibt bestehen; zuerst erkannter Device Loss beendet den Wait mit `DEVICE_LOST`; wird `DestroyDevice` verarbeitet, solange der Wait noch offen ist und Device Loss noch nicht festgestellt wurde, endet er mit `DEVICE_DESTROYED`. Der Disconnect entfernt den Wait ohne Reply. Ein späterer Übergang darf den bereits terminalen Wait nicht überschreiben.

Nach erfolgreicher Verarbeitung von `DestroyDevice` darf der Server keine neuen XAverius-Events mehr erzeugen oder zustellen, deren `device_xid` das zerstörte logische Device bezeichnet. Das gilt auch für `DEVICE_LOST`, `DEVICE_IDLE`, `DEVICE_MEMORY_PRESSURE`, `SUBMISSION_COMPLETE`, `SUBMISSION_FAILED` und `ASYNC_ERROR`; bei `ASYNC_ERROR` darf die zerstörte Device-XID nicht als `device_xid` oder `resource_xid` ausgegeben werden. Bereits vor der Verarbeitung von `DestroyDevice` erzeugte und in den X11-Ausgabestrom eingereihte Events bleiben davon unberührt. Die Unterdrückung der Zustellung ändert weder den internen terminalen Ausgang angenommener Submissions noch die Pflicht, Backend-Referenzen bis zum Ende möglicher Zugriffe zu halten. Device- und Queue-Event-Auswahlen werden mit der Kaskadeninvalidierung entfernt.

Die interne Bereinigung muss sicher und unabhängig von der öffentlichen XID-Verfügbarkeit erfolgen. Der Server darf nicht unbegrenzt auf einem hängenden oder verlorenen Device warten. Wenn das Device verloren ist, gelten die folgenden Device-Loss-Regeln; der Server darf erfolgreiche GPU-Completion nicht vortäuschen.

## Device Loss and Terminal Cleanup

Wird ein logisches Device als verloren erkannt, gilt für alle darauf angenommenen, noch nicht terminalen Submissions:

- Jede Submission endet als fehlgeschlagen mit Status `DEVICE_LOST`; sie darf nicht als erfolgreich abgeschlossen gemeldet werden.
- Zugehörige Fences wechseln nach `FAILED`, nicht nach `SIGNALED`.
- Betroffene Command Buffer wechseln nach Ende ihrer Pending-Phase nach `INVALID` und sind nicht erneut einreichbar.
- Interne Ressourcenreferenzen bleiben so lange erhalten, wie der Backend-Treiber oder die Serverbereinigung noch auf sie zugreifen kann. Ihre Freigabe darf nicht von einer GPU-Completion abhängen, die nach Device Loss nicht mehr eintreten kann.

Einzelne ressourcenspezifische Destroy-/Free-Requests sind nach Device Loss nicht pauschal verboten: Sie dürfen ausgeführt werden, wenn ihre jeweiligen Ownership-, Recording- und Lebensdauerprüfungen erfüllt sind. Da betroffene Submissions und offene Host-Waits bei erkanntem Device Loss terminalisiert werden, dürfen sie nicht allein wegen ihres früheren Pending-Zustands weiter blockieren. `DestroyResource`, `DestroyFence`, `DestroySemaphore`, `DestroyCommandPool`, `DestroyDescriptorPool` und `FreeDescriptorSets` bleiben logische Bereinigungswege nach ihren jeweiligen Regeln; insbesondere bleiben Recording-Referenzen ein Hindernis, wo die Request-Regeln dies vorsehen. `FreeMemory` bleibt gesperrt, solange intern noch ein Buffer gebunden ist oder Backend-Zugriffe auf die Allokation möglich sind. Ein logischer Destroy darf öffentliche XIDs invalidieren, aber keine vorzeitige Freigabe interner Backend-Objekte erzwingen.

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

Ein Descriptor Set darf nicht aktualisiert oder freigegeben werden, solange eine angenommene Submission es verwenden kann. Command Buffer referenzieren das Descriptor-Set-Objekt; die Slot-Inhalte werden bei der späteren Ausführung aus dem aktuellen Set gelesen, nicht beim Recording eingefroren. Ein erfolgreiches `UpdateDescriptorSets` ersetzt deshalb atomar die betroffenen Slot-Inhalte und aktualisiert die daraus abgeleiteten internen Buffer-Referenzen aller nicht-pending Command Buffer, die das Set referenzieren. Ein `EXECUTABLE`-Command-Buffer bleibt durch das Update allein ausführbar; eine spätere Zerstörung einer nun nicht mehr referenzierten alten Ressource darf ihn nicht wegen dieser entfernten Abhängigkeit invalidieren.

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
