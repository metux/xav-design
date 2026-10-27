# XAverius Presentation Request Audit

**Branch:** `docs/restructure-2026-10-21`  
**Audit date:** 2026-10-27  
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

The wire-layout text and static checker define 41–47 as the planned append-only assignments after the final semantic review. Those values remain prospective, not allocated or reserved: the requests must not be advertised or used under those values until the corresponding rows are committed to the central registry. The normative text now distinguishes that planned mapping from an actual registry allocation.

## CI/checker status

The current branch head `a60d8c1ba2c902181ced1f561cb48301767d3af7` has a successful `wire-layout` workflow run, [40482324248](https://github.com/metux/xav-design/actions/runs/40482324248), completed 2026-10-27 09:38:40 UTC. The workflow syntax-checks the checker and wire tests, runs `tools/check-wire-layout.py`, runs Timeline semaphore regressions, and executes the full `unittest` suite. The latest run is green; earlier runs 1522–1531 failed while incremental assertions were being reconciled, then subsequent commits passed. This confirms the workflow result for the branch head, not implementation against a running X server (the tests are specification-contract and wire-fixture tests).

## Remaining work

1. Keep presentation subopcodes 41–47 and command-entry ID 5 prospective until the design decision to include presentation in the profile is explicitly made and the central registries are intentionally updated.
2. Continue cross-checking request/reply/XGE/error/register coverage against normative chapters; passing static tests establishes consistency with the current contract, not completeness of the design itself.
3. Preserve the distinction between presentation completion, image release, and actual runtime/server behavior; no running X server or GPU backend is exercised by this workflow.
4. Keep `master` unchanged; all edits in this audit are on `docs/restructure-2026-10-21`.
