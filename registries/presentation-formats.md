# Presentation format and mode registry

Status: **initial presentation-profile values assigned; not part of compute-only v0.1**.

These identifiers are XAverius wire values. They are not native Vulkan enum values and must not be cast to/from Vulkan enums without an explicit mapping. Value zero is reserved in each namespace. Assigned values are append-only.

## Pixel formats

| Value | Symbol | Meaning |
|---:|---|---|
| 1 | RGBA8_UNORM | Four 8-bit channels in R, G, B, A order; unsigned normalized components |
| 2 | BGRA8_UNORM | Four 8-bit channels in B, G, R, A order; unsigned normalized components |

The format names describe logical component order, not host byte order. Wire metadata uses the X11 connection byte order for integer fields; pixel storage follows the selected format's channel order and is not endian-swapped as a whole pixel.

## Color spaces

| Value | Symbol | Meaning |
|---:|---|---|
| 1 | SRGB_NONLINEAR | Standard sRGB nonlinear presentation color space |

A format/color-space pair is usable only if the queried Surface capabilities explicitly return that pair. The presence of an identifier in this registry does not require every server/backend to support it.

## Presentation modes

| Value | Symbol | Meaning |
|---:|---|---|
| 1 | FIFO | Presentations are queued in order; the presentation system does not intentionally replace a queued image with a later one before its turn |

FIFO is the baseline mode for a conforming presentation-capable profile. A server may report no presentation support for a given Device/Surface pair, but if it reports presentation support it must report FIFO as supported. Other modes may be appended later; clients must reject unknown values rather than infer semantics.

## Scope and compatibility

These registries define only pixel format, color space, and presentation mode identifiers. They do not yet define image usage bits, alpha-compositing policy, display timing, transforms, HDR metadata, or graphics command entries. Those must be specified separately before a complete image-rendering ABI is declared.
