# On-screen presentation in X11 windows

Status: **ownership/lifecycle and initial format/mode IDs defined; capability wire layout, request layouts, and numeric assignments remain provisional**.

This chapter extends the compute-oriented v0.1 design toward presentation into ordinary X11 windows. It does not change existing compute request contracts, queue semantics, or resource ownership rules. The initial implementation may remain compute-only; this chapter establishes the direction for a later presentation-capable profile.

## 1. Architectural model

XAverius presentation is server-side. The client creates and manages an ordinary X11 window through the normal X11 core protocol, then identifies that window to XAverius by its XID. XAverius does not create a second, client-native Vulkan window surface and does not require the client to use a platform-specific Vulkan WSI extension.

The server owns the presentation implementation and is responsible for connecting the logical XAverius surface to the named X11 window. The backend may use a native Vulkan WSI path when the server's Vulkan implementation supports a suitable X11 target. Otherwise it may use server-managed Vulkan images and an internal copy, blit, or composition path into the X11 window. These are implementation alternatives: the externally observable contract is presentation in the selected X11 window, not use of a particular Vulkan WSI implementation.

A server implementation MUST NOT require the client to pass native window-system handles, file descriptors, client pointers, or backend-specific Vulkan handles over the XAverius wire protocol.

## 2. Object model

The presentation API is expected to introduce at least these logical objects:

- **Surface** — an XAverius resource referring to one existing X11 Window on the same X server connection. The surface does not own or create the X11 Window.
- **Swapchain** — a device-owned set of presentable images and their presentation state, associated with one surface.
- **Swapchain image** — an image owned by the swapchain. It is not an independently client-destroyable resource in the initial design.
- **Acquired image** — a swapchain image temporarily owned by the client for rendering or other permitted use.
- **Presentation operation** — an ordered request to make a rendered swapchain image available for display in the target window.

These are conceptual object categories, not final wire names or assigned request subopcodes. The current request registry remains unchanged until each request layout, error behavior, and lifetime rule has been reviewed.


## 2.1 Ownership and destruction contract

The following ownership rules are normative for the presentation-capable profile:

- A Surface is a client-created XAverius resource owned by the X11 connection that created it. It is bound to one exact X11 Window identity and is **not** owned by a logical Vulkan Device. This allows a client to query whether different logical devices can present to the same window without recreating the Surface.
- A Swapchain is a client-created XAverius resource owned by exactly one logical Device and refers to exactly one Surface. Its images and image-acquisition state are children of the Swapchain, not separately client-destroyable resources.
- A Surface may outlive any logical Device. Destroying a Device invalidates its Swapchains, but does not destroy a Surface owned by the same connection.
- A Surface must not be destroyed while a live Swapchain references it. The destroy request is rejected atomically; the Surface remains live.
- A Swapchain must not be destroyed while any queue submission, accepted presentation operation, pending acquire registration, or backend access may still reference its images. The destroy request is rejected atomically in that case. An image being ACQUIRED by itself does not prevent destruction once the client has ensured that no GPU command or backend operation can still use it: successful destruction invalidates the Swapchain and all image indices, so they can no longer be presented or acquired.
- Successful destruction immediately invalidates the public XID. Backend images, window references, and internal synchronization objects may be released later under the common resource-lifetime rules.
- Destruction of the underlying X11 Window does not implicitly destroy or rebind the Surface XID. It transitions the Surface to SURFACE_LOST; operations that require a usable Surface report that state, and explicit Surface destruction remains available.
- Client disconnect invalidates the client's Surface and Swapchain XIDs. Internal window/image references remain until queued operations and backend accesses are quiescent; XID reuse must never redirect such references.

For wire-layout planning, the natural initial request shapes are a 16-byte CreateSurface (target Surface XID plus X11 Window XID), a 12-byte DestroySurface, and a 12-byte DestroySwapchain (target resource XID, with Device inferred from the resource). These are provisional layouts, not allocated or frozen requests; the common 8-byte header is included in each total. A later request-layout pass must cross-check these shapes against common error mapping and the central registry before assigning subopcodes.

### Exact X11 Window identity

A numeric XID alone is not a durable reference. On successful Surface creation, the server must resolve the Window XID to the server's internal resource identity and retain a reference to that identity. It must also subscribe to or otherwise reliably observe the window's destruction and geometry changes. If the XID is subsequently reused, the retained reference continues to identify the original window object, now destroyed; it must never resolve again by numeric lookup.

A Surface creation failure must leave the target Surface XID unallocated and must not retain a partial window reference. A Surface creation request naming an unknown/destroyed XID or a non-Window resource fails synchronously; the exact X11 error code is to be settled with the request error map. A later Window destruction is asynchronous and cannot retroactively turn the original successful create request into an X11 error.

## 3. Window relationship and lifecycle

The referenced window MUST be a valid X11 Window on the same X server connection. A non-window XID, an unknown XID, or a window that is not usable for presentation must be rejected using the eventual request-specific X11 error mapping. Presentation requests MUST NOT silently create a window or change ordinary X11 window-management policy.

The Surface holds a server-side reference to the X11 window identity, not merely its numeric XID. If the window is destroyed and its XID later reused, the existing Surface MUST NOT begin referring to the new window. This follows the internal-identity rule in [resource lifetime](resource-lifetime.md).

Window resize, unmap, and destruction are asynchronous X11 lifecycle changes, not XAverius resource creation requests. The presentation implementation must observe these changes and keep its surface/swapchain state coherent:

- A change to the X11 Window's pixel extent marks each associated active Swapchain OUT_OF_DATE. No new acquire or present operation is accepted against an OUT_OF_DATE Swapchain; requests return the explicit OUT_OF_DATE status. Already accepted GPU and presentation operations are allowed to reach terminal outcomes, and the client may create a replacement Swapchain using freshly queried capabilities. The old Swapchain remains destroyable after pending uses have drained, even if its images were acquired but are no longer referenced by work.
- Window destruction makes the associated Surface unusable for future acquisition and presentation. It must not redirect presentation to a later window that reuses the XID.
- Unmapping or obscuring a window does not itself destroy the Surface. Whether the backend can avoid work while it is not visible is an optimization and must not change resource identity or synchronization guarantees.
- A client may explicitly destroy its Surface and swapchain before destroying the X11 window. The eventual API must define deterministic behavior for destruction with acquired images or queued presentation operations.

A window event or resize notification is not itself proof that GPU work or presentation has completed.

## 4. Surface capabilities and swapchain negotiation

Before creating a swapchain, the client needs a queryable contract for whether the selected logical device can present to the Surface, which image formats and presentation modes are supported, and which extent, image-count, and image-usage constraints apply. This query is scoped to the exact pair (Device XID, Surface XID); it must not silently substitute another physical or logical device.

The capability query must report server/backend-supported values, not assume that every Vulkan physical device can present to every X11 window. Device selection for compute does not imply presentation support. If the chosen logical device cannot present to the Surface, swapchain creation must fail deterministically rather than silently migrating resources to another device.

The initial presentation profile uses the explicit [presentation format and mode registry](../registries/presentation-formats.md). Format values are XAverius wire identifiers, not native Vulkan enum values. A supported format is reported together with its color-space identifier; clients must use a pair returned by the query. FIFO is the baseline presentation mode and must be reported whenever presentation is supported.

The capability contract must report: (a) whether the Device/Surface pair can present; (b) current window extent; (c) minimum and maximum permitted swapchain image count; (d) minimum and maximum supported extent; (e) supported format/color-space pairs; (f) supported presentation modes; and (g) the image usage operations the server can actually support for those images. The wire representation and exact request/reply layout remain to be specified, but every count must be paired with an explicit record size and a reply-length formula, and reserved fields must be zero.

Capability results are a snapshot, not a permanent promise. Window resize, surface loss, backend reconfiguration, or device loss may invalidate the snapshot. A zero-sized/minimized window must be reported explicitly as temporarily not presentable (rather than returning a fabricated nonzero extent or blocking indefinitely); the client can query again after a later geometry change. A false presentation-support result is a normal capability result, not a reason to migrate the Swapchain to another Device.


## 4.1 Swapchain image identity and usage

Swapchain images are identified by the pair (Swapchain XID, image_index), where image_index is a zero-based index returned by Swapchain creation and bounded by that Swapchain's image_count. They do not receive public XIDs, cannot be independently destroyed, and cannot be rebound to another Swapchain. This avoids creating a second public-resource lifetime for an image whose storage and presentation state are owned by the Swapchain.

The image state machine is:

- AVAILABLE: eligible to be returned by a successful acquire.
- ACQUIRED: owned by the client; may be referenced by supported image commands and may be submitted for presentation.
- PRESENT_PENDING: accepted for presentation; the presentation backend may still access the image, and it cannot be acquired again.
- AVAILABLE again: only after the presentation backend has released the image for reuse.
- INVALID: the Swapchain has become unusable or has been destroyed; no further operation may use the image.

A failed acquire does not change any image state. A present request rejected before acceptance leaves the image ACQUIRED. Once a present request is accepted, the image transitions to PRESENT_PENDING; an eventual presentation failure must still produce a terminal outcome that releases or invalidates the image deterministically. If a Swapchain becomes OUT_OF_DATE or SURFACE_LOST while an image is ACQUIRED, the client may destroy that Swapchain after all GPU references have completed; it does not need to present the image solely to make destruction possible. The protocol must never make an image reacquirable merely because the rendering QueueSubmit completed.

The Swapchain creation contract must include an image usage mask. In the initial profile, TRANSFER_DST is the only defined usage bit; capability queries return it only when the server can support the buffer-to-image copy for the selected Device/Surface pair and format. Swapchain creation with any unreported or unassigned usage bit is rejected atomically. The usage mask does not itself make an operation available: the presentation profile must separately define image-aware command entries and descriptors for each advertised use.

The current compute-only command set does not directly address a Swapchain image. The initial presentation-capable profile now defines a minimal pixel path via CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE: compute work may fill a transfer-source Buffer, and a command entry copies the pixel data into an acquired Swapchain image with TRANSFER_DST usage. The command-entry ID is registered as presentation-profile-only. This enables basic on-screen pixel output but does not provide general graphics pipelines, rasterization, or color-attachment rendering. Advertising an image usage without a command path that can exercise it is non-conforming.

## 5. Acquire, render, and present ordering

The intended workflow is:

1. Create an ordinary X11 window using core X11 requests.
2. Create a Surface referring to that window.
3. Query Surface capabilities and choose a supported swapchain configuration.
4. Create a Swapchain and its presentable images.
5. Acquire an available image, with an explicit timeout/status contract and a synchronization signal that can be used by queue work.
6. Record and submit rendering commands using the existing XAverius command-buffer and queue-submission model, subject to the image's supported usage.
7. Queue a presentation operation that identifies the swapchain image and the synchronization dependency that makes its rendered contents ready.
8. Reuse or destroy swapchain resources only after the relevant acquisition and presentation lifecycle permits it.

The final protocol must specify whether acquisition signals a semaphore, a fence, or both; whether present waits on one or more semaphores; and how binary-semaphore consumption is represented. The current command-entry registry only supports compute dispatch and buffer descriptors; it has no image resource or graphics commands. Therefore this chapter does not claim that swapchain images can already be rendered to with the current v0.1 command set. A usable on-screen rendering profile must separately add and register the necessary image resource/usage support and rendering commands, or define a clearly scoped image-upload/copy path. It must not imply that the server can infer GPU readiness merely from request order. Existing XAverius semantics explicitly distinguish protocol request order, queue acceptance, GPU completion, and host replies.

Presentation must be integrated with queue ordering without adding implicit cross-queue ordering beyond the dependencies explicitly established by the client and the presentation contract.


## 5.1 Acquisition synchronization contract

Acquisition is a reply-bearing operation with an explicit timeout and status result; it must not block the X11 request dispatcher while waiting for an image. The server may retain a pending acquire registration and continue processing requests from the connection, including host semaphore signals and destruction checks. A timeout of zero performs a non-blocking poll; an infinite timeout is represented by the all-ones CARD64 value. Other timeout values are nanoseconds.

An acquire operation may name an optional binary Semaphore XID and optional Fence XID owned by the same logical Device. At least one synchronization object or a successful reply carrying the image index must make the acquisition result observable; the final wire layout must state whether both synchronization objects may be supplied together. Timeline semaphores are not valid acquire signals. On successful acquisition, each supplied synchronization object is signaled exactly once under the existing semaphore/fence state rules. A failed or timed-out acquire signals neither object and changes no image state.

Acquire status values must distinguish at least SUCCESS, TIMEOUT, NOT_READY, OUT_OF_DATE, SURFACE_LOST, and DEVICE_LOST. TIMEOUT/NOT_READY/OUT_OF_DATE/SURFACE_LOST are not X11 framing errors; they are operation results. An image index is valid only on SUCCESS. OUT_OF_DATE and SURFACE_LOST must not return a fabricated image index.

A pending acquire registration holds internal references to its Swapchain, Surface, and supplied synchronization objects. Destroying any of those resources while the acquire is pending must be rejected or must first terminally cancel the acquire according to a deterministic rule; no object may be freed while a pending registration can signal it. The final contract should prefer atomic rejection of the destroy request while the acquire remains pending.

## 5.2 Presentation synchronization contract

A present operation names the Device, an existing queue tuple (queue family and queue index), the Swapchain and acquired image index, plus a list of binary semaphores to wait on. The queue must belong to that Device and must be reported as capable of presenting to the Surface. Timeline semaphores are not accepted as present waits in the initial profile.

The present request is reply-bearing. A SUCCESS reply means the operation was accepted and the image entered PRESENT_PENDING; it does not mean the image has been displayed, released, or reached physical scanout. Before acceptance, the server validates every resource, image state, queue capability, and wait semaphore atomically. A rejected request leaves the image ACQUIRED and does not consume or reserve any wait semaphore.

After acceptance, the named binary semaphore waits are consumed according to the existing binary-semaphore rules, and the presentation backend waits until those dependencies are satisfied before reading the image. Request order alone is not a substitute for this GPU dependency. The server must avoid blocking the X11 dispatcher while waiting for presentation dependencies.

The operation has an asynchronous terminal outcome. The protocol must expose both (a) the point at which the image is no longer in use by the presentation backend and can be acquired again, and (b) presentation completion as defined by the selected backend. These are distinct signals even if a particular backend reports them at the same time. An asynchronous failure must not leave an image permanently PRESENT_PENDING: it must either release the image for reuse or transition the affected Swapchain to a state in which the image is INVALID, with the terminal outcome observable by the client.

## 6. Completion is three different things

The presentation contract MUST distinguish at least these milestones:

- **GPU submission completion** — rendering commands have reached their terminal GPU outcome.
- **Image release / reacquisition eligibility** — the presentation system no longer needs the image and it can be acquired again.
- **Presentation completion** — the image has reached the presentation system's defined completion point for the target window.

These milestones may occur at different times. A normal QueueSubmit terminal event is not, by itself, proof that a submitted image has been displayed or released for reacquisition. Likewise, a successful present request reply should mean only what its normative reply contract says (for example, request accepted or operation queued), not necessarily that pixels have reached the screen.

The eventual API must specify how asynchronous present failures, out-of-date swapchains, surface loss, and device loss are reported. It must avoid an unbounded server wait in the X11 request dispatcher.

## 7. Resize and swapchain replacement

A resize can make the old swapchain extent unsuitable while GPU work or presentation operations still refer to its images. The API must support a controlled replacement path: stop new acquisitions from the old swapchain, create a replacement using current capabilities, and retire the old swapchain only after all acquired images and queued operations have reached a safe terminal state.

The server must not free image backing storage while a queue submission, presentation operation, or backend access can still reference it. Public XIDs, if used for swapchains or surfaces, follow the existing immediate-public-invalidation and delayed-internal-release model.

A zero-sized or temporarily unpresentable window marks associated Swapchains OUT_OF_DATE and makes capabilities report temporarily not presentable. It must not force the client to destroy and recreate the X11 window. The client can retry after a later resize. Window destruction marks the Surface SURFACE_LOST and all associated Swapchains unusable; no new acquire or present is accepted, but already accepted operations still require a terminal outcome and safe backend release.

## 8. Initial scope and explicit non-goals

The presentation-capable profile should initially target presentation into ordinary X11 windows only. The following are not implied by this chapter and require separate design work:

- client-native VkXlibSurfaceKHR handles or client-side Vulkan WSI;
- pixmap presentation, XRender Pictures, RandR transforms, and arbitrary external image sharing;
- implicit cross-client or cross-device sharing of XAverius resources;
- a guarantee that every compute-capable physical device is also presentation-capable;
- a guarantee of a particular display timing, refresh interval, tearing policy, or physical scanout completion point unless explicitly reported by a future capability/extension contract.


## 10. Provisional wire layouts

This section proposes concrete fixed layouts so they can be audited against the common XAverius header and X11 reply framing. The layouts remain provisional until the cross-chapter error and checker pass is complete. All offsets below include the standard 8-byte request header.

### CreateSurface — Void, 16 bytes

- Offset 8: XID `surface_xid` — client-allocated target XID
- Offset 12: XID `window_xid` — existing core X11 Window

On success, creates a connection-owned Surface and retains the exact internal Window identity. The target XID remains unallocated on failure.

### DestroySurface — Void, 12 bytes

- Offset 8: XID `surface_xid`

The Device is not part of this request because Surface is connection-owned rather than Device-owned. A live Swapchain referencing the Surface causes atomic rejection.

### GetSurfaceCapabilities — Reply, 16 bytes

- Offset 8: XID `device_xid`
- Offset 12: XID `surface_xid`

The standard X11 reply header occupies offsets 0–31. The fixed capability fields below use its ordinary data area at offsets 8–28 and continue in the XAverius payload at offsets 32–60. All offsets in the table are absolute offsets from the beginning of the reply packet.

| Offset | Type | Field |
|---:|---|---|
| 8 | CARD32 | `status` |
| 12 | CARD32 | `present_supported` (0 or 1) |
| 16 | CARD32 | `current_width` |
| 20 | CARD32 | `current_height` |
| 24 | CARD32 | `min_image_count` |
| 28 | CARD32 | `max_image_count` (0 means no fixed maximum) |
| 32 | CARD32 | `min_width` |
| 36 | CARD32 | `min_height` |
| 40 | CARD32 | `max_width` |
| 44 | CARD32 | `max_height` |
| 48 | CARD32 | `format_pair_count` |
| 52 | CARD32 | `present_mode_count` |
| 56 | CARD32 | `image_usage_flags` |
| 60 | CARD32 | `reserved = 0` |

Variable payload follows at offset 64: `format_pair_count` records of 8 bytes (`CARD32 format_id`, `CARD32 color_space_id`), followed by `present_mode_count` CARD32 values. Total reply size is `64 + 8 * format_pair_count + 4 * present_mode_count`; therefore `reply.length = 8 + 2 * format_pair_count + present_mode_count`. Counts and total size must be checked with wide arithmetic before allocation or serialization.

Status values: 0 SUCCESS; 1 TEMPORARILY_NOT_PRESENTABLE; 2 SURFACE_LOST; 3 DEVICE_LOST. CreateSwapchain status values are 0 SUCCESS; 1 OUT_OF_DATE; 2 SURFACE_LOST; 3 DEVICE_LOST; 4 UNSUPPORTED_CONFIGURATION; 5 ALLOCATION_FAILED. SUCCESS with `present_supported = 0` means the Device/Surface pair is valid but cannot present. TEMPORARILY_NOT_PRESENTABLE means the window has zero extent; it must set present_supported to 0 and all extent/count/format/mode/usage fields to zero. SURFACE_LOST and DEVICE_LOST likewise return zero capability fields. Unknown or foreign resource XIDs are synchronous X11 errors, not status values.

### CreateSwapchain — Reply, 48 bytes

- Offset 8: XID `device_xid`
- Offset 12: XID `swapchain_xid` — client-allocated target XID
- Offset 16: XID `surface_xid`
- Offset 20: CARD32 `image_count` — exact requested count
- Offset 24: CARD32 `format_id`
- Offset 28: CARD32 `color_space_id`
- Offset 32: CARD32 `width`
- Offset 36: CARD32 `height`
- Offset 40: CARD32 `present_mode_id`
- Offset 44: CARD32 `image_usage_flags`

Reply payload at offset 32 is two CARD32 values: `status`, `actual_image_count`; total reply size is 40 bytes and `reply.length = 2`. The initial contract requests an exact image count: success reports the same count; a backend unable to provide exactly that count rejects creation. This avoids an ambiguity about the client-visible image-index range. A successful create atomically allocates the Swapchain XID and image set. A non-success status leaves the target XID unallocated.

### DestroySwapchain — Void, 12 bytes

- Offset 8: XID `swapchain_xid`

Device ownership is inferred from the resource. Destruction is rejected while pending acquisition, queue work, accepted presentation, or backend access can still use its images. Acquired-but-idle images are invalidated with the Swapchain and do not independently prevent destruction.

### AcquireNextImage — Reply, 32 bytes

- Offset 8: XID `device_xid`
- Offset 12: XID `swapchain_xid`
- Offset 16: CARD64 `timeout_ns`; all ones means infinite
- Offset 24: XID `semaphore_xid`; zero means absent
- Offset 28: XID `fence_xid`; zero means absent

Reply payload at offset 32 is three CARD32 values: `status`, `image_index`, `reserved = 0`; total reply size is 44 bytes and `reply.length = 3`. The image index is meaningful only for SUCCESS. If both semaphore and fence are nonzero, both must be valid and eligible for acquisition signaling; neither is signaled on failure or timeout. The semaphore, when present, must be binary.

### QueuePresent — Reply, variable length

Fixed request fields:

- Offset 8: XID `device_xid`
- Offset 12: CARD32 `queue_family_index`
- Offset 16: CARD32 `queue_index`
- Offset 20: XID `swapchain_xid`
- Offset 24: CARD32 `image_index`
- Offset 28: CARD32 `wait_semaphore_count`
- Offset 32: CARD64 `presentation_token` (nonzero and unique for the connection lifetime)
- Offset 40: `wait_semaphore_count` XID values for binary semaphores

Total request size is `40 + 4 * wait_semaphore_count`. The count must be positive only if the client uses explicit waits; zero is permitted when the image needs no additional queue dependency. Duplicate semaphore XIDs are invalid. A reply contains one CARD32 status at offset 32; total reply size is 36 bytes and `reply.length = 1`. SUCCESS means accepted, not displayed. OUT_OF_DATE, SURFACE_LOST, and DEVICE_LOST are status outcomes and do not consume waits or change the image from ACQUIRED. Synchronous validation errors are X11 errors and likewise leave all state unchanged.

The seven requests above are not assigned subopcodes in this chapter. After the request audit and checker are updated to these layouts, they may be appended to the central registry without moving the existing values 1–40.

## 11. Work required before assigning request opcodes

Before adding presentation requests to the central registry, the design pass must settle and cross-check:

1. Surface and swapchain ownership, destroy behavior, and exact X11 Window identity tracking.
2. Surface capability query wire layout and the format/mode registries; initial pixel-format, color-space, and FIFO mode IDs are now defined in [presentation-formats](../registries/presentation-formats.md).
3. Swapchain image usage and image-index identity are now defined in section 4.1; the required image-aware command/descriptor path remains to be specified.
4. Acquire timeout/status semantics and semaphore/fence signaling are outlined in section 5.1; exact request/reply wire layout remains to be specified.
5. Present wait-semaphore semantics, queue association, reply behavior, and asynchronous terminal events are outlined in section 5.2; exact layouts and event IDs remain to be assigned.
6. Resize, out-of-date, surface-lost, and device-lost transitions.
7. How presentation completion and image release are observed separately from GPU submission completion.
8. Resource lifetime and synchronization integration with the existing checker and conformance cases.

No request subopcode is reserved by this chapter. Numeric assignments must be made append-only in [the request subopcode registry](../registries/request-subopcodes.md) after the wire contracts are reviewed.
