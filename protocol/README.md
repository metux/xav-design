XAverius shared protocol header
================================

This directory contains the implementation-neutral C wire declarations shared by X server and client code.

- `include/xaverius.h` is the single public header. It contains all request subopcodes, event IDs, error codes, flags, registry values, request/reply/event structures, nested variable-tail records, and fixed-size constants.

The build environment must provide the X11 protocol headers (`X.h` and `Xmd.h`; on Debian-family systems install `libx11-dev` or the xproto development package). Add `protocol/include` to the compiler include path and include `<xaverius.h>`.

Discover the dynamic extension major opcode with X11 `QueryExtension`; it is not a compile-time constant. Multi-byte fields use the X11 connection byte order. These declarations describe wire offsets, not host-order accessors; use X11 byte-order helpers when encoding and decoding. Wire XIDs and Atom IDs are represented as `CARD32`, independent of the host Xlib typedef widths.

All wire structures use four-byte packing. Do not cast arbitrary network buffers to these structures on architectures or compilers where unaligned access is unsafe; copy fields or use suitable accessors. Variable-tail replies and records must be sized from their explicit counts and lengths with overflow checks before allocation or access. The ordinary X11 request length limit applies; BIG-REQUESTS is not part of this protocol.

The normative source remains the specification under `spec/` and the registries under `registries/`. Update those first when changing the ABI, then keep this header synchronized.
