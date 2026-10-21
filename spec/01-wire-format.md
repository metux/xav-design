# 2. X11-Framing

## 2.1 Request-Header

Jeder XAverius-Request beginnt mit dem Standard-X11-Request-Header von vier Bytes. Direkt danach folgt der XAverius-Common-Header.

```c
/* X11 header: offset 0 */
CARD8  reqType;       /* Extension major opcode */
CARD8  data;          /* X11 request framing */
CARD16 length;        /* Request length in 4-byte units */

/* XAverius header: offset 4 */
CARD8  subopcode;     /* Centrally assigned request ID */
CARD8  flags;         /* Request-specific flags */
CARD16 reserved;      /* MUST be zero in v0.1 */
```

Der Common-Header ist vier Bytes groß; der gesamte feste XAverius-Request-Header ist damit acht Bytes groß. Der Request-Payload beginnt grundsätzlich bei Offset 8, sofern ein Request nichts anderes festlegt.

Die X11-Verbindungsbyteordnung gilt für sämtliche mehrbyteigen Wire-Felder.

Der X-Server weist die Extension-Major-Opcode zu. XAverius verwendet zentral vergebene Minor- beziehungsweise Subopcode-Werte.

## 2.2 Längen, Padding und BIG-REQUESTS

- X11-Request-Längen werden in Einheiten von vier Bytes angegeben.
- Variable Bytefelder werden auf vier Bytes aufgerundet und mit Nullbytes aufgefüllt.
- Padding muss null sein.
- Ein inkonsistentes Request-Layout oder ein nicht passender Payload-Umfang ergibt `BadLength`.
- Ungültige Werte oder reservierte Bits ergeben normalerweise `BadValue`.
- BIG-REQUESTS folgt den Standard-X11-Regeln.
- Ohne BIG-REQUESTS beträgt die maximale gewöhnliche Request-Länge 262140 Bytes einschließlich Header.
- Größenberechnungen müssen vor der Verarbeitung auf Überläufe geprüft werden.

Ein Server darf variable Payloads nicht auf Grundlage ungeprüfter Counts allokieren.

## 2.3 Replies

Replies verwenden den Standard-X11-Reply-Header von 32 Bytes. `reply.length` gibt die Anzahl der Vierbyteeinheiten nach diesem Header an.

Wenn ein Reply einen variablen Payload enthält, beginnt dieser grundsätzlich bei Offset 32.

Nicht verwendete Felder müssen entsprechend der jeweiligen Reply-Definition null sein.

## 2.4 Fehler

XAverius-spezifische Fehler verwenden den standardisierten 32-Byte-X11-Error-Packet-Aufbau. XAverius definiert keine zusätzlichen Fehler-Payload-Bytes.

Der absolute Fehlercode ist:

`first_error + XAverius_error_offset`

Der Fehler muss mit der ursprünglichen Request-Sequenznummer korreliert werden.

## 2.5 XGE-Events

XAverius-Events verwenden X Generic Events (XGE). Der Standard-XGE-Header ist 32 Bytes lang. Event-spezifische Felder beginnen bei Offset 32.

Das XGE-Feld `length` zählt Vierbyteeinheiten nach dem ersten 32-Byte-Header.

# 3. Wire-Typen, XIDs und Ownership

## 3.1 Primitive Typen

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

## 3.2 Client-Ressourcen

Client-erzeugte XAverius-Ressourcen verwenden gültige, vom Client allokierbare XIDs.

Ein ungültiger oder bereits belegter Create-XID ergibt `BadIDChoice`, sofern der jeweilige Request keine speziellere X11-Regel vorschreibt.

Der Server muss für jede Ressource eine interne Identität verwalten, die nicht allein aus der öffentlichen XID besteht. Dadurch darf eine spätere Wiederverwendung derselben XID niemals laufende Arbeit auf eine neue Ressource umleiten.

Eine erfolgreich zerstörte öffentliche Ressource ist für neue Requests nicht mehr adressierbar.

## 3.3 Physische Devices

Physical-Device-XIDs werden serverseitig vergeben.

- Clients dürfen Physical-Device-XIDs nicht zerstören.
- Ein bestehender XID darf niemals einem anderen Physical-Device-Objekt zugewiesen werden.
- Bei Entfernung oder Ausfall bleibt die Identität erhalten; der Status ändert sich.
- Die Sichtbarkeit eines Physical Devices garantiert nicht, dass ein logisches Device darauf erstellt werden darf.
- Die konkrete Nutzungsberechtigung wird separat geprüft.

## 3.4 Device-Ownership

Jede logische Device-Ressource gehört genau einem logischen Device.

Cross-Device-Nutzung ergibt normalerweise `BadMatch`, auch wenn beide logischen Devices dasselbe physische GPU-Gerät verwenden.

Ein Ressourcen-Request muss prüfen:

1. Existenz und Typ der XID,
2. Client-Ownership,
3. Device-Zugehörigkeit,
4. Ressourcenzustand,
5. Request-spezifische Vulkan-Bedingungen.

Die exakte Reihenfolge und Zuordnung der X11-Fehler muss requestweise festgelegt werden.
