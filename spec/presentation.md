# On-screen presentation in X11 windows

Status: **architecture defined; request layouts and numeric assignments intentionally not yet allocated**.

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

## 3. Window relationship and lifecycle

The referenced window MUST be a valid X11 Window on the same X server connection. A non-window XID, an unknown XID, or a window that is not usable for presentation must be rejected using the eventual request-specific X11 error mapping. Presentation requests MUST NOT silently create a window or change ordinary X11 window-management policy.

The Surface holds a server-side reference to the X11 window identity, not merely its numeric XID. If the window is destroyed and its XID later reused, the existing Surface MUST NOT begin referring to the new window. This follows the internal-identity rule in [resource lifetime](resource-lifetime.md).

Window resize, unmap, and destruction are asynchronous X11 lifecycle changes, not XAverius resource creation requests. The presentation implementation must observe these changes and keep its surface/swapchain state coherent:

- A resize may change the surface extent and invalidate the current swapchain for future acquisition or presentation.
- Window destruction makes the associated Surface unusable for future acquisition and presentation. It must not redirect presentation to a later window that reuses the XID.
- Unmapping or obscuring a window does not itself destroy the Surface. Whether the backend can avoid work while it is not visible is an optimization and must not change resource identity or synchronization guarantees.
- A client may explicitly destroy its Surface and swapchain before destroying the X11 window. The eventual API must define deterministic behavior for destruction with acquired images or queued presentation operations.

A window event or resize notification is not itself proof that GPU work or presentation has completed.

## 4. Surface capabilities and swapchain negotiation

Before creating a swapchain, the client needs a queryable contract for whether the selected logical device can present to the Surface, which image formats and presentation modes are supported, and which extent, image-count, usage, and transform constraints apply.

The capability query must report server/backend-supported values, not assume that every Vulkan physical device can present to every X11 window. Device selection for compute does not imply presentation support. If the chosen logical device cannot present to the Surface, swapchain creation must fail deterministically rather than silently migrating resources to another device.

The initial presentation profile should prefer a small, explicit set of formats and modes. Format values must use a XAverius wire registry with fixed numeric assignments; native Vulkan enum values must not be copied to the wire without an explicit compatibility decision. Extent and image-count limits must be explicit, and zero-sized/minimized windows must have a defined non-blocking behavior rather than causing an indefinite wait.

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

The final protocol must specify whether acquisition signals a semaphore, a fence, or both; whether present waits on one or more semaphores; and how binary-semaphore consumption is represented. It must not imply that the server can infer GPU readiness merely from request order. Existing XAverius semantics explicitly distinguish protocol request order, queue acceptance, GPU completion, and host replies.

Presentation must be integrated with queue ordering without adding implicit cross-queue ordering beyond the dependencies explicitly established by the client and the presentation contract.

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

A zero-sized or temporarily unpresentable window must not force the client to destroy and recreate the X11 window. The API should report the condition explicitly and allow the client to retry after a later resize.

## 8. Initial scope and explicit non-goals

The presentation-capable profile should initially target presentation into ordinary X11 windows only. The following are not implied by this chapter and require separate design work:

- client-native VkXlibSurfaceKHR handles or client-side Vulkan WSI;
- pixmap presentation, XRender Pictures, RandR transforms, and arbitrary external image sharing;
- implicit cross-client or cross-device sharing of XAverius resources;
- a guarantee that every compute-capable physical device is also presentation-capable;
- a guarantee of a particular display timing, refresh interval, tearing policy, or physical scanout completion point unless explicitly reported by a future capability/extension contract.

## 9. Work required before assigning request opcodes

Before adding presentation requests to the central registry, the design pass must settle and cross-check:

1. Surface and swapchain ownership, destroy behavior, and exact X11 Window identity tracking.
2. Surface capability and format registries, including byte order and color-space scope.
3. Swapchain image usage and how image handles are exposed without allowing independent destruction.
4. Acquire timeout/status semantics and semaphore/fence signaling.
5. Present wait-semaphore semantics, queue association, reply behavior, and asynchronous failure events.
6. Resize, out-of-date, surface-lost, and device-lost transitions.
7. How presentation completion and image release are observed separately from GPU submission completion.
8. Resource lifetime and synchronization integration with the existing checker and conformance cases.

No request subopcode is reserved by this chapter. Numeric assignments must be made append-only in [the request subopcode registry](../registries/request-subopcodes.md) after the wire contracts are reviewed.
