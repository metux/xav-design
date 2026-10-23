# Presentation-profile event registry

Status: future presentation-capable profile; not part of compute-only v0.1.

These event IDs extend the XAverius XGE event-type namespace without changing the compute-only v0.1 event registry. IDs are append-only and must not be renumbered or reused. They are valid only when the server advertises the presentation-capable profile.

## Event type IDs

| Value | Symbol |
|---:|---|
| 7 | `IMAGE_RELEASED` |
| 8 | `PRESENTATION_COMPLETE` |

## Presentation event status values

| Value | Symbol |
|---:|---|
| 0 | SUCCESS |
| 1 | OUT_OF_DATE |
| 2 | SURFACE_LOST |
| 3 | DEVICE_LOST |
| 4 | PRESENTATION_FAILED |

These values are local to the presentation event status field. They are not X11 error codes or XAverius error offsets. A compute-only server must not emit these event types and must reject the presentation-only queue event-mask bits.
