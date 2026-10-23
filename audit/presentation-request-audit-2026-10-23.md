# XAverius Presentation Request Audit

**Branch:** `docs/restructure-2026-10-21`  
**Audit date:** 2026-10-23  
**Scope:** Presentation requests targeting server-side X11 Windows; wire layouts, error precedence, status replies, and atomic state transitions.

## Current result

The active branch defines these seven presentation requests in `spec/presentation.md`:

1. `CreateSurface`
2. `DestroySurface`
3. `GetSurfaceCapabilities`
4. `CreateSwapchain`
5. `DestroySwapchain`
6. `AcquireNextImage`
7. `QueuePresent`

Their numeric request subopcodes remain unassigned. The presentation-capable profile is not part of the compute-only baseline.

## Verified wire-length matrix

Request lengths include the 8-byte request header. Reply lengths include the standard 32-byte X11 reply header.

| Request | Request length | Reply length |
|---|---:|---:|
| `CreateSurface` | 16 bytes | none |
| `DestroySurface` | 12 bytes | none |
| `GetSurfaceCapabilities` | 16 bytes | 64 bytes plus variable records |
| `CreateSwapchain` | 48 bytes | 40 bytes |
| `DestroySwapchain` | 12 bytes | none |
| `AcquireNextImage` | 32 bytes | 44 bytes |
| `QueuePresent` | 40 + 4 × `wait_semaphore_count` bytes | 36 bytes |

The request/reply heading errors in `spec/presentation.md` were corrected, and matching framing tables and conformance requirements were added to `spec/conformance.md`.

## Cross-chapter semantic checks

The inspected normative chapters establish these requirements:

- Framing and checked arithmetic precede scalar validation, XID resolution, and state checks.
- Scalar syntax and reserved fields are validated before XID resolution. Create-XID checks and input-XID checks follow each request's documented field order.
- Resource type, ownership, and Device state are checked before lifecycle/status and mutable synchronization-state checks.
- `QueuePresent` acceptance atomically reserves the unique token and each wait slot, retains required resources, and transitions the image from `ACQUIRED` to `PRESENT_PENDING`. Rejection does none of those things.
- A successful `QueuePresent` reply means accepted, not displayed. Image release and presentation completion are separate terminal milestones/events.
- Resize, Surface loss, and Device loss prevent new work as specified while previously accepted operations are terminalized exactly once; lifecycle transitions are not rolled back by rejected requests.
- `DestroySwapchain` rejects while recording references, pending acquisition, accepted queue/presentation work, or backend access can still use its images. An acquired-but-idle image alone does not block destruction.
- Presentation event types 7 and 8 are each 64 bytes (XGE length 8), with event-local status values defined separately from request reply statuses and X11 error offsets.

## Concrete correction made during this pass

The wire-layout section stated that, after review, the seven requests would be appended specifically as subopcodes 41–47. That prematurely implied a numeric allocation while the same chapter said the requests remained unassigned. The text now requires assignment through the central append-only registry only after review and does not presume a numeric range; other requests may be assigned first.

## CI/checker status

The repository records a successful earlier wire-layout run, [39950681596](https://github.com/metux/xav-design/actions/runs/39950681596), whose `wire-layout` job passed syntax checks, request/reply/XGE validation, and 119 golden-wire tests. That run predates the latest presentation audit edits and does not validate these commits. The current commits returned no combined status entries, and the available workflow-run lookup did not expose a run for them. Therefore current-commit CI remains **unverified**; an empty status response is not evidence that the checker passed.

## Remaining work

1. Locate and execute the existing static checker against the current presentation layouts and conformance rules.
2. Run or trigger CI and inspect actual job results; do not infer success from an empty status response.
3. Resolve any checker or cross-chapter contradictions before assigning request subopcodes.
4. Keep `master` unchanged; all edits in this audit are on `docs/restructure-2026-10-21`.
