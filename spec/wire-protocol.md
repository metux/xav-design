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

The X server dynamically assigns the extension major opcode from the X11 extension range 128–255. Clients MUST discover XAverius using the standard X11 `QueryExtension` request and use the returned major opcode; hard-coding the XAverius major opcode is forbidden. The same value appears in the X11 request header's `reqType` field and the XGE `extension` field. It is not a XAverius registry constant. In XAverius v0.1, the X11 request header's `data` field is always zero; a non-zero value MUST result in `BadValue` before subopcode dispatch, XID resolution, allocation, or state changes. The zero X11 `length` check for unsupported BIG-REQUESTS framing takes precedence and MUST still return `BadLength` before interpreting offset 4. Request identity is carried exclusively by the `subopcode` field at offset 4. Subopcodes are centrally registered; value `0` is reserved. Assigned subopcodes are stable and MUST NOT be reassigned or shifted by later extensions. Undefined requests have no implicit value. In a standard X11 error packet, the subopcode is zero-extended into `minorCode`; `majorCode` contains the extension major opcode. Clients MUST NOT interpret `data` as a subopcode.

## Common Request Validation Precedence

Every request follows this shared order before any request-specific state change:

1. Validate the X11 envelope independently of XAverius fields: a zero X11 `length` (unsupported BIG-REQUESTS framing), a packet/declared-length mismatch, a length beyond the ordinary X11 limit, or an overflow in envelope arithmetic results in `BadLength`. The zero-length case MUST be rejected before reading offset 4.
2. Validate the common-header fields that have invariant meanings: nonzero X11 `data` or nonzero common-header `reserved` results in `BadValue`. These checks precede subopcode dispatch, profile gating, request-specific parsing, XID lookup, allocation, and state changes. The `flags` byte at offset 5 is request-specific: its assigned bits are interpreted only after subopcode dispatch, and any bits reserved by that request must be zero. Thus a nonzero `data` or common `reserved` field takes precedence over an unsupported presentation subopcode; the zero-length/envelope `BadLength` checks above still take precedence over it.
3. Dispatch the subopcode and apply the profile gate. An unsupported presentation request returns `BadRequest` before parsing its request-specific payload, provided the envelope and common header are valid.
4. For a supported request, validate its exact layout, request-specific lengths/counts and checked arithmetic; these failures return `BadLength`. Then apply the request-specific order for scalar values, assigned `flags` bits, reserved fields, padding, XID resolution, ownership/type, lifecycle/device state, and backend operations. The default is scalar/reserved/padding validation before XID resolution, followed by ownership/type and state checks; a request chapter MAY explicitly reorder checks within these later phases where dependencies require it. Such an exception MUST state the affected checks and their precedence, and MUST NOT override phases 1–3.
5. No rejected request may allocate variable payload storage from unchecked counts, resolve XIDs before the required earlier phases pass, or partially change public or internal state.

This rule distinguishes envelope framing from request-specific exact-length validation: the former can be checked without interpreting the XAverius subopcode, while the latter requires dispatch. Request-specific precedence exceptions, such as the explicitly defined `CommandBufferData` ABORT behavior, apply only within the later phases and do not bypass the common envelope/header checks.

## Profile-Gated Requests

Subopcodes 1–40 form the compute-baseline profile. Subopcodes 41–47 are defined only by the presentation-capable profile. A server that does not implement that profile MUST reject a request with subopcode 41–47 using the core X11 error `BadRequest` before parsing its request-specific payload. It MUST NOT perform XID resolution, change state, or generate a normal reply for that request. A client can therefore probe profile support with a correctly framed `GetSurfaceCapabilities` request; `BadRequest` means presentation requests are unavailable on that server. A server that supports the profile processes these requests according to their definitions and ordinary error/reply rules.

This profile boundary does not change central subopcode assignments and does not implicitly enable presentation support. Compute-only servers MUST continue to treat command-entry ID 5, event-type IDs 7 and 8, and the associated queue-mask bits as unsupported.

## Lengths, Padding, and BIG-REQUESTS

- X11 request lengths are expressed in four-byte units.
- Variable byte fields are rounded up to a four-byte boundary and padded with zero bytes.
- Padding bytes MUST be zero. The receiver MUST validate padding bytes rather than silently ignoring non-zero padding; non-zero padding results in `BadValue`.
- The common-header `flags` byte at offset 5 and `reserved` CARD16 at offset 6, every request-specific reserved field, and every reserved bit MUST be zero unless a future protocol version explicitly assigns it a meaning. Receivers MUST reject non-zero reserved fields/bits with `BadValue` before XID resolution, resource allocation, or state changes. Reserved fields are not padding: each is a fixed-width wire field whose location and width remain part of the request layout.
- A request-specific layout MUST state the width and offset of each reserved field and MUST state the zero requirement. Any gap between fields MUST either be explicitly identified as reserved zero bytes or be accounted for by the variable-payload padding rule; undocumented holes are forbidden.
- An inconsistent request layout or a payload size that does not match the declared layout results in `BadLength`.
- Invalid values or reserved bits normally result in `BadValue`; non-zero padding and non-zero reserved fields/bits specifically result in `BadValue`.
- BIG-REQUESTS is not supported in v0.1. Its extended-length field is at offset 4, where it conflicts with the XAverius common header. Clients MUST NOT send XAverius requests in BIG-REQUESTS format. The server MUST reject a XAverius request whose X11 header `length` field is zero with `BadLength` before interpreting bytes at offset 4 as the XAverius subopcode, flags, or reserved field.
- Without BIG-REQUESTS, the maximum ordinary request length is 262140 bytes, including the complete request and both the X11 and XAverius headers. Larger payloads MUST be transferred in multiple requests where the request definition permits chunking.
- For every variable-length request, the server MUST calculate the expected total length using checked arithmetic. Arithmetic overflow, an expected length greater than 262140 bytes, an X11 length field of zero, or a mismatch among the declared length, counts, and actual packet end MUST result in `BadLength`. All length and count validation MUST finish before payload allocation, XID resolution, or state changes.
- Size calculations MUST be checked for overflow before processing.

A server MUST NOT allocate variable payloads based on unchecked counts. This rule applies even when a request-specific chapter does not repeat the maximum size. Chunked requests MUST limit each individual chunk; the maximum length applies per request, not to the entire logical shader or command-buffer recording.

## Replies

Replies use the standard 32-byte X11 reply header. `reply.length` gives the number of four-byte units following this header.

If a reply contains a variable payload, it begins at offset 32 unless the reply definition explicitly specifies otherwise.

Unused fields MUST be zero as specified by the corresponding reply definition.

## Errors

XAverius-specific errors use the standard 32-byte X11 error-packet layout. XAverius defines no additional error-payload bytes.

The absolute error code is:

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
