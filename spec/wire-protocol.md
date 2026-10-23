# X11-Framing

## Request-Header

Jeder XAverius-Request beginnt mit dem Standard-X11-Request-Header von vier Bytes. Direkt danach folgt der XAverius-Common-Header.

```c
/* X11 header: offset 0 */
CARD8  reqType;       /* Extension major opcode */
CARD8  data;          /* MUST be zero for XAverius v0.1 */
CARD16 length;        /* Request length in 4-byte units */

/* XAverius header: offset 4 */
CARD8  subopcode;     /* Centrally assigned request ID */
CARD8  flags;         /* Request-specific flags */
CARD16 reserved;      /* MUST be zero in v0.1 */
```

Der Common-Header ist vier Bytes groß; der gesamte feste XAverius-Request-Header ist damit acht Bytes groß. Der Request-Payload beginnt grundsätzlich bei Offset 8, sofern ein Request nichts anderes festlegt.

Die X11-Verbindungsbyteordnung gilt für sämtliche mehrbyteigen Wire-Felder.

Der X-Server weist die Extension-Major-Opcode dynamisch aus dem X11-Erweiterungsbereich 128–255 zu. Clients MUST XAverius mit der standardmäßigen X11-`QueryExtension`-Anfrage entdecken und den zurückgegebenen Major-Opcode verwenden; ein fest codierter XAverius-Major-Opcode ist unzulässig. Derselbe Wert steht im X11-Request-Header `reqType` und im XGE-Feld `extension`. Er ist keine XAverius-Registry-Konstante. Für XAverius v0.1 ist das X11-Request-Header-Feld `data` immer null; die Request-Identität steht ausschließlich im `subopcode`-Feld bei Offset 4. Der `subopcode` ist zentral registriert; Wert `0` ist reserviert. Bereits vergebene Subopcodes sind stabil und dürfen bei späteren Erweiterungen nicht neu vergeben oder verschoben werden. Nicht definierte Requests besitzen keinen impliziten Wert. In einem standardmäßigen X11-Error-Packet wird dieser Wert zero-extended in `minorCode` eingetragen. `majorCode` enthält den Extension-Major-Opcode. Clients dürfen `data` nicht als Subopcode interpretieren.

## Längen, Padding und BIG-REQUESTS

- X11-Request-Längen werden in Einheiten von vier Bytes angegeben.
- Variable Bytefelder werden auf vier Bytes aufgerundet und mit Nullbytes aufgefüllt.
- Padding muss null sein.
- Ein inkonsistentes Request-Layout oder ein nicht passender Payload-Umfang ergibt `BadLength`.
- Ungültige Werte oder reservierte Bits ergeben normalerweise `BadValue`.
- BIG-REQUESTS wird in v0.1 nicht unterstützt. Sein Extended-Length-Feld liegt bei Offset 4 und kollidiert dort mit dem XAverius-Common-Header. Clients MUST NOT senden XAverius-Requests im BIG-REQUESTS-Format. Der Server MUST eine XAverius-Anfrage mit dem X11-Headerfeld `length = 0` als `BadLength` zurückweisen, bevor er Bytes ab Offset 4 als XAverius-Subopcode, Flags oder reserviertes Feld interpretiert.
- Ohne BIG-REQUESTS beträgt die maximale gewöhnliche Request-Länge 262140 Bytes einschließlich des gesamten Requests, also einschließlich X11- und XAverius-Header. Größere Nutzdaten müssen in mehreren Requests übertragen werden, soweit der jeweilige Request dies erlaubt.
- Für jeden Request mit variabler Länge MUSS der Server die erwartete Gesamtlänge mit geprüfter Arithmetik berechnen. Ein arithmetischer Überlauf, eine erwartete Länge über 262140 Bytes, ein X11-Längenfeld von null oder eine Abweichung zwischen deklarierter Länge, Counts und tatsächlichem Paketende MUSS zu `BadLength` führen. Die vollständige Längen-/Count-Prüfung MUSS vor Payload-Allokation, XID-Auflösung und Zustandsänderungen abgeschlossen sein.
- Größenberechnungen müssen vor der Verarbeitung auf Überläufe geprüft werden.

Ein Server darf variable Payloads nicht auf Grundlage ungeprüfter Counts allokieren. Diese Grenze gilt auch dann, wenn das request-spezifische Kapitel die Maximalgröße nicht wiederholt. Chunk-basierte Requests müssen stattdessen die jeweilige Chunk-Länge begrenzen; die maximale Länge gilt pro Request, nicht für die gesamte logische Shader- oder Command-Buffer-Aufzeichnung.

## Replies

Replies verwenden den Standard-X11-Reply-Header von 32 Bytes. `reply.length` gibt die Anzahl der Vierbyteeinheiten nach diesem Header an.

Wenn ein Reply einen variablen Payload enthält, beginnt dieser grundsätzlich bei Offset 32.

Nicht verwendete Felder müssen entsprechend der jeweiligen Reply-Definition null sein.

## Fehler

XAverius-spezifische Fehler verwenden den standardisierten 32-Byte-X11-Error-Packet-Aufbau. XAverius definiert keine zusätzlichen Fehler-Payload-Bytes.

Der absolute Fehlercode ist:

`first_error + XAverius_error_offset`

Der Fehler muss mit der ursprünglichen Request-Sequenznummer korreliert werden. Das Error-Packet setzt `majorCode` auf den XAverius-Extension-Major-Opcode und `minorCode` auf den zero-extended XAverius-`subopcode` des fehlerhaften Requests.

## XGE-Events

XAverius-Events verwenden X Generic Events (XGE). Der Standard-XGE-Header ist 32 Bytes lang. Event-spezifische Felder beginnen bei Offset 32. Im XGE-Header enthält `extension` den dynamisch zugewiesenen XAverius-Major-Opcode und `evtype` die statische CARD16-Event-Type-ID aus der Event-Registry. Der Core-Eventcode ist `GenericEvent = 35`; XAverius besitzt kein eigenes serverseitig zugewiesenes XGE-Event-Base.

Das XGE-Feld `length` zählt Vierbyteeinheiten nach dem ersten 32-Byte-Header. Vor dem Versand eines längeren Events muss der Server wissen, dass der empfangende Client XGE unterstützt. XAverius verlangt daher erfolgreiche XGE-1.0-Aushandlung pro Verbindung vor dem Erzeugen eines logischen Devices oder vor `SelectEvents`; die request-spezifischen Regeln stehen in [Events](events.md).

## Primitive Typen

| Wire-Typ | Bedeutung |
|---|---|
| `CARD8` | Unsigned 8-bit |
| `CARD16` | Unsigned 16-bit |
| `CARD32` | Unsigned 32-bit |
| `CARD64` | Unsigned 64-bit |
| `FLOAT32` | IEEE-754 binary32 |
| `BYTE[n]` | Bytefolge mit expliziter Länge |
| `XID` | 32-bit X11 Resource ID |
| `ATOM` | X11 Atom-ID |

Nullterminierung wird nur verwendet, wenn eine Felddefinition dies ausdrücklich verlangt.
