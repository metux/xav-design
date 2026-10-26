# X11 Framing

## Request Header

Every XAverius request begins with the standard four-byte X11 request header, immediately followed by the XAverius common header.

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

The common header is four bytes, making the complete fixed XAverius request header eight bytes. Unless a request explicitly specifies otherwise, its payload begins at offset 8.

The X11 connection byte order applies to every multi-byte wire field.

The X server dynamically assigns the extension major opcode from the X11 extension range 128–255. Clients MUST discover XAverius using the standard X11 `QueryExtension` request and use the returned major opcode; hard-coding the XAverius major opcode is forbidden. The same value appears in the X11 request header's `reqType` field and the XGE `extension` field. It is not a XAverius registry constant. In XAverius v0.1, the X11 request header's `data` field is always zero; request identity is carried exclusively by the `subopcode` field at offset 4. Subopcodes are centrally registered; value `0` is reserved. Assigned subopcodes are stable and MUST NOT be reassigned or shifted by later extensions. Undefined requests have no implicit value. In a standard X11 error packet, the subopcode is zero-extended into `minorCode`; `majorCode` contains the extension major opcode. Clients MUST NOT interpret `data` as a subopcode.

## Profile-Gated Requests

Subopcodes 1–40 form the compute-baseline profile. Subopcodes 41–47 are defined only by the presentation-capable profile. A server that does not implement that profile MUST reject a request with subopcode 41–47 using the core X11 error `BadRequest` before parsing its request-specific payload. It MUST NOT perform XID resolution, change state, or generate a normal reply for that request. A client can therefore probe profile support with a correctly framed `GetSurfaceCapabilities` request; `BadRequest` means presentation requests are unavailable on that server. A server that supports the profile processes these requests according to their definitions and ordinary error/reply rules.

This profile boundary does not change central subopcode assignments and does not implicitly enable presentation support. Compute-only servers MUST continue to treat command-entry ID 5, event-type IDs 7 and 8, and the associated queue-mask bits as unsupported.

## Lengths, Padding, and BIG-REQUESTS

- X11-Request-Längen werden in Einheiten von vier Bytes angegeben.
- Variable Bytefelder werden auf vier Bytes aufgerundet und mit Nullbytes aufgefüllt.
- Padding muss null sein.
- An inconsistent request layout or a payload size that does not match the declared layout results in `BadLength`.
- Invalid values or reserved bits normally result in `BadValue`.
- BIG-REQUESTS is not supported in v0.1. Its extended-length field is at offset 4, where it conflicts with the XAverius common header. Clients MUST NOT send XAverius requests in BIG-REQUESTS format. The server MUST reject a XAverius request whose X11 header `length` field is zero with `BadLength` before interpreting bytes at offset 4 as the XAverius subopcode, flags, or reserved field.
- Without BIG-REQUESTS, the maximum ordinary request length is 262140 bytes, including the complete request and both the X11 and XAverius headers. Larger payloads MUST be transferred in multiple requests where the request definition permits chunking.
- For every variable-length request, the server MUST calculate the expected total length using checked arithmetic. Arithmetic overflow, an expected length greater than 262140 bytes, an X11 length field of zero, or a mismatch among the declared length, counts, and actual packet end MUST result in `BadLength`. All length and count validation MUST finish before payload allocation, XID resolution, or state changes.
- Size calculations MUST be checked for overflow before processing.

A server MUST NOT allocate variable payloads based on unchecked counts. This rule applies even when a request-specific chapter does not repeat the maximum size. Chunked requests MUST limit each individual chunk; the maximum length applies per request, not to the entire logical shader or command-buffer recording.

## Replies

Replies verwenden den Standard-X11-Reply-Header von 32 Bytes. `reply.length` gibt die Anzahl der Vierbyteeinheiten nach diesem Header an.

Wenn ein Reply einen variablen Payload enthält, beginnt dieser grundsätzlich bei Offset 32.

Nicht verwendete Felder müssen entsprechend der jeweiligen Reply-Definition null sein.

## Errors

XAverius-specific errors use the standard 32-byte X11 error-packet layout. XAverius defines no additional error-payload bytes.

Der absolute Fehlercode ist:

`first_error + XAverius_error_offset`

The error MUST be correlated with the original request sequence number. The error packet sets `majorCode` to the XAverius extension major opcode and `minorCode` to the zero-extended XAverius `subopcode` of the failing request.

## XGE Events

XAverius events use X Generic Events (XGE). The standard XGE header is 32 bytes long; event-specific fields begin at offset 32. In the XGE header, `extension` contains the dynamically assigned XAverius major opcode, and `evtype` contains the static CARD16 event-type ID from the event registry. The core event code is `GenericEvent = 35`; XAverius has no separately assigned server-side XGE event base.

The XGE `length` field counts four-byte units after the initial 32-byte header. Before sending a longer event, the server must know that the receiving client supports XGE. XAverius therefore requires successful XGE 1.0 negotiation on each connection before creating a logical device or issuing `SelectEvents`; request-specific rules are defined in [Events](events.md).

## Primitive Types

| Wire Type | Meaning |
|---|---|
| `CARD8` | Unsigned 8-bit |
| `CARD16` | Unsigned 16-bit |
| `CARD32` | Unsigned 32-bit |
| `CARD64` | Unsigned 64-bit |
| `FLOAT32` | IEEE-754 binary32 |
| `BYTE[n]` | Bytefolge mit expliziter Länge |
| `XID` | 32-bit X11 Resource ID |
| `ATOM` | X11 Atom-ID |

Null termination is used only when a field definition explicitly requires it.
