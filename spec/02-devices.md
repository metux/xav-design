# 4. Device-Discovery und logische Devices

## 4.1 Device-Auswahl

Es gibt zwei Pfade:

1. `CreateDefaultDevice`: Der Server wählt ein geeignetes Physical Device und erstellt ein logisches Device.
2. Explizite Auswahl: `EnumeratePhysicalDevices`, Eigenschaftsabfragen und `GetPhysicalDeviceQueueFamilyProperties`, danach `CreateDevice`.

Queues werden nicht über Queue-XIDs adressiert. Eine Queue wird über das Tupel

`(device_xid, queue_family_index, queue_index)`

identifiziert.

Der Queue-Family-Index entspricht der Reihenfolge der zurückgegebenen Queue-Family-Liste. Der Queue-Index adressiert eine tatsächlich für diese Familie angeforderte Queue.

## 4.2 `EnumeratePhysicalDevices`

Der Reply enthält nach dem 32-Byte-X11-Header direkt null oder mehr `PHYSICALDEVICEINFO`-Records. Es gibt kein zusätzliches Device-Count-Feld.

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

## 4.3 `GetPhysicalDeviceProperty`

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

- `SUCCESS`
- `NOT_SUPPORTED`
- `NOT_AVAILABLE`

Bei einem Status ungleich `SUCCESS` müssen `property_type` und `value_length` null sein und der Reply enthält keinen Wert-Payload.

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

## 4.4 `GetPhysicalDeviceQueueFamilyProperties`

Request: Physical-Device-XID bei Offset 8, Gesamtlänge 12 Bytes.

Reply: Standard-Reply-Header plus `QUEUEFAMILYINFO`-Records mit je 12 Bytes.

| Relativer Offset | Typ | Feld |
|---:|---|---|
| 0 | CARD32 | `queue_flags` |
| 4 | CARD32 | `queue_count` |
| 8 | CARD32 | `reserved = 0` |

Die Records folgen der Vulkan-Reihenfolge. Die Payload-Länge muss durch 12 teilbar sein.

Queue-Flag-Bits:

- Bit 0: `GRAPHICS`
- Bit 1: `COMPUTE`
- Bit 2: `TRANSFER`
- Bit 3: `SPARSE_BINDING`
- Bit 4: `PROTECTED`
- Bits 5–31: reserviert

## 4.5 `CreateDevice`

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

Die Anzahl muss positiv und unterstützt sein. Prioritäten müssen endlich und im Intervall [0,1] liegen. Doppelte Queue-Family-Einträge sind unzulässig.

`DEVICEFEATUREREQUEST`:

- `CARD32 feature_id`
- `CARD32 enabled`

Größe: 8 Bytes. In v0.1 muss `enabled = 1` sein. Nicht angegebene Features werden nicht angefordert. Doppelte Feature-IDs sind ungültig.

`DEVICEEXTENSIONREQUEST`:

- `CARD16 name_length`
- `CARD16 reserved = 0`
- ASCII-Extension-Name ohne NUL, auf vier Bytes gepaddet

Größe: `4 + ((name_length + 3) & ~3)`.

Doppelte Extensions sind unzulässig. Feature-IDs und Extensions werden über zentrale Registries definiert.

Die Erstellung ist atomar: Bei einem Fehler darf kein teilweise erstelltes logisches Device zurückbleiben.

## 4.6 `CreateDefaultDevice`

Request:

- Offset 8: `XID device_xid`
- Offset 12: `CARD16 queue_count`
- Offset 14: `CARD16 reserved = 0`
- Offset 16: `FLOAT32 priorities[queue_count]`

Gesamtlänge: `16 + 4 * queue_count`.

Die Queue-Anzahl muss mindestens 1 betragen. Der Server wählt ein geeignetes Physical Device und eine Compute-fähige Queue Family. Es werden keine optionalen Features oder Extensions implizit aktiviert.

Falls kein geeignetes Gerät existiert, wird `DEVICE_UNAVAILABLE` zurückgegeben.

## 4.7 `DestroyDevice`

Bei erfolgreichem Request werden die öffentliche Device-XID und alle öffentlichen XIDs seiner Ressourcen sofort ungültig.

Interne Vulkan-Objekte werden erst freigegeben, wenn die Vulkan-Lebensdauerregeln und alle ausstehenden Abhängigkeiten dies erlauben.

Die erfolgreiche Zerstörung bedeutet weder, dass die GPU-Arbeit abgeschlossen ist, noch dass das Device auf ein anderes Physical Device umgeleitet wurde.
