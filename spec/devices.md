# Device-Discovery und logische Devices

## Device-Auswahl

Es gibt zwei Pfade:

1. `CreateDefaultDevice`: Der Server wählt ein geeignetes Physical Device und erstellt ein logisches Device.
2. Explizite Auswahl: `EnumeratePhysicalDevices`, Eigenschaftsabfragen und `GetPhysicalDeviceQueueFamilyProperties`, danach `CreateDevice`.

Queues werden nicht über Queue-XIDs adressiert. Eine Queue wird über das Tupel

`(device_xid, queue_family_index, queue_index)`

identifiziert.

Der Queue-Family-Index entspricht der Reihenfolge der zurückgegebenen Queue-Family-Liste. Der Queue-Index adressiert eine tatsächlich für diese Familie angeforderte Queue.

## `EnumeratePhysicalDevices`

Der Request enthält keinen request-spezifischen Payload und ist insgesamt 8 Bytes lang. Der Request-Typ ist `Reply`.

Der Reply enthält nach dem 32-Byte-X11-Header direkt null oder mehr `PHYSICALDEVICEINFO`-Records. Es gibt kein zusätzliches Device-Count-Feld. Da jeder Record einschließlich des gepaddeten Namens vierbyte-ausgerichtet ist, gilt `reply.length = Summe aller Record-Längen / 4`; bei null Records ist `reply.length = 0`.

Fester Record-Anteil: 32 Bytes.

| Relativer Offset | Typ | Feld |
|---:|---|---|
| 0 | XID | `physical_device_xid` |
| 4 | CARD32 | `device_type` |
| 8 | CARD32 | `vendor_id` |
| 12 | CARD32 | `device_id` |
| 16 | CARD32 | `api_version` |
| 20 | CARD32 | `driver_version` |
| 24 | CARD32 | `compute_queue_family_count` |
| 28 | CARD16 | `device_name_length` |
| 30 | CARD16 | `reserved = 0` |
| 32 | BYTE[] | UTF-8-Gerätename, ohne NUL, auf 4 Bytes gepaddet |

Die Record-Länge beträgt:

`32 + ((device_name_length + 3) & ~3)`

Padding muss null sein. `compute_queue_family_count` zählt nur Queue Families mit Compute-Unterstützung.

## `GetPhysicalDeviceProperty`

Request:

- Offset 8: Physical-Device-XID
- Offset 12: `ATOM property_atom`
- Gesamtlänge: 16 Bytes

Reply:

| Offset | Typ | Feld |
|---:|---|---|
| 8 | CARD32 | `status` |
| 12 | CARD32 | `property_type` |
| 16 | CARD32 | `value_length` in Bytes |
| 20–31 | BYTE[12] | reserviert, null |
| 32 | BYTE[] | Wert, auf 4 Bytes gepaddet |

Statuswerte:

- `SUCCESS = 0`
- `NOT_SUPPORTED = 1`
- `NOT_AVAILABLE = 2`

Bei einem Status ungleich `SUCCESS` müssen `property_type` und `value_length` null sein und der Reply enthält keinen Wert-Payload. Bei Erfolg gilt `reply.length = ceil(value_length / 4)`; bei einem Status ungleich `SUCCESS` ist `reply.length = 0`.

Vorgesehene XAverius-Property-Type-IDs:

| ID | Typ |
|---:|---|
| 0 | `NONE` |
| 1 | `CARD32` |
| 2 | `CARD64` |
| 3 | `ATOM` |
| 4 | `STRING8` |
| 5 | `BYTE_ARRAY` |
| 6 | `CARD32_ARRAY` |
| 7 | `CARD64_ARRAY` |

Kandidaten für Properties sind `device.uuid`, `driver.uuid`, `compute.maxWorkGroupInvocations` und `compute.maxWorkGroupSize`. Die konkrete Property- und Atom-Registry ist offen.

## `GetPhysicalDeviceQueueFamilyProperties`

Request: Physical-Device-XID bei Offset 8, Gesamtlänge 12 Bytes.

Reply: Standard-Reply-Header plus `QUEUEFAMILYINFO`-Records mit je 12 Bytes. Es gibt kein zusätzliches Count-Feld; `reply.length = 3 * queue_family_count`, wobei `queue_family_count` aus der Payload-Länge geteilt durch 12 folgt. Bei null Queue-Families ist `reply.length = 0`.

| Relativer Offset | Typ | Feld |
|---:|---|---|
| 0 | CARD32 | `queue_flags` |
| 4 | CARD32 | `queue_count` |
| 8 | CARD32 | `reserved = 0` |

Die Records folgen der Vulkan-Reihenfolge. Die Payload-Länge muss durch 12 teilbar sein.

Die Bits von `queue_flags` sind in der [Queue-Flag-Registry](../registries/queue-flags.md) normativ definiert. Server müssen native Vulkan-Flags in diese XAverius-Wire-Bits übersetzen; Bits 5–31 sind reserviert.

## `CreateDevice`

Request:

| Offset | Typ | Feld |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `physical_device_xid` |
| 16 | CARD16 | `queue_family_request_count` |
| 18 | CARD16 | `feature_request_count` |
| 20 | CARD16 | `device_extension_count` |
| 22 | CARD16 | `reserved = 0` |
| 24 | variable | Queue-Family-, Feature- und Extension-Requests |

`QUEUEFAMILYREQUEST`:

- `CARD32 queue_family_index`
- `CARD16 queue_count`
- `CARD16 reserved = 0`
- `FLOAT32 queue_priorities[queue_count]`

Größe: `8 + 4 * queue_count`.

Die Anzahl muss positiv und unterstützt sein. `queue_family_request_count` muss mindestens 1 sein. Prioritäten müssen endlich und im Intervall [0,1] liegen. Doppelte Queue-Family-Einträge sind unzulässig.

`DEVICEFEATUREREQUEST`:

- `CARD32 feature_id`
- `CARD32 enabled`

Größe: 8 Bytes. In v0.1 muss `enabled = 1` sein. Nicht angegebene Features werden nicht angefordert. Doppelte Feature-IDs sind ungültig.

`DEVICEEXTENSIONREQUEST`:

- `CARD16 name_length`
- `CARD16 reserved = 0`
- ASCII-Extension-Name ohne NUL, auf vier Bytes gepaddet

Größe: `4 + ((name_length + 3) & ~3)`.

Doppelte Extensions sind unzulässig. Feature-IDs und Extensions werden über zentrale Registries definiert. Die Registry unterscheidet bekannte Feature-IDs von unbekannten IDs; ein bekanntes Feature kann je Physical Device unterstützt oder nicht unterstützt sein. Extension-Namen müssen nichtleere ASCII-Namen ohne NUL sein und dem Vulkan-Extension-Namensformat entsprechen.

Für die Fehlerbehandlung gilt:

- Eine unbekannte `feature_id`, die nicht in der XAverius-Feature-Registry definiert ist, ergibt `BadValue`.
- Ein registriertes Feature, das das ausgewählte Physical Device nicht unterstützt, ergibt `BadMatch`.
- Ein formal ungültiger Extension-Name ergibt `BadValue`.
- Eine formal gültige Extension, die nicht in der XAverius-Extension-Registry bekannt ist oder vom ausgewählten Physical Device nicht unterstützt wird, ergibt `BadMatch`.
- Doppelte Feature-IDs oder Extension-Namen ergeben `BadValue`.
- Der Server aktiviert nur die ausdrücklich angeforderten und unterstützten Features und Extensions. Er darf nicht unterstützte Anforderungen nicht stillschweigend ignorieren.

Die Prüfung erfolgt vollständig vor der Erzeugung des logischen Devices. Bei einem Fehler bleibt die `device_xid` unangelegt und es werden keine partiellen Vulkan-Objekte veröffentlicht.

Die Gesamtlänge beträgt `24 + Σ(8 + 4 * queue_count_i) + 8 * feature_request_count + Σ(4 + ((name_length_j + 3) & ~3))`, wobei die Queue-Family-Records zuerst, danach alle Feature-Records und zuletzt alle Extension-Records folgen. Der Request muss exakt dieser Länge entsprechen; zusätzliche oder fehlende Bytes ergeben `BadLength`.

`CreateDevice` ist ein Void-Request. Erfolgsfälle erzeugen keinen Reply; Fehler werden als normale X11-Fehler für diesen Request gemeldet. Die Fehlerzuordnung für unbekannte beziehungsweise nicht unterstützte Features und Extensions ist verbindlich in [Errors and error mapping](errors.md) festgelegt.

Ist das ausgewählte Physical Device nicht verfügbar, wird `DEVICE_UNAVAILABLE` als X11-Fehler gemeldet. Die Erstellung ist atomar: Bei einem Fehler darf kein teilweise erstelltes logisches Device zurückbleiben.

## `CreateDefaultDevice`

Request:

- Offset 8: `XID device_xid`
- Offset 12: `CARD16 queue_count`
- Offset 14: `CARD16 reserved = 0`
- Offset 16: `FLOAT32 priorities[queue_count]`

Gesamtlänge: `16 + 4 * queue_count`.

Die Queue-Anzahl muss mindestens 1 betragen. Alle Prioritäten müssen endlich und im Intervall [0,1] liegen; andernfalls wird `BadValue` gemeldet. Das reservierte Feld muss null sein. Der Server wählt ein geeignetes Physical Device und eine Compute-fähige Queue Family. Es werden keine optionalen Features oder Extensions implizit aktiviert.

`CreateDefaultDevice` ist ein Void-Request. Falls kein geeignetes Gerät existiert, meldet der Server den XAverius-X11-Fehler `DEVICE_UNAVAILABLE`; es gibt keinen normalen Reply.

## `DestroyDevice`

`DestroyDevice` ist ein Void-Request mit fester Gesamtlänge von 12 Bytes: Device-XID bei Offset 8. Die XID muss ein logisches Device sein, das dieser Client-Verbindung gehört. Eine unbekannte/nicht-live XID ergibt `BadValue`; ein falscher live Ressourcentyp oder fremde Ownership ergibt `BadMatch`. Bei Device Loss darf die Bereinigung nach den Lebensdauerregeln fortgesetzt werden.

Bei erfolgreichem Request werden die öffentliche Device-XID und alle öffentlichen XIDs seiner Ressourcen sofort ungültig.

Interne Vulkan-Objekte werden erst freigegeben, wenn die Vulkan-Lebensdauerregeln und alle ausstehenden Abhängigkeiten dies erlauben.

Die erfolgreiche Zerstörung bedeutet weder, dass die GPU-Arbeit abgeschlossen ist, noch dass das Device auf ein anderes Physical Device umgeleitet wurde.

## Physische Devices

Physical-Device-XIDs werden serverseitig vergeben.

- Clients dürfen Physical-Device-XIDs nicht zerstören.
- Ein bestehender XID darf niemals einem anderen Physical-Device-Objekt zugewiesen werden.
- Bei Entfernung oder Ausfall bleibt die Identität erhalten; der Status ändert sich.
- Die Sichtbarkeit eines Physical Devices garantiert nicht, dass ein logisches Device darauf erstellt werden darf.
- Die konkrete Nutzungsberechtigung wird separat geprüft.

## Device-Ownership

Jede logische Device-Ressource gehört genau einem logischen Device.

Cross-Device-Nutzung ergibt normalerweise `BadMatch`, auch wenn beide logischen Devices dasselbe physische GPU-Gerät verwenden.

Ein Ressourcen-Request muss prüfen:

1. Existenz und Typ der XID,
2. Client-Ownership,
3. Device-Zugehörigkeit,
4. Ressourcenzustand,
5. Request-spezifische Vulkan-Bedingungen.

Die allgemeine XID-Fehlerzuordnung ist in [Errors and error mapping](errors.md) verbindlich festgelegt. Request-spezifische Zusatzregeln dürfen diese Grundzuordnung nur ausdrücklich erweitern, nicht stillschweigend überschreiben.
