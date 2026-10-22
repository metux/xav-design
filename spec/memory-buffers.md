# 5. Memory und Buffers

## 5.1 `CreateBuffer`

Gesamtlänge: 32 Bytes.

| Offset | Typ | Feld |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `buffer_xid` |
| 16 | CARD64 | `size` in Bytes |
| 24 | CARD32 | `usage_flags` |
| 28 | CARD32 | `reserved = 0` |

Die Größe muss positiv sein und mindestens ein unterstütztes `usage_flags`-Bit muss gesetzt sein. Unbekannte Bits oder `usage_flags = 0` werden mit `BadValue` abgewiesen. Buffer-Erstellung alloziert und bindet noch keinen Speicher.

Usage-Bits:

- Bit 0: `STORAGE_BUFFER`
- Bit 1: `TRANSFER_SRC`
- Bit 2: `TRANSFER_DST`
- Bit 3: `UNIFORM_BUFFER`
- Bit 4: `INDEX_BUFFER`
- Bit 5: `VERTEX_BUFFER`
- Bit 6: `INDIRECT_BUFFER`
- Bits 7–31: reserviert

Der Server darf keine Usage-Flags stillschweigend hinzufügen. Images sind in v0.1 nicht enthalten.

Für den initialen Compute-Test:

- A und B: `STORAGE_BUFFER | TRANSFER_DST`
- C: `STORAGE_BUFFER | TRANSFER_SRC`

## 5.2 `GetPhysicalDeviceMemoryProperties`

Request: Physical-Device-XID bei Offset 8, Gesamtlänge 12 Bytes. Der Request verwendet ausdrücklich die XID eines Physical Devices, nicht die XID eines logischen Devices.

Der Reply enthält nach dem 32-Byte-Header:

- `CARD32 memory_type_count`
- `CARD32 memory_heap_count`
- `CARD32 memory_properties_flags`
- `CARD32 reserved = 0`
- `MEMORYTYPEINFO[]`
- `MEMORYHEAPINFO[]`

`MEMORYTYPEINFO` ist 8 Bytes groß:

- `CARD32 property_flags`
- `CARD32 heap_index`

`MEMORYHEAPINFO` ist 16 Bytes groß:

- `CARD64 size`
- `CARD32 heap_flags`
- `CARD32 reserved = 0`

Die Reply-Payload-Länge beträgt `16 + 8 * memory_type_count + 16 * memory_heap_count` Bytes. Entsprechend ist `reply.length = 4 + 2 * memory_type_count + 4 * memory_heap_count`.

Memory-Type-Flags:

- Bit 0: `DEVICE_LOCAL`
- Bit 1: `HOST_VISIBLE`
- Bit 2: `HOST_COHERENT`
- Bit 3: `HOST_CACHED`
- Bit 4: `LAZILY_ALLOCATED`
- Bit 5: `PROTECTED`

Heap-Flag-Bit 0 bezeichnet `DEVICE_LOCAL`. Andere Bits sind reserviert.

Es gelten maximal 32 Memory Types und 16 Memory Heaps. Indizes beginnen bei null und bleiben für die Lebensdauer der Physical-Device-XID beziehungsweise ihrer Gerätegeneration stabil; alle logischen Devices auf diesem Physical Device verwenden dieselbe Zuordnung. Jeder Heap-Index muss gültig sein. `memory_type_count` und `memory_heap_count` dürfen ihre jeweiligen Obergrenzen nicht überschreiten. Jeder `property_flags`-Wert darf nur definierte Bits enthalten; reservierte Bits müssen null sein. `heap_index` muss kleiner als `memory_heap_count` sein. Bei null Memory Types beziehungsweise null Memory Heaps darf kein entsprechender Record folgen.

`memory_properties_flags` besitzt noch keine festgelegte Semantik; bis zur Zuweisung einer Registry-Definition muss das Feld null sein.

## 5.3 `GetBufferMemoryRequirements`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Gesamtlänge: 16 Bytes

Reply:

| Offset | Typ | Feld |
|---:|---|---|
| 8 | CARD64 | `size` |
| 16 | CARD64 | `alignment` |
| 24 | CARD32 | `memory_type_bits` |
| 28 | CARD32 | `reserved = 0` |

Reply-Payload-Länge ist null. Größe und Alignment müssen positiv sein. `memory_type_bits` ist eine Bitmaske: Bit N erlaubt `memory_type_index = N`; Bits außerhalb von `memory_type_count` müssen null sein. Für einen erfolgreich abgefragten Buffer muss mindestens ein unterstützter Memory-Type-Bit gesetzt sein. Die Werte beziehen sich auf das Physical Device des angegebenen logischen Devices und bleiben für dessen Lebensdauer stabil.

## 5.4 `AllocateMemory`

Gesamtlänge: 32 Bytes.

- Offset 8: Device-XID
- Offset 12: Memory-XID
- Offset 16: `CARD64 allocation_size`
- Offset 24: `CARD32 memory_type_index`
- Offset 28: `CARD32 reserved = 0`

Die Allokationsgröße muss positiv sein, und der Memory-Type-Index muss für das Physical Device des logischen Devices existieren. `AllocateMemory` reserviert genau `allocation_size` Bytes und bindet keinen Buffer. Der Server darf die angeforderte Größe nicht stillschweigend aufrunden; notwendige interne Backend-Ausrichtung muss ohne Änderung der öffentlich sichtbaren Allokationsgröße umgesetzt werden. Kann die Allokation nicht bereitgestellt werden, wird `ALLOCATION_FAILED` gemeldet und die `memory_xid` bleibt unangelegt.

## 5.5 `FreeMemory`

Gesamtlänge: 16 Bytes.

- Offset 8: Device-XID
- Offset 12: Memory-XID

Der Memory-Block muss zum angegebenen logischen Device gehören. Der Request wird atomar abgewiesen, wenn irgendein Buffer noch an diese Allokation gebunden ist (`BadMatch`) oder angenommene GPU-Arbeit auf die Allokation zugreift (`INVALID_SYNCHRONIZATION_STATE`). Bei Ablehnung bleiben Memory-XID und Allokation unverändert.

XAverius v0.1 unterstützt kein Unbind/Rebind. Daher müssen alle an die Allokation gebundenen Buffer vor `FreeMemory` erfolgreich zerstört werden. Bei Erfolg wird die öffentliche Memory-XID sofort ungültig; die interne Allokation darf erst freigegeben werden, wenn keine internen Referenzen oder Backend-Zugriffe mehr bestehen.

## 5.6 `BindBufferMemory`

Gesamtlänge: 28 Bytes.

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: Memory-XID
- Offset 20: `CARD64 memory_offset`

Buffer und Memory müssen zum angegebenen Device gehören. In v0.1 darf ein Buffer nur einmal gebunden werden.

Der `memory_type_index` der Allokation muss kleiner als `memory_type_count` sein und das entsprechende Bit in `memory_type_bits` muss gesetzt sein (`(memory_type_bits & (1u << memory_type_index)) != 0`). Der Offset ist in Bytes angegeben und muss ein Vielfaches des gemeldeten `alignment` sein. Für die Bindungsgrenze ist `requirements.size` maßgeblich, nicht lediglich die logische Buffer-Größe; die Allokation muss also den vollständigen vom Backend benötigten Bereich abdecken.

Die Bounds-Prüfung muss überlaufsicher erfolgen:

- `memory_offset <= allocation_size`
- `requirements.size <= allocation_size - memory_offset`

Cross-Device-Nutzung, unpassender Memory-Type, doppeltes Binden, ungültiges Alignment oder unzureichender Speicher ergeben `BadMatch`. Unbekannte/nicht-live Device-, Buffer- oder Memory-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp ergibt `BadMatch`. Bei nicht verfügbarem oder verlorenem Device wird `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST` gemeldet. Der Request ist atomar: bei Ablehnung bleibt der Buffer ungebunden.

## 5.7 `WriteBuffer`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: `CARD64 buffer_offset`
- Offset 24: `CARD32 data_length`
- Offset 28: Byte-Payload
- anschließend Null-Padding bis zur nächsten Vierbytegrenze

Gesamtlänge:

`28 + ((uint64(data_length) + 3) & ~uint64(3))`

`data_length` muss positiv sein. Die Gesamtlänge muss mit breiterer als 32-Bit-Arithmetik berechnet werden. Ist sie nicht ohne Überlauf darstellbar oder größer als die für diese Verbindung geltende maximale X11-Request-Länge, wird der Request mit `BadLength` abgewiesen. Das Padding muss vollständig aus Nullbytes bestehen; nicht-null Padding ergibt `BadValue`.

Der Buffer muss gebunden sein, `TRANSFER_DST` besitzen und den vollständigen Zielbereich abdecken. Bounds werden überlaufsicher mit `buffer_offset <= buffer_size` und `data_length <= buffer_size - buffer_offset` geprüft.

Jeder `WriteBuffer`-Request ist ein eigenständiger Schreibvorgang. Es gibt weder Upload-ID noch einen mehrteiligen Upload-Transaktionszustand oder ein Final-Chunk-Flag.

Clients dürfen mehrere Requests im normalen X11-Request-Stream hintereinander senden. Jeder Request erhält seine eigene Sequenznummer und seinen eigenen Reply.

`WriteBuffer` ist ein Reply-Request. Bei Erfolg sendet der Server einen leeren Standard-X11-Reply von 32 Bytes; bei einem Fehler vor Abschluss sendet er den definierten X11-Fehler. Ein Void-Request ohne Reply wäre mit den folgenden Abschlussgarantien nicht vereinbar.

Ein erfolgreicher Reply garantiert normativ:

1. Die Eingabedaten wurden vollständig übernommen; der Client darf seinen Eingabepuffer wiederverwenden.
2. Der Transfer ist abgeschlossen und alle erforderlichen Host-Cache- sowie GPU-Visibility-Operationen sind erfolgt.
3. Alle vor diesem `WriteBuffer`-Request angenommenen `QueueSubmit`-Submissions desselben logischen Devices haben ihren terminalen Ausgang erreicht und das Backend greift nicht mehr auf Ressourcen zu, deren Zugriff mit dem Schreibtransfer kollidieren könnte, bevor der Schreibtransfer die Zieldaten verändert. Dies verhindert Rennen mit früher eingereihter GPU-Arbeit, auch wenn sie auf einer anderen Queue läuft.
4. Jeder `QueueSubmit` desselben logischen Devices, den der Server nach erfolgreicher Verarbeitung dieses Requests annimmt, muss die geschriebenen Bytes sehen, wenn die Submission sie liest. Das gilt unabhängig von Queue-Family und Queue-Index und auch dann, wenn der Buffer oder Speicher nicht host-coherent ist.
5. Diese Garantie gilt für den gesamten geschriebenen Bereich und erfordert keine expliziten Semaphore oder Barrieren des Clients zwischen diesem Upload und später angenommenen Submissions.

Diese Regeln definieren einen Ordnungsübergang ausschließlich innerhalb des angegebenen logischen Devices: frühere angenommene GPU-Arbeit → abgeschlossener `WriteBuffer`-Transfer → später angenommene GPU-Arbeit. Es gibt keine implizite Synchronisation mit anderen logischen Devices, auch wenn diese derselben physischen GPU zugeordnet sind. Logische Devices gehören jeweils der Client-Verbindung, die sie erstellt hat.

Der Server darf den X11-Request-Dispatcher nicht synchron blockieren, während er auf frühere GPU-Arbeit wartet, wenn dadurch ein späterer `SignalSemaphore`-Request derselben Verbindung nicht mehr verarbeitet werden könnte. Ein solcher späterer Host-Signal-Request darf ausgeführt werden, um frühere Submissions freizugeben. Spätere `QueueSubmit`-Requests derselben Verbindung dürfen dagegen erst angenommen werden, nachdem `WriteBuffer` erfolgreich abgeschlossen wurde; sie müssen bis dahin zurückgestellt werden. So bleibt die Upload-Grenze wirksam, ohne eine Submission durch einen Host-Signal-Request zu deadlocken. Bei einem fehlgeschlagenen `WriteBuffer` gilt die erfolgreiche Upload-Garantie nicht; zurückgestellte Requests werden nach Feststellung des Fehlers gemäß ihren normalen Regeln weiterverarbeitet. Während ein `WriteBuffer` auf frühere Submissions wartet, muss der Server außerdem die Signal-Entries zurückgestellter `QueueSubmit`-Requests auf einen möglichen Abhängigkeitszyklus prüfen. Wenn eine zurückgestellte Submission ein Binary-Semaphore signalisiert, auf das eine frühere nicht-terminale Submission wartet, oder einen Timeline-Wert signalisiert, der den von einer früheren nicht-terminalen Submission erwarteten Wert erreicht oder überschreitet, und kein bereits angenommener Signalvorgang diesen Wait erfüllen kann, muss der Server den ausstehenden `WriteBuffer` mit `DEPENDENCY_FAILED` beenden, statt auf den zurückgestellten GPU-Signalvorgang zu warten. Für diese Prüfung zählen Signal-Entries aus zurückgestellten Submissions nicht als angenommene oder verfügbare Signale. Solange ein `QueueSubmit` zurückgestellt ist, darf er weder Semaphore-/Fence-Zustände oder Pending-Reservierungen verändern noch interne Ressourcenreferenzen als angenommene Submission festschreiben; vollständige Validierung und atomare Zustandsübernahme erfolgen erst nach Abschluss des `WriteBuffer`. Danach werden zurückgestellte Requests in normaler Request-Reihenfolge verarbeitet. Diese konservative Regel kann einen Upload auch dann ablehnen, wenn ein noch nicht eingetroffener Host-Signal-Request denselben Wait hätte erfüllen können; sie verhindert jedoch, dass die Upload-Ordnungsgrenze einen bereits erkennbaren Zyklus unauflösbar macht.

In v0.1 darf der Server dies konservativ durch vollständiges Warten auf vorherige Submissions und durch notwendige Transfer-/Speicherbarrieren beziehungsweise Device-Synchronisation implementieren. Eine optimierte Implementierung darf feingranularer arbeiten, muss aber dieselbe beobachtbare Ordnung und das beschriebene Fortschrittsverhalten garantieren.

Ein vorheriger Submission-Fehler allein verhindert den Upload nicht, sofern das Device weiterhin verwendbar ist: Der Server wartet auf den terminalen Ausgang, führt den Transfer danach aus und garantiert die neuen Bytes für spätere Arbeit. Ist das Device verloren, schlägt `WriteBuffer` mit `DEVICE_LOST` fehl und darf keinen erfolgreichen Reply senden. Bei einem fehlgeschlagenen Upload wird ebenfalls kein erfolgreicher Reply gesendet; der Inhalt des Zielbereichs ist dann nicht garantiert.

## 5.8 `ReadBuffer`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: `CARD64 buffer_offset`
- Offset 24: `CARD32 data_length`

Gesamtlänge: 28 Bytes.

Die Länge muss positiv sein. Der Buffer muss gebunden sein, `TRANSFER_SRC` besitzen und den angeforderten Bereich abdecken. Bounds werden überlaufsicher mit `buffer_offset <= buffer_size` und `data_length <= buffer_size - buffer_offset` geprüft.

Der Reply enthält nach dem 32-Byte-Header genau `data_length` gelesene Bytes ab Offset 32 und anschließend Null-Padding auf vier Bytes. `reply.length = floor((uint64(data_length) + 3) / 4)`; die Rechnung erfolgt in mindestens 64-Bit-Arithmetik. Das Padding ist Teil des X11-Reply-Transports und nicht Teil der Buffer-Daten.

`ReadBuffer` definiert einen Snapshot-Ordnungsübergang innerhalb des adressierten logischen Devices. Der Server muss vor dem Snapshot alle vor diesem Request angenommenen `QueueSubmit`-Submissions abwarten, deren Arbeit den angeforderten Bereich direkt oder über eine andere gebundene Ressource schreiben kann, und sicherstellen, dass deren Backend-Zugriffe auf den Bereich beendet sind. Dasselbe gilt für alle vor diesem Request eingereihten `WriteBuffer`-Transfers: Ein erfolgreicher Transfer muss abgeschlossen sein; ein fehlgeschlagener Transfer muss terminal sein und darf den Zielbereich nicht mehr im Backend verändern können. Eine bloße logische Terminalisierung reicht nicht aus, solange Backend-Zugriffe noch möglich sind. Ein fehlgeschlagener früherer `WriteBuffer` liefert keine Sichtbarkeitsgarantie für dessen Zielbereich; `ReadBuffer` darf deshalb nicht so tun, als seien die fehlgeschlagenen Eingabedaten geschrieben worden. Erforderliche Host-Visibility- und Cache-Operationen müssen vor dem Snapshot abgeschlossen sein. Bloße Queue-Reihenfolge auf einer einzelnen Queue reicht nicht aus, wenn andere Queues beteiligt sind.

Der Server muss die angeforderten Bytes in einen stabilen Daten-Snapshot übernehmen, bevor ein späterer `QueueSubmit` desselben Devices den gelesenen Bereich verändern darf. Solche späteren `QueueSubmit`-Requests dürfen bis zur Erfassung des Snapshots zurückgestellt werden; sie gelten währenddessen nicht als angenommen und dürfen keine Semaphore-/Fence-Zustände, Pending-Reservierungen oder internen Referenzen angenommener Submissions verändern. Danach werden sie in normaler Request-Reihenfolge validiert und verarbeitet. Der Request-Dispatcher darf während des Wartens nicht so blockieren, dass ein späterer Host-`SignalSemaphore`-Request derselben Verbindung eine frühere Submission nicht mehr freigeben kann. Wie bei `WriteBuffer` muss der Server erkennbare Abhängigkeitszyklen prüfen: Wenn ein zurückgestelltes Queue-Signal für eine frühere nicht-terminale Submission erforderlich wäre und kein bereits angenommener Signalvorgang den Wait erfüllen kann, muss `ReadBuffer` mit `DEPENDENCY_FAILED` fehlschlagen, statt auf den zurückgestellten Signalvorgang zu warten. Signal-Entries zurückgestellter Submissions gelten dabei nicht als angenommene oder verfügbare Signale. Ein fehlgeschlagener `ReadBuffer` verspricht keinen Snapshot; zurückgestellte Requests werden danach nach ihren normalen Regeln weiterverarbeitet.

Ein früherer Submission-Fehler verhindert `ReadBuffer` nicht allein, solange das Device weiterhin verwendbar ist. Der Reply enthält dann die tatsächlich im Snapshot lesbaren Bytes, aber XAverius garantiert nicht, dass ein Bereich, dessen beabsichtigter Schreibzugriff fehlgeschlagen ist, die vom fehlgeschlagenen Shader oder Transfer erwarteten Daten enthält. Der Server darf aus einem fehlgeschlagenen Submission-Status keine erfolgreiche Ausführung oder Datenintegrität ableiten. Ist das logische Device verloren, muss `ReadBuffer` mit `DEVICE_LOST` fehlschlagen und darf keinen erfolgreichen Daten-Reply senden; Daten dürfen nicht aus einem Backend gelesen werden, dessen Zugriffssicherheit oder Quieszenz nicht feststeht. Interne Ressourcen und Speicher bleiben bis zum nachweislichen Ende möglicher Backend-Zugriffe referenziert oder werden gemäß den Device-Loss-Regeln quarantänisiert.

Eine konservative Implementierung darf für v0.1 das Device vollständig synchronisieren, wenn keine feinere Abhängigkeitsverfolgung vorhanden ist. Sie muss trotzdem den Snapshot vor späteren schreibenden Submissions stabilisieren und die oben genannten Regeln für Submission-Fehler, Abhängigkeitszyklen und Device Loss einhalten.
