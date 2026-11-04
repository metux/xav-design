# XAverius client prototype

This directory contains the first buildable slice of the client-side protocol runtime. It is **not** a Vulkan ICD and does not yet implement the full request set.

## Design

- Transport: public XCB APIs only. The library accepts a caller-owned `xcb_connection_t *`; it does not open, close, or own the X connection.
- Extension discovery: `xcb_get_extension_data()` for `XAVERIUS`; the major opcode is discovered dynamically.
- XAverius framing: XCB's extension descriptor uses minor opcode `0`, leaving the X11 `data` byte zero. The first body byte is the XAverius subopcode at absolute request offset 4.
- Byte order: XCB wire scalars use the connection's negotiated client byte order; the runtime copies them into aligned host scalar objects. Wire XIDs and Atoms are CARD32 values.
- Replies: XCB's reply machinery is used; the runtime validates the standard 32-byte reply envelope and all variable-tail record bounds before exposing data.
- Ownership: the connection and its event queue belong to the caller. Returned device arrays and their names belong to the library and are released with `xav_free_physical_devices()`.

The shared wire declarations currently live in `protocol/include/xaverius.h`; the client includes that protocol header rather than maintaining duplicate ABI declarations.

## Build

Requires the XCB development package and a C11 compiler.

```sh
make -C client
make -C client check
```

The static library is `client/libxaverius-client.a`. Link with `-lxcb` and add `client/include` and `protocol/include` to the include path.

## Implemented API slice

1. Discover the extension and dynamic major opcode.
2. Send XAverius `QueryVersion` (subopcode 0), validate the reply envelope and reject incompatible major/older minor versions.
3. Send `EnumeratePhysicalDevices` (subopcode 1), validate every variable-length PHYSICALDEVICEINFO record, and return host-order records.

The runtime exposes xav_connection_negotiate_xge() for the standard Generic Event Extension GEQueryVersion request. Call it successfully before selecting XAverius XGE events or issuing CreateDevice. xav_connection_select_events() sends a checked SelectEvents request, and xav_event_decode() decodes all nine registered XAverius XGE event types. It accepts events already obtained from the caller-owned XCB event queue; it does not poll or consume that queue.

XCB's in-memory GE event representation includes an extra full_sequence CARD32 at offset 32. Consequently, the event-specific payload begins at byte 36 in the XCB event allocation even though it begins at byte 32 on the wire. The decoder accounts for this insertion, checks the exact registered payload length and all reserved bytes, and returns unknown event types without interpreting them. Decoded scalar fields are host-order. For an unknown event, the payload pointer is borrowed from the original XCB event and becomes invalid when that event is freed.

## Next slices

- Complete bootstrap: Atom interning, device-property and queue-family/memory queries.
- Device/resource wrappers, XID allocation, Buffer/Memory requests and checked variable-size encoders.
- Shader uploads, command recording, submission and asynchronous error correlation.
- Semaphore/fence APIs and event-driven completion.
- Presentation profile, separately gated by server capability.

A future Vulkan ICD should sit above this runtime. It should translate Vulkan handles, structures, flags and results into the client API; it should not duplicate XCB transport or wire encoding.
