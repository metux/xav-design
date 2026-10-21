# Resource lifetime and ownership

## Client resources

Client-erzeugte XAverius-Ressourcen verwenden gültige, vom Client allokierbare XIDs.

Ein ungültiger oder bereits belegter Create-XID ergibt `BadIDChoice`, sofern der jeweilige Request keine speziellere X11-Regel vorschreibt.

Der Server muss für jede Ressource eine interne Identität verwalten, die nicht allein aus der öffentlichen XID besteht. Dadurch darf eine spätere Wiederverwendung derselben XID niemals laufende Arbeit auf eine neue Ressource umleiten.

Eine erfolgreich zerstörte öffentliche Ressource ist für neue Requests nicht mehr adressierbar.

# Ressourcenlebenszyklus und Zerstörung

## Zustandsmodell

Jedes Objekt besitzt mindestens zwei getrennte Lebensdaueransichten:

**Öffentlicher Zustand**

- `LIVE`
- `INVALID`

**Interner Zustand**

- `ACTIVE`
- `DESTROY_PENDING`
- `RELEASED`

Die Implementierung sollte zusätzlich die interne Ressourcenidentität, Client- und Device-Ownership, abhängige Objekte sowie ausstehende Submission-Referenzen verfolgen.

Die öffentliche XID wird bei erfolgreicher Zerstörung sofort ungültig. Die tatsächliche Vulkan-Zerstörung darf verzögert erfolgen.

## Normative Zustandsübergänge

Die folgenden Übergänge sind normativ:

- Erfolgreiches Erstellen: öffentliche Sicht `LIVE`, interner Zustand `ACTIVE`.
- Abgewiesener Destroy-Request: keinerlei Änderung an öffentlichem Zustand, internem Zustand, abhängigen Command-Buffer-Zuständen oder Ownership.
- Erfolgreiche normale Zerstörung: öffentliche Sicht wird im selben Request `INVALID`. Sind keine internen Referenzen und keine Backend-Zugriffe mehr vorhanden, darf das Objekt direkt nach `RELEASED` wechseln; andernfalls wechselt es nach `DESTROY_PENDING`.
- `DESTROY_PENDING` → `RELEASED`: erst wenn alle internen Referenzen freigegeben sind, kein Backend-Zugriff mehr möglich ist und die Backend-Zerstörung abgeschlossen ist.
- Device-Kaskadeninvalidierung bei `DestroyDevice`, Client-Disconnect oder Device Loss: alle zugehörigen öffentlichen XIDs werden `INVALID`; Objekte mit verbleibenden internen Referenzen oder Backend-Zugriffen bleiben `DESTROY_PENDING`, die übrigen dürfen `RELEASED` werden.

Ein Objekt im Zustand `DESTROY_PENDING` kann nicht über seine alte XID adressiert oder erneut zerstört werden. Eine wiederverwendete XID bezeichnet eine neue interne Ressourcenidentität und darf keine Referenzen auf das alte Objekt übernehmen. `RELEASED` ist terminal.

Interne Referenzen werden getrennt gezählt beziehungsweise nachverfolgt für aufgezeichnete Command Buffer, angenommene Submissions, Buffer-Handles in Descriptor-Slots, Eltern-Kind-Ownership und noch laufende Serveroperationen. Das Entfernen einer öffentlichen XID entfernt nicht automatisch die Referenzen einer bereits angenommenen Submission. Bei erfolgreichem normalen Destroy müssen alle erforderlichen Command-Buffer-Invalidierungen und internen Referenzanpassungen atomar mit der öffentlichen Invalidierung erfolgen.

## Ownership-Hierarchie

Explizite Eltern-Kind-Beziehungen:

- Device → alle device-eigenen öffentlichen Ressourcen
- CommandPool → zugehörige Command Buffer
- DescriptorPool → zugehörige Descriptor Sets

Andere Beziehungen sind Abhängigkeiten, keine automatischen Ownership-Beziehungen:

- Buffer ↔ Memory
- Pipeline ↔ Pipeline Layout
- Pipeline ↔ Shader Module während der Erstellung
- Pipeline Layout ↔ Descriptor Set Layout während der Erstellung
- Command Buffer ↔ Ressourcen, die in aufgezeichneten Commands verwendet werden

Die Implementierung darf nicht annehmen, dass jedes Objekt, dessen Handle beim Erstellen eines anderen Objekts verwendet wurde, dauerhaft existieren muss. Maßgeblich sind die tatsächlichen Vulkan-Lebensdauerregeln.

## Zerstörungsmatrix

| Ressource | Öffentliche Zerstörung | Regel bei ausstehender Verwendung |
|---|---|---|
| Device | Invalidiert Device und Kinder sofort | Interne Bereinigung wird verzögert |
| CommandPool | Invalidiert Pool und Kind-Command-Buffer atomar | Abweisen, solange mindestens ein Kind pending ist |
| CommandBuffer | XID wird ungültig | Abweisen, solange pending |
| DescriptorPool | Invalidiert Pool und alle Kind-Sets atomar | Abweisen, wenn ein Kind-Set pending ist oder ein Kind-Set von einem `RECORDING`-Command-Buffer referenziert wird |
| DescriptorSet | XID wird ungültig | Abweisen, solange pending |
| Buffer | XID wird ungültig | Abweisen, solange ein angenommener GPU-Command den Buffer direkt oder indirekt verwendet; sonst interne Freigabe verzögern, falls noch Serveroperationen darauf verweisen |
| Memory | Nur bei erfolgreicher Prüfung invalidiert | `FreeMemory` wird abgewiesen, solange irgendein Buffer daran gebunden ist oder angenommene Arbeit die Allokation verwendet |
| Pipeline | XID wird ungültig | Abweisen, solange ein angenommener Command die Pipeline verwendet |
| PipelineLayout | XID wird ungültig | Abweisen, solange ein angenommener Command das Layout verwendet; nicht-pending executable Command Buffer werden nach der allgemeinen Referenzregel invalidiert |
| ShaderModule | Nach erfolgreicher Pipeline-Erstellung unabhängig zerstörbar | Vulkan-Lebensdauerregeln bleiben maßgeblich |
| DescriptorSetLayout | Nach erfolgreicher Pipeline-Layout-Erstellung unabhängig zerstörbar | Vulkan-Lebensdauerregeln bleiben maßgeblich |
| Fence | XID wird ungültig | Abweisen, solange die Fence einer nicht-terminalen Submission zugeordnet ist |
| Semaphore | XID wird ungültig | Abweisen, solange ein angenommener Queue-Wait/-Signal oder eine ausstehende Server-Host-Operation die Semaphore verwendet |
| Physical Device | Nicht durch Client zerstörbar | Server-Ownership; XID wird nie neu zugewiesen |

Die Regeln sind XAverius-API-Entscheidungen und keine Behauptung, dass Vulkan für alle Ressourcentypen identische Lebensdauerbeschränkungen definiert.

## Aufgezeichnete Referenzen und Command-Buffer-Invalidierung

Der Server verfolgt für jeden Command Buffer die Ressourcen, auf die seine aufgezeichneten Commands direkt oder indirekt verweisen. Dazu gehören insbesondere Pipelines, Pipeline Layouts, Descriptor Sets, Buffer und die über Descriptor Sets referenzierten Buffer. Diese Abhängigkeiten bleiben bestehen, solange der Command Buffer aufgezeichnet oder ausführbar ist. Eine Submission übernimmt eigene interne Referenzen, die bis zum terminalen Submission-Ausgang und bis zum Ende aller Backend-Zugriffe bestehen bleiben. Ein XID-Invalidieren darf nie einen Backend-Handle auf ein anderes Objekt umleiten.

- Wird eine Ressource zerstört, auf die ein `RECORDING`-Command-Buffer verweist, wird die Zerstörung mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen. Der Client muss die Aufzeichnung beenden oder den Command Buffer verwerfen, bevor er die Ressource zerstört.
- Wird eine Ressource zerstört, auf die ein `EXECUTABLE`-Command-Buffer verweist, werden diese Command Buffer vor erfolgreichem Abschluss des Destroy-Requests in `INVALID` überführt. Sie dürfen danach nicht eingereicht werden; eine erneute Aufzeichnung ist erforderlich.
- Ist die Ressource in einer angenommenen Submission noch in Verwendung, gilt die ressourcenspezifische Pending-Regel aus der Zerstörungsmatrix. Ein Destroy-Request, der wegen Pending-Use abgewiesen wird, lässt XID und Command-Buffer-Zustände unverändert.
- Ein Destroy-Request ist atomar: Wenn die ressourcenspezifische Regel die Zerstörung ablehnt, werden weder die öffentliche XID invalidiert noch Command-Buffer-Zustände geändert.

Das gilt auch für indirekte Abhängigkeiten, die über Descriptor Set → Buffer oder Buffer → gebundenen Memory verlaufen. Der Server darf einen ausführbaren Command Buffer nicht als gültig behandeln, wenn eine seiner aufgezeichneten Ressourcenabhängigkeiten öffentlich zerstört wurde.

## `DestroyResource`

Vorgeschlagener generischer Request:

- Offset 8: Ressourcen-XID
- Gesamtlänge: 12 Bytes

Die genaue Zulässigkeit für einzelne Ressourcentypen wird durch die jeweilige API-Regel bestimmt. Physical Devices sind ausgenommen.

Ein erfolgreicher Request invalidiert die öffentliche XID sofort. Interne Objekte dürfen erst freigegeben werden, wenn ihre Vulkan-Lebensdauerbedingungen erfüllt sind.

Ungültige XIDs, falsche Typen und fremde Ownership werden gemäß der request-spezifischen X11-Fehlerzuordnung behandelt.

## Device-Zerstörung und Client-Disconnect

Bei erfolgreichem `DestroyDevice` oder Client-Disconnect werden die öffentlichen XIDs des logischen Devices und seiner Ressourcen ungültig; danach sind sie für neue Requests nicht mehr adressierbar. Die Kaskadeninvalidierung darf nicht an normalen Pending-Use-Ablehnungen scheitern. Sie ändert aber nicht rückwirkend bereits angenommene Arbeit: Bei normalem Teardown muss diese Arbeit ihren tatsächlichen terminalen Ausgang erreichen, und interne Vulkan-Objekte bleiben bis zum Ende aller Backend-Zugriffe erhalten. Bei Client-Disconnect können Events nicht mehr zugestellt werden.

Die interne Bereinigung muss sicher und unabhängig von der öffentlichen XID-Verfügbarkeit erfolgen. Der Server darf nicht unbegrenzt auf einem hängenden oder verlorenen Device warten. Wenn das Device verloren ist, gelten die folgenden Device-Loss-Regeln; der Server darf erfolgreiche GPU-Completion nicht vortäuschen.

## Device Loss und terminale Bereinigung

Wird ein logisches Device als verloren erkannt, gilt für alle darauf angenommenen, noch nicht terminalen Submissions:

- Jede Submission endet als fehlgeschlagen mit Status `DEVICE_LOST`; sie darf nicht als erfolgreich abgeschlossen gemeldet werden.
- Zugehörige Fences wechseln nach `FAILED`, nicht nach `SIGNALED`.
- Betroffene Command Buffer wechseln nach Ende ihrer Pending-Phase nach `INVALID` und sind nicht erneut einreichbar.
- Interne Ressourcenreferenzen bleiben so lange erhalten, wie der Backend-Treiber oder die Serverbereinigung noch auf sie zugreifen kann. Ihre Freigabe darf nicht von einer GPU-Completion abhängen, die nach Device Loss nicht mehr eintreten kann.

Öffentliche Ressourcen-XIDs dürfen bei Device-Zerstörung oder der dazugehörigen Kaskadenbereinigung invalidiert werden, auch wenn normale Pending-Use-Zerstörungen sonst abgewiesen würden. Diese Sonderregel gilt nur für die Device-weite Bereinigung; sie hebt interne Referenzpflichten nicht auf und darf keine erfolgreiche Completion vortäuschen. Der Server muss den Backend-Zustand sicher abbauen und darf interne Ressourcen erst freigeben, wenn kein Backend-Zugriff mehr möglich ist.

Nach erkanntem Device Loss schlagen Requests, die weitere Vulkan-Arbeit erfordern, mit `DEVICE_LOST` fehl. Requests zur Statusabfrage und zur logischen Bereinigung dürfen weiterhin verarbeitet werden, soweit ihr jeweiliger Vertrag dies zulässt. Der genaue Fehlerpfad für fehlgeschlagene Backend-Teardown-Schritte bleibt ein offener Implementierungsaspekt.

## Descriptor Pools und Sets

`DestroyDescriptorPool` ist atomar. Der Request wird abgewiesen, wenn ein enthaltenes Set pending verwendet wird oder von einem `RECORDING`-Command-Buffer referenziert wird. Bei Ablehnung bleiben Pool, Sets und Command-Buffer-Zustände unverändert. Andernfalls werden der Pool und alle enthaltenen Sets öffentlich invalidiert; nicht-pending `EXECUTABLE`-Command-Buffer, die eines dieser Sets referenzieren, werden `INVALID`.

`FreeDescriptorSets` folgt denselben Regeln für die ausgewählten Sets: pending Verwendung oder Referenz durch einen `RECORDING`-Command-Buffer führt zur atomaren Ablehnung. Bei Erfolg werden die ausgewählten Sets invalidiert und nicht-pending `EXECUTABLE`-Command-Buffer, die sie referenzieren, `INVALID`. Ein Set darf nicht gleichzeitig über einen expliziten Free-Request und die Pool-Kaskade freigegeben werden; eine bereits invalidierte Set-XID ist für weitere Free-Requests ungültig.

## Pipelines und Synchronisationsobjekte

`DestroyPipeline` und `DestroyPipelineLayout` werden abgewiesen, solange eine angenommene Submission die jeweilige Ressource verwendet. Ohne Pending-Use gelten die allgemeinen Regeln für aufgezeichnete Referenzen: Referenzen aus `RECORDING`-Command-Buffer verhindern die Zerstörung; referenzierende nicht-pending `EXECUTABLE`-Command-Buffer werden bei erfolgreicher Zerstörung `INVALID`.

`DestroyFence` wird abgewiesen, solange die Fence einer nicht-terminalen Submission zugeordnet ist. `DestroySemaphore` wird abgewiesen, solange ein angenommener Queue-Wait, ein Queue-Signal oder eine noch laufende serverseitige Host-Operation die Semaphore verwendet. Diese Ablehnungen sind atomar und verwenden `INVALID_SYNCHRONIZATION_STATE`. Nach Device Loss darf die Device-weite Kaskadeninvalidierung diese normalen Ablehnungen umgehen, während interne Referenzen bis zum Ende möglicher Backend-Zugriffe bestehen bleiben.

## Command Buffer und Descriptor Sets

Ein pending Command Buffer darf in v0.1 nicht verändert, zurückgesetzt, freigegeben oder erneut eingereicht werden.

Ein Descriptor Set darf nicht aktualisiert oder freigegeben werden, solange eine angenommene Submission es verwenden kann.

Update-after-bind und Update-unused-while-pending werden nicht angeboten.

## Buffer und Memory

`DestroyBuffer` wird abgewiesen, solange eine angenommene Submission den Buffer direkt oder über einen Descriptor Set verwendet. Nach erfolgreicher Zerstörung werden nicht-pending executable Command Buffer, die den Buffer direkt oder indirekt referenzieren, gemäß der allgemeinen Regel `INVALID`. Descriptor Sets, die den Buffer enthalten, bleiben als Objekte bestehen, gelten aber als nicht submitbar, bis alle betroffenen Descriptor-Slots mit gültigen Buffer-Referenzen aktualisiert wurden oder die Sets freigegeben wurden. Neue Submissions mit solchen ungültigen Descriptor-Inhalten werden atomar abgewiesen.

`FreeMemory` wird abgewiesen, solange irgendein Buffer an die Allokation gebunden ist oder angenommene Arbeit auf die Allokation zugreift. XAverius v0.1 bietet kein Unbind/Rebind. Der Client muss daher alle gebundenen Buffer zuerst erfolgreich zerstören und erst danach den Memory-Block freigeben. Ein gebundener Buffer führt zu `BadMatch`; ausstehende GPU-Arbeit führt zu `INVALID_SYNCHRONIZATION_STATE`. Ein abgewiesener `FreeMemory`-Request invalidiert die Memory-XID nicht. Wenn ein zerstörter Buffer noch von Descriptor-Slots referenziert wird, bleibt sein internes Objekt bis zum Überschreiben dieser Slots oder zur Freigabe der Descriptor Sets erhalten; die Buffer-XID bleibt dabei ungültig.

## Fehler bei ungültigen Lebenszyklusoperationen

- Ungültige oder zerstörte XID: request-spezifischer Standard-X11-Fehler
- Falscher Typ oder inkompatible Ressource: normalerweise `BadMatch`
- Falsches Device: `BadMatch`
- Zerstörung eines pending Command Buffers oder Descriptor Sets: `INVALID_SYNCHRONIZATION_STATE`
- Ungültiger Fence-Reset: `INVALID_SYNCHRONIZATION_STATE`
- Verlorenes Device: `DEVICE_LOST`, sofern der Request nicht ausdrücklich noch die logische Invalidierung erlaubt

Die erfolgreiche Device-Kaskadeninvalidierung ist eine Sonderregel und wird nicht durch die normalen Pending-Use-Ablehnungen blockiert.
