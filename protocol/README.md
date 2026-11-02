XAverius shared protocol headers
================================

This directory contains implementation-neutral C wire declarations shared by X server and client code.

- include/xaveriusconst.h: stable request, event, error, flag and registry values.
- include/xaveriusproto.h: request, reply, event and nested-record wire structures plus fixed-size constants.
- include/xaverius.h: umbrella include.

Add protocol/include to the compiler include path and include <xaverius.h>. Discover the dynamic extension major opcode with X11 QueryExtension; it is not a compile-time constant. Multi-byte fields use the X11 connection byte order. These declarations describe wire offsets, not host-order accessors; use X11 byte-order helpers when encoding and decoding.

Variable-length structures use a one-element trailing member for compatibility with traditional X11 protocol headers. sz_xav* constants describe the fixed prefix. Calculate actual sizes with checked arithmetic and enforce XAV_MAX_REQUEST_BYTES; never use sizeof(struct) as the size of a variable-length packet.

The structures are packed to four-byte alignment because some XGE 64-bit fields occur at offsets that are four-byte aligned but not eight-byte aligned. The normative source remains spec/ and registries/. Update these headers together with any normative wire-layout or registry change. No server implementation behavior or Vulkan handles are defined here.
