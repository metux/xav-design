# 10. Ressourcenlebenszyklus und Zerstörung

## 10.1 Zustandsmodell

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

## 10.2 Ownership-Hierarchie

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

## 10.3 Zerstörungsmatrix

| Ressource | Öffentliche Zerstörung | Regel bei ausstehender Verwendung |
|---|---|---|
| Device | Invalidiert Device und Kinder sofort | Interne Bereinigung wird verzögert |
| CommandPool | Invalidiert Pool und Kind-Command-Buffer | Abweisen, solange ein Kind pending ist |
| CommandBuffer | XID wird ungültig | Abweisen, solange pending |
| DescriptorPool | Invalidiert Pool und Kind-Sets | Abweisen, solange ein Kind-Set pending ist |
| DescriptorSet | XID wird ungültig | Abweisen, solange pending |
| Buffer | XID wird ungültig | Buffer und gebundener Speicher bleiben intern erhalten |
| Memory | XID wird ungültig | Tatsächliche Freigabe erst, wenn abhängige Objekte und Arbeit es erlauben |
| Pipeline | XID wird ungültig | Konservative Regel: Zerstörung bei Pending-Use abweisen |
| PipelineLayout | XID wird ungültig | Konservative Regel: Zerstörung bei noch bestehender Command-/Submission-Abhängigkeit abweisen |
| ShaderModule | Nach erfolgreicher Pipeline-Erstellung unabhängig zerstörbar | Vulkan-Lebensdauerregeln bleiben maßgeblich |
| DescriptorSetLayout | Nach erfolgreicher Pipeline-Layout-Erstellung unabhängig zerstörbar | Vulkan-Lebensdauerregeln bleiben maßgeblich |
| Fence | XID wird ungültig | Konservative Regel: Pending-Zerstörung abweisen |
| Semaphore | XID wird ungültig | Konservative Regel: Zerstörung bei Pending-Use abweisen |
| Physical Device | Nicht durch Client zerstörbar | Server-Ownership; XID wird nie neu zugewiesen |

Die Regeln sind XAverius-API-Entscheidungen und keine Behauptung, dass Vulkan für alle Ressourcentypen identische Lebensdauerbeschränkungen definiert.

## 10.4 `DestroyResource`

Vorgeschlagener generischer Request:

- Offset 8: Ressourcen-XID
- Gesamtlänge: 12 Bytes

Die genaue Zulässigkeit für einzelne Ressourcentypen wird durch die jeweilige API-Regel bestimmt. Physical Devices sind ausgenommen.

Ein erfolgreicher Request invalidiert die öffentliche XID sofort. Interne Objekte dürfen erst freigegeben werden, wenn ihre Vulkan-Lebensdauerbedingungen erfüllt sind.

Ungültige XIDs, falsche Typen und fremde Ownership werden gemäß der request-spezifischen X11-Fehlerzuordnung behandelt.

## 10.5 Device-Zerstörung und Client-Disconnect

Bei `DestroyDevice` oder Client-Disconnect werden öffentliche Device-Ressourcen ungültig.

Die interne Bereinigung muss sicher und unabhängig von der öffentlichen XID-Verfügbarkeit erfolgen. Der Server darf nicht unbegrenzt auf einem hängenden oder verlorenen Device warten.

Nach Device Loss müssen betroffene Operationen als fehlgeschlagen behandelt werden. Der Server darf nicht so tun, als sei GPU-Arbeit erfolgreich abgeschlossen worden.

## 10.6 Command Buffer und Descriptor Sets

Ein pending Command Buffer darf in v0.1 nicht verändert, zurückgesetzt, freigegeben oder erneut eingereicht werden.

Ein Descriptor Set darf nicht aktualisiert oder freigegeben werden, solange eine angenommene Submission es verwenden kann.

Update-after-bind und Update-unused-while-pending werden nicht angeboten.

## 10.7 Buffer und Memory

Ein Buffer darf öffentlich invalidiert werden, obwohl eine Submission ihn noch benötigt. Das interne Buffer-Objekt und gebundener Speicher müssen erhalten bleiben, bis Vulkan ihre Freigabe erlaubt.

Memory darf nicht freigegeben werden, solange ein gebundener Buffer oder eine ausstehende Operation darauf angewiesen ist.

## 10.8 Fehler bei ungültigen Lebenszyklusoperationen

- Ungültige oder zerstörte XID: request-spezifischer Standard-X11-Fehler
- Falscher Typ oder inkompatible Ressource: normalerweise `BadMatch`
- Falsches Device: `BadMatch`
- Zerstörung eines pending Command Buffers oder Descriptor Sets: `INVALID_SYNCHRONIZATION_STATE`
- Ungültiger Fence-Reset: `INVALID_SYNCHRONIZATION_STATE`
- Verlorenes Device: `DEVICE_LOST`, sofern der Request nicht ausdrücklich noch die logische Invalidierung erlaubt

Die erfolgreiche Device-Kaskadeninvalidierung ist eine Sonderregel und wird nicht durch die normalen Pending-Use-Ablehnungen blockiert.

# 11. Zentrale XAverius-Fehler-Registry

Die folgenden Werte sind Offsets relativ zu `first_error` der Extension.

| Offset | Symbol |
|---:|---|
| 0 | `DEVICE_UNAVAILABLE` |
| 1 | `DEVICE_LOST` |
| 2 | `INVALID_SYNCHRONIZATION_STATE` |
| 3 | `EXECUTION_FAILED` |
| 4 | `TRANSFER_FAILED` |
| 5 | `ALLOCATION_FAILED` |
| 6 | `DEPENDENCY_FAILED` |
| 7 | `INTERNAL_SERVER_ERROR` |

Der tatsächliche X11-Fehlercode ist `first_error + offset`.

Das Fehlerpaket verwendet den Extension-Major-Opcode, den Request-Subopcode, die Sequenznummer des auslösenden Requests und eine betroffene Ressourcen-XID, falls sinnvoll; andernfalls null.

## 11.1 Allgemeine Fehlerklassen

| Situation | Ergebnis |
|---|---|
| Request-Länge oder Count inkonsistent | `BadLength` |
| Ungültiger Feldwert, reservierte Bits oder Flags | `BadValue` |
| Ungültige oder bereits belegte Create-XID | `BadIDChoice` |
| Falscher Ressourcentyp oder Cross-Device-Kombination | normalerweise `BadMatch` |
| Ungültige Ressource | Request-spezifischer Standard-X11-Fehler |
| Device nicht verfügbar | `DEVICE_UNAVAILABLE` |
| Device verloren | `DEVICE_LOST` |
| Ungültiger Synchronisationszustand | `INVALID_SYNCHRONIZATION_STATE` |
| Synchroner Transferfehler | `TRANSFER_FAILED` |
| Synchroner Allokationsfehler | `ALLOCATION_FAILED` |
| Ungültige Abhängigkeit verhindert Annahme | `DEPENDENCY_FAILED` |
| Unerwarteter Serverfehler | `INTERNAL_SERVER_ERROR` |

## 11.2 Request-spezifische Fehlerzuordnung

### `WriteBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null oder ungültige reservierte Felder: `BadValue`
- Ungültige XID: request-spezifischer X11-Fehler
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_DST`, Bereich außerhalb des Buffers: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`

### `ReadBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null oder ungültige reservierte Felder: `BadValue`
- Ungültige XID: request-spezifischer X11-Fehler
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_SRC`, ungültiger Bereich: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`

### `QueueSubmit`

- Count-/Längenfehler: `BadLength`
- Ungültige Masks, reservierte Felder oder numerische Werte: `BadValue`
- Ungültige XID: request-spezifischer X11-Fehler
- Falscher Typ oder Cross-Device-Ressource: `BadMatch`
- Nicht ausführbarer Command Buffer, ungültiger Fence- oder Semaphore-Zustand: `INVALID_SYNCHRONIZATION_STATE`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Ungültige Abhängigkeit, die Annahme verhindert: `DEPENDENCY_FAILED`

### Fence-Requests

- Falsche Länge: `BadLength`
- Ungültige Flags oder reservierte Felder: `BadValue`
- Ungültige Ressource: request-spezifischer X11-Fehler
- Falscher Typ oder Device: `BadMatch`
- Ungültiger Reset-/Destroy-Zustand: `INVALID_SYNCHRONIZATION_STATE`
- Timeout und asynchroner Ausführungsfehler bei `WaitForFence`: normaler Reply-Status

### `BindBufferMemory`

Cross-Device-Nutzung, bereits gebundener Buffer, ungültiges Alignment, zu kleine Allokation oder inkompatibler Memory-Type ergeben `BadMatch`.

### `UpdateDescriptorSets`

- Falsche Länge: `BadLength`
- Reservierte Felder oder ungültige Werte: `BadValue`
- Inkompatibler Descriptor, Buffer oder Device: `BadMatch`
- Update während Pending-Use: `INVALID_SYNCHRONIZATION_STATE`

Jeder Request muss vor Implementierungsfreigabe eine vollständige, konkrete Fehlerzuordnung besitzen.

## 11.3 Synchron versus asynchron

Ein Fehler vor Annahme wird durch einen X11-Fehler oder den ausdrücklich definierten normalen Fehler-Reply signalisiert. Der Request darf keinen Teilzustand hinterlassen.

Ein Fehler nach Annahme wird durch XAverius-Events und Synchronisationszustände signalisiert. Ein später X11-Fehler für einen bereits angenommenen Request ist unzulässig.
