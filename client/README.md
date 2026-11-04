# XAverius client prototype

This directory is an initial, deliberately small client-side protocol runtime. It is **not** a Vulkan ICD and does not implement Vulkan dispatchable handles or the full request set yet.

## Design

- Transport: public XCB APIs only. The library accepts a caller-owned `xcb_connection_t *`; it does not open, close, or own the X connection.
- Extension discovery: `xcb_get_extension_data()` for `XAVERIUS`; the major opcode is always discovered, never compiled in.
- XAverius framing: XCB's request descriptor uses minor opcode `0`, so the X11 `data` byte is zero. The first four body bytes are the XAverius common header: subopcode, flags, reserved. In other words, the subopcode remains at absolute request offset 4 as required by the spec.
- Byte order: all multi-byte fields are decoded explicitly using the connection setup's image byte order. Wire XIDs/Atoms remain CARD32 values.
- Replies: use XCB's sequence/reply machinery and validate the complete reply envelope and variable-tail bounds before exposing data.
- Ownership: the connection and its event queue belong to the caller. Returned device arrays belong to the client library and are released with `xav_free()`.

The shared wire declarations currently live in `protocol/include/xaverius_proto.h`; the client includes that single protocol header rather than maintaining duplicate ABI declarations.

## Build

Requires the XCB development package and a C11 compiler.

```sh
make
make check
```

The static library is `libxaverius-client.a`. Link with `-lxcb` and add `client/include` and `protocol/include` to the include path.

## Phase 1 API implemented here

1. Discover the extension with XCB.
2. Send XAverius `QueryVersion` (subopcode 0), validate the reply and reject incompatible major/older minor versions.
3. Send `EnumeratePhysicalDevices` (subopcode 1), validate the X11 reply envelope and every variable-length PHYSICALDEVICEINFO record, and return host-order records.

The prototype intentionally leaves logical-device creation and XGE negotiation for the next implementation slice. In particular, `CreateDevice` requires successful XGE 1.0+ negotiation and must not be exposed as a successful operation before that prerequisite is met.

## Next slices

- Phase 1 completion: XGE `GEQueryVersion`, event dispatcher, Atom interning and device-property/memory/queue-family queries.
- Phase 2: device/resource wrapper objects, XID allocation, Buffer/Memory requests and checked variable-size encoders.
- Phase 3: shader uploads, command recording, submission and asynchronous error correlation.
- Phase 4: semaphore/fence APIs and event-driven completion.
- Phase 5: presentation profile, separately gated by server capability.

The future Vulkan ICD should sit above this runtime. It should translate Vulkan handles, structures, flags and results into the client API; it should not duplicate XCB transport or wire encoding.
