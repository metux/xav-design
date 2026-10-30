# On-screen presentation in X11 windows

Status: **ownership/lifecycle, initial format/mode IDs, request/reply layouts, static checker coverage, presentation command-entry ID 5, and request subopcodes 41–47 defined; presentation requests remain profile-gated**.

This chapter extends the compute-oriented v0.1 design toward presentation into ordinary X11 windows. It does not change existing compute request contracts, queue semantics, or resource ownership rules. The initial implementation may remain compute-only; this chapter establishes the direction for a later presentation-capable profile.

## 1. Architectural model

XAverius presentation is server-side. The client creates and manages an ordinary X11 window through the normal X11 core protocol, then identifies that window to XAverius by its XID. XAverius does not create a second, client-native Vulkan window surface and does not require the client to use a platform-specific Vulkan WSI extension.

The server owns the presentation implementation and is responsible for connecting the logical XAverius surface to the named X11 window. The backend may use a native Vulkan WSI path when the server's Vulkan implementation supports a suitable X11 target. Otherwise it may use server-managed Vulkan images and an internal copy, blit, or composition path into the X11 window. These are implementation alternatives: the externally observable contract is presentation in the selected X11 window, not use of a particular Vulkan WSI implementation.

A server implementation MUST NOT require the client to pass native window-system handles, file descriptors, client pointers, or backend-specific Vulkan handles over the XAverius wire protocol.

## 2. Object model

The presentation API is expected to introduce at least these logical objects:

- **Surface** — an XAverius resource referring to one existing core X11 Window owned by the requesting X11 client connection. The surface does not own or create the X11 Window; cross-client Window references are not supported.
- **Swapchain** — a device-owned set of presentable images and their presentation state, associated with one surface.
- **Swapchain image** — an image owned by the swapchain. It is not an independently client-destroyable resource in the initial design.
- **Acquired image** — a swapchain image temporarily owned by the client for rendering or other permitted use.
- **Presentation operation** — an ordered request to make a rendered swapchain image available for display in the target window.

These are conceptual object categories. The request names and wire layouts in section 10 are defined and assigned subopcodes 41–47 in the central registry. The static checker covers their wire layouts and core error-map invariants; all seven requests remain gated on the presentation-capable profile.


## 2.1 Ownership and destruction contract

The following ownership rules are normative for the presentation-capable profile:

- A Surface is a client-created XAverius resource owned by the X11 connection that created it. It is bound to one exact X11 Window identity and is **not** owned by a logical Vulkan Device. This allows a client to query whether different logical devices can present to the same window without recreating the Surface.
- A Swapchain is a client-created XAverius resource owned by exactly one logical Device and refers to exactly one Surface. Its images and image-acquisition state are children of the Swapchain, not separately client-destroyable resources.
- A Surface may outlive any logical Device. Destroying a Device invalidates its Swapchains, but does not destroy a Surface owned by the same connection.
- A Surface must not be destroyed while a live Swapchain references it. The destroy request is rejected atomically; the Surface remains live.
- A Swapchain must not be destroyed while any recording command buffer, queue submission, accepted presentation operation, pending acquire registration, or backend access may still reference its images. The destroy request is rejected atomically in that case. Non-pending executable command buffers that reference it are invalidated atomically when destruction succeeds. An image being ACQUIRED by itself does not prevent destruction once the client has ensured that no GPU command or backend operation can still use it: successful destruction invalidates the Swapchain and all image indices, so they can no longer be presented or acquired.
- Successful destruction immediately invalidates the public XID. Backend images, window references, and internal synchronization objects may be released later under the common resource-lifetime rules.
- Destruction of the underlying X11 Window does not implicitly destroy or rebind the Surface XID. It transitions the Surface to SURFACE_LOST; operations that require a usable Surface report that state, and explicit Surface destruction remains available.
- Client disconnect invalidates the client's Surface and Swapchain XIDs. Internal window/image references remain until queued operations and backend accesses are quiescent; XID reuse must never redirect such references.

For wire-layout history, the initial request shapes are a 16-byte CreateSurface (target Surface XID plus X11 Window XID), a 12-byte DestroySurface, and a 12-byte DestroySwapchain (target resource XID, with Device inferred from the resource). The final layouts include the common 8-byte header and are cross-checked against the common error mapping and central registry.

### Exact X11 Window identity

A numeric XID alone is not a durable reference. On successful Surface creation, the server must resolve the Window XID to the server's internal resource identity and retain a reference to that identity. It must also subscribe to or otherwise reliably observe the window's destruction and geometry changes. If the XID is subsequently reused, the retained reference continues to identify the original window object, now destroyed; it must never resolve again by numeric lookup. The internal reference is to the Window resource identity, not to its current numeric XID-table entry. Window destruction marks that identity destroyed and the Surface `SURFACE_LOST`; the Surface XID remains live until explicit `DestroySurface` (or connection teardown), and the destroyed Window identity must never be rebound to a replacement Window. The server may release the retained tombstone/reference only when the Surface and all operations that can still refer to that identity have been safely retired.

A Surface creation failure must leave the target Surface XID unallocated and must not retain a partial window reference. A Surface creation request naming an unknown/destroyed XID or a non-Window resource fails synchronously with the core X11 `BadWindow` error. The target Surface XID is validated as a create-XID and uses `BadIDChoice` on invalidity or collision. A later Window destruction is asynchronous and cannot retroactively turn the original successful create request into an X11 error.

## 3. Window relationship and lifecycle

The referenced window MUST be a valid X11 Window on the same X server connection. A non-window XID, an unknown XID, or a window that is not usable for presentation must be rejected using the eventual request-specific X11 error mapping. Presentation requests MUST NOT silently create a window or change ordinary X11 window-management policy.

The Surface holds a server-side reference to the X11 window identity, not merely its numeric XID. If the window is destroyed and its XID later reused, the existing Surface MUST NOT begin referring to the new window. This follows the internal-identity rule in [resource lifetime](resource-lifetime.md).

Window resize, unmap, and destruction are asynchronous X11 lifecycle changes, not XAverius resource creation requests. The presentation implementation must observe these changes and keep its surface/swapchain state coherent:

- A change to the X11 Window's pixel extent marks each associated active Swapchain OUT_OF_DATE. No new acquire or present operation is accepted against an OUT_OF_DATE Swapchain; requests return the explicit OUT_OF_DATE status. Already accepted GPU and presentation operations are allowed to reach terminal outcomes, and the client may create a replacement Swapchain using freshly queried capabilities. The old Swapchain remains destroyable after pending uses have drained, even if its images were acquired but are no longer referenced by work.
- Window destruction transitions the associated Surface to `SURFACE_LOST` and makes it unusable for future acquisition and presentation. The Surface remains an addressable lost object until explicit `DestroySurface` or connection teardown; requests must not silently delete it, rebind it, or redirect presentation to a later Window that reuses the XID. Accepted operations are terminalized under the existing presentation-lifecycle rules.
- Unmapping or obscuring a window does not itself destroy the Surface, mark a Swapchain `OUT_OF_DATE`, or make the Surface `SURFACE_LOST`. Whether the backend can avoid work while it is not visible is an optimization and must not change resource identity or synchronization guarantees. A later map/unmap transition alone does not imply GPU or presentation completion.
- A client may explicitly destroy its Surface and swapchain before destroying the X11 window. Destruction with an acquired-but-idle image invalidates that image with the Swapchain; destruction is rejected while accepted presentation operations or other pending work can still reference the Swapchain.

A window event or resize notification is not itself proof that GPU work or presentation has completed.

### Serialization of Window and Surface lifecycle

The server MUST serialize each Window lifecycle notification and each XAverius request that creates, queries, or destroys the associated Surface against one authoritative per-connection resource-state order. A lifecycle notification is applied at its serialized transition point; the server MUST NOT resolve the Window XID again to identify the object for an existing Surface.

- `CreateSurface` resolves `window_xid` against the Window resource identity that exists at that request's serialized validation point. If the request is processed before destruction of that Window, creation may succeed and the resulting Surface then becomes `SURFACE_LOST` when destruction is processed. If destruction has already occurred and the XID is still unbound, the request fails with `BadWindow`. If the client has since validly created a new Window using the same numeric XID before `CreateSurface` is processed, the request may bind to that new Window; it MUST NOT infer identity from the destroyed predecessor. The request order on a single X11 connection determines which current Window the XID denotes.
- If `DestroySurface` succeeds before Window destruction is processed, its public Surface XID becomes invalid immediately. The later notification MUST NOT mutate or notify a different resource; the retained internal Window identity and any backend references are released only after all operations that may refer to them are quiescent. If Window destruction is processed first, the Surface becomes `SURFACE_LOST` but remains explicitly destroyable under the normal reference checks.
- `DestroySurface` performs all type, ownership, and live-Swapchain-reference checks at its serialization point. If any live Swapchain references the Surface, it fails atomically with `INVALID_SYNCHRONIZATION_STATE`: the Surface remains public and its state/references are unchanged by that request. If the checks pass, public invalidation and detachment from future Surface operations are atomic; internal reference release may be deferred.
- Connection teardown invalidates the connection's public Surface and Swapchain XIDs and suppresses future event/reply delivery for that connection. It does not cancel accepted backend work or permit early release of internal Window identities that backend work may still access. A delayed Window notification or completion must never look up a replacement resource by numeric XID.

For all races, the first serialized terminal transition for a given public resource wins. Later notifications may complete internal cleanup but MUST NOT revive the resource, overwrite an already serialized terminal status, or change the identity referenced by an accepted operation.

`CreateSwapchain` participates in the same authoritative resource-state order as Window geometry/destruction notifications and the relevant `DestroySurface`, `DestroyDevice`, and competing Swapchain lifecycle requests. Its commit point is the serialized point at which the server has completed validation against the current Surface/Device state and can atomically publish the new Swapchain XID. In a race with `DestroySurface`, creation committing first makes the live Swapchain reference visible to the destroy check, so `DestroySurface` is rejected atomically; `DestroySurface` committing first invalidates the Surface XID, so the later creation fails XID/type/ownership validation and cannot publish a Swapchain. In a race with `DestroyDevice`, the first serialized transition wins: a committed Swapchain is invalidated by the Device cascade. If successful `DestroyDevice` serializes before `CreateSwapchain` resolves its XIDs, the Device XID is no longer live and creation fails with `BadValue` at XID resolution; it MUST NOT return `DEVICE_LOST`, which is reserved for a still-live Device whose state is lost. If Device loss (without destruction) serializes first, `CreateSwapchain` returns `DEVICE_LOST` and leaves the target XID unallocated. The server MUST use the Window extent and Surface/Device lifecycle state current at that point, not a cached capability snapshot. If resize/zero-extent or Window destruction is serialized before that point, the request returns `OUT_OF_DATE` or `SURFACE_LOST` respectively (after the higher-priority Device-loss check), leaves the target XID unallocated, and retains no Swapchain/image/backend references. If creation commits first, the request may return `SUCCESS`; a later serialized resize or Window destruction immediately transitions the newly published Swapchain to `OUT_OF_DATE` or its Surface to `SURFACE_LOST`, even if the success reply has not yet reached the client. This later lifecycle transition does not retroactively change the create reply. All fallible preparation MUST remain private to the request until publication: allocate the Swapchain record, per-image records and backing resources, prepare backend/window-system resources, and acquire any provisional Device/Surface references before exposing the target XID or any image. The serialized commit point MUST revalidate the current Device/Surface/Window state and current extent after preparation; a lifecycle transition that won during preparation determines the normal status result instead of allowing a stale snapshot to commit. The server then publishes the Swapchain XID, exact image set, backend association, and retained-reference ownership as one indivisible state transition. If preparation or revalidation fails, cleanup MUST release every provisional resource/reference exactly once without touching a reused target XID or rolling back independent lifecycle changes. Allocation failure before commit returns `ALLOCATION_FAILED` with no public XID and no leaked request-owned references. Implementations MUST NOT expose a partially initialized Swapchain or roll back an independent lifecycle transition to preserve a successful create.

## 4. Surface capabilities and swapchain negotiation

Before creating a swapchain, the client needs a queryable contract for whether the selected logical device can present to the Surface, which image formats and presentation modes are supported, and which extent, image-count, and image-usage constraints apply. This query is scoped to the exact pair (Device XID, Surface XID); it must not silently substitute another physical or logical device.

The capability query must report server/backend-supported values, not assume that every Vulkan physical device can present to every X11 window. Device selection for compute does not imply presentation support. If the chosen logical device cannot present to the Surface, swapchain creation must fail deterministically rather than silently migrating resources to another device.

The initial presentation profile uses the explicit [presentation format and mode registry](../registries/presentation-formats.md). Format values are XAverius wire identifiers, not native Vulkan enum values. A supported format is reported together with its color-space identifier; clients must use a pair returned by the query. FIFO is the baseline presentation mode and must be reported whenever presentation is supported.

The capability contract must report: (a) whether the Device/Surface pair can present; (b) current window extent; (c) minimum and maximum permitted swapchain image count; (d) minimum and maximum supported extent; (e) supported format/color-space pairs; (f) supported presentation modes; (g) the image usage operations the server can actually support for those images; and (h) per-queue-family presentation support for this Device/Surface pair. The provisional wire layout is defined in section 10, including record sizes, the reply-length formula, and zero-valued reserved fields.

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

The current compute-only command set does not directly address a Swapchain image. The initial presentation-capable profile now defines a minimal pixel path via CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE: compute work may fill a transfer-source Buffer, and a command entry copies the pixel data into an acquired Swapchain image with TRANSFER_DST usage. The presentation-only command-entry ID is 5. This enables basic on-screen pixel output but does not provide general graphics pipelines, rasterization, or color-attachment rendering. Advertising an image usage without a command path that can exercise it is non-conforming.

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

The provisional wire layouts in section 10 permit both an optional binary semaphore and optional fence on acquisition, and a list of binary semaphore waits on presentation. Binary-semaphore consumption follows the existing synchronization rules. The command-entry registry assigns ID 5 to the presentation-only buffer-to-swapchain-image copy. This does not make presentation part of the compute-only v0.1 profile: a server may advertise the entry only when it also implements the presentation-capable profile and its associated capability, lifetime, synchronization, and event contracts. The protocol must not imply that the server can infer GPU readiness merely from request order. Existing XAverius semantics explicitly distinguish protocol request order, queue acceptance, GPU completion, and host replies.

Presentation must be integrated with queue ordering without adding implicit cross-queue ordering beyond the dependencies explicitly established by the client and the presentation contract.


## 5.1 Acquisition synchronization contract

Acquisition is a reply-bearing operation with an explicit timeout and status result; it must not block the X11 request dispatcher while waiting for an image. The server may retain a pending acquire registration and continue processing requests from the connection, including host semaphore signals and destruction checks. A timeout of zero performs a non-blocking poll and returns `NOT_READY` if no image is immediately available; a finite positive timeout that expires returns `TIMEOUT`. An infinite timeout is represented by the all-ones CARD64 value. Other timeout values are nanoseconds.

An acquire operation may name an optional binary Semaphore XID and optional Fence XID owned by the same logical Device; either may be omitted, and both may be supplied together. The reply itself reports the acquisition result and, on SUCCESS, the acquired image index. Timeline semaphores are not valid acquire signals. After the Device/Surface/Swapchain lifecycle checks, validate every supplied object for acquisition-signal eligibility and reject a conflicting pending acquire with `INVALID_SYNCHRONIZATION_STATE` before polling for an image or registering a wait; this remains an error even when no image is immediately available or `timeout_ns = 0`. Only after these checks may the request poll or wait. On successful acquisition, each supplied synchronization object is signaled exactly once under the existing semaphore/fence state rules. A failed or timed-out acquire signals neither object and changes no image state.

Acquire status values are SUCCESS=0, TIMEOUT=1, NOT_READY=2, OUT_OF_DATE=3, SURFACE_LOST=4, DEVICE_LOST=5, and DEVICE_DESTROYED=6. TIMEOUT/NOT_READY/OUT_OF_DATE/SURFACE_LOST/DEVICE_LOST/DEVICE_DESTROYED are not X11 framing errors; they are operation results. An image index is valid only on SUCCESS. OUT_OF_DATE and SURFACE_LOST must not return a fabricated image index.

The initial evaluation and registration/terminalization boundary MUST be atomic in the same serialization domain as image availability, Swapchain/Surface lifecycle changes, Device loss/destruction, timeout expiry, and competing acquire requests. After the wire/XID/type/ownership and lifecycle checks, the server validates the optional Semaphore and Fence states and reserves their acquisition-signal slots as part of this same operation; another request MUST NOT consume, signal, reset, or reserve either object incompatibly while the acquire is open. If an image is immediately available, the server atomically changes it to ACQUIRED, commits the signal of each supplied object exactly once, and terminalizes the request with SUCCESS. If no image is available and timeout is zero, the poll terminalizes immediately with NOT_READY and installs no registration or signal reservation. For a nonzero timeout, the server MUST atomically either observe and acquire an available image or install one open registration with its object reservations and retained references. An image becoming available between the initial check and registration MUST therefore either be observed by the check or wake the installed registration; it MUST NOT be lost between those steps.

When an image becomes reusable while one or more acquire registrations for the same Swapchain remain open, assignment to a pending acquire MUST be part of the same serialized image-release transition. The server MUST assign the image to exactly one still-open registration and atomically perform the `AVAILABLE` to `ACQUIRED` transition, signal that registration's reserved Semaphore/Fence objects, and terminalize it with `SUCCESS`. It MUST NOT expose the image as `AVAILABLE` to a later request while an eligible pending registration exists. If no eligible registration exists, the image becomes `AVAILABLE` for a later acquire. If several registrations are pending, the server MAY choose any one of them; FIFO order and fairness are not guaranteed. Every other registration remains open and may acquire a different image or terminate through its own timeout or lifecycle result. A single image MUST NOT satisfy more than one registration, and one registration MUST NOT acquire more than one image.

Every pending acquire has one terminalization gate. Image availability/success, timeout expiry, Device loss, Surface loss, Swapchain OUT_OF_DATE, and DestroyDevice MUST be serialized through that gate; the first terminal transition committed while the registration is open wins. If image acquisition commits first, a later timeout or lifecycle notification cannot revoke the acquired image, change the reply, or unsignal its objects. If timeout commits first, a later image-available callback cannot acquire an image or signal either object. If a lifecycle transition commits first, its defined status wins and neither object is signaled. On any non-success terminal outcome, release all signal reservations without changing the externally visible Semaphore/Fence signal state; on success, commit both supplied signals and the image transition as one indivisible operation. Late or duplicate callbacks MUST NOT emit another reply, acquire another image, signal either object again, or release a registration reference twice. Disconnect suppresses reply delivery but still closes the registration and releases every registration-only reference exactly once.
A pending acquire registration holds internal references to its Swapchain, Surface, Device, and supplied synchronization objects. Destroying the Swapchain or Surface while the acquire is pending is rejected atomically with `INVALID_SYNCHRONIZATION_STATE`; the pending registration and its synchronization-object references remain intact. `DestroyDevice` is different: it invalidates the Device and its owned resources immediately, terminalizes each still-open acquire with reply status `DEVICE_DESTROYED`, signals neither supplied synchronization object, and releases registration-only references after that terminal transition. The first terminal result serialized by the server wins; a later `DestroyDevice` must not overwrite an already-terminal acquire. Disconnect suppresses the reply but still removes the registration and safely releases its references.

A pending acquire is also reevaluated when an asynchronous lifecycle transition makes its Swapchain unusable. If Device loss is serialized first, the pending acquire terminates with `DEVICE_LOST`; otherwise Surface loss terminates it with `SURFACE_LOST`, and Swapchain invalidation due to resize/zero extent terminates it with `OUT_OF_DATE`. These lifecycle outcomes do not wait for the acquire timeout and do not signal either supplied synchronization object or transition an image to `ACQUIRED`. The first terminal result serialized for the registration wins across timeout, lifecycle notification, and `DestroyDevice`; a later transition cannot replace the reply status. Once terminalized, the registration is removed and its registration-only references are released exactly once. If a finite timeout expires or a zero-timeout poll returns first, its `TIMEOUT` or `NOT_READY` result wins and a later lifecycle notification cannot rewrite that completed reply. Disconnect suppresses delivery but not terminalization or reference cleanup.

## 5.2 Presentation synchronization contract

A present operation names the Device, an existing queue tuple (queue family and queue index), the Swapchain and acquired image index, plus a list of binary semaphores to wait on. The queue must belong to that Device, and its queue family must have `present_supported = 1` in the server's current capability data for that Device/Surface pair; `GetSurfaceCapabilities` exposes this per-family property to the client. Timeline semaphores are not accepted as present waits in the initial profile.

The present request is reply-bearing. A SUCCESS reply means the operation was accepted and the image entered PRESENT_PENDING; it does not mean the image has been displayed, released, or reached physical scanout. If any accepted submission can still write or otherwise access the image, QueuePresent must include a binary wait semaphore whose signal dependency covers that work. Same-queue request order alone is not a substitute for this dependency. A zero-length wait list is valid only when no outstanding GPU work needs to be ordered before presentation. Before acceptance, the server validates every resource, image state, queue capability, and wait semaphore atomically. A rejected request leaves the image ACQUIRED and does not consume or reserve any wait semaphore.

After acceptance, the named binary semaphore waits participate in the same per-Semaphore pending-wait accounting as `QueueSubmit` waits. Acceptance atomically reserves one wait slot for each semaphore together with the image transition and presentation-token reservation; it must reject a semaphore that already has an incompatible pending wait, is `UNTRUSTED`, or otherwise cannot legally be waited. The server then waits asynchronously for each dependency and consumes the signal only when the backend wait is known to have succeeded. Request order alone is not a substitute for this GPU dependency. The server must avoid blocking the X11 dispatcher while waiting for presentation dependencies.

If an accepted presentation fails before a wait is known to have been consumed, the server must resolve each wait independently: if it can prove the wait did not consume the payload, it releases that wait reservation and preserves the semaphore's prior confirmed state and any valid pending signal; if it can prove consumption, it records consumption; if neither can be established, it marks that binary semaphore `UNTRUSTED` under the common synchronization rules. It must never silently reset a semaphore to `UNSIGNALED` or treat an uncertain signal as available. Device loss follows the existing stricter device-wide semaphore rules. These semaphore transitions are internal and occur even if the presentation events are suppressed.

The operation has an asynchronous terminal outcome. The protocol must expose both (a) the point at which the image is no longer in use by the presentation backend and can be acquired again, and (b) presentation completion as defined by the selected backend. These are distinct signals even if a particular backend reports them at the same time. An asynchronous failure must not leave an image permanently PRESENT_PENDING: it must either release the image for reuse or transition the affected Swapchain to a state in which the image is INVALID. The terminal status is recorded exactly once. If `PRESENTATION_COMPLETE` is selected at the terminal point and delivery is permitted, that event reports the status; if event delivery is masked or suppressed, the protocol does not guarantee that the client can recover the exact terminal cause later, although the resulting image/Swapchain invalidation remains observable through subsequent operations.

Terminalization is serialized per accepted presentation operation. Exactly one terminal status is recorded; later backend callbacks or lifecycle notifications must not replace it or emit a second `PRESENTATION_COMPLETE`. The status reflects the first terminal outcome serialized by the server: a presentation already terminally completed as `SUCCESS` is not retroactively changed by a later resize or loss notification, while an operation still pending when a relevant failure is serialized terminates with that failure status.

A window resize or zero extent marks the Swapchain `OUT_OF_DATE` immediately for new requests. An accepted presentation that can still complete normally may terminate `SUCCESS`; if the resize prevents that operation from reaching its defined completion point, it terminates `OUT_OF_DATE`. In the latter case the old Swapchain cannot accept another acquire, so the image is invalidated and no `IMAGE_RELEASED` is emitted. Window destruction similarly makes the Surface `SURFACE_LOST`; any still-pending accepted presentation that cannot complete normally terminates `SURFACE_LOST`, invalidates its image and Swapchain, and emits no `IMAGE_RELEASED`. Device loss terminates still-pending accepted presentations with `DEVICE_LOST`, invalidates all affected Swapchains/images, and emits no `IMAGE_RELEASED`. A lifecycle notification does not override a terminal result already serialized for that operation.

`PRESENTATION_FAILED` is used for a backend failure not better classified as `OUT_OF_DATE`, `SURFACE_LOST`, or `DEVICE_LOST`. After such a failure, the server emits `IMAGE_RELEASED` only if it has established both that backend access has ended and that the image remains reusable in a still-usable Swapchain. Otherwise it invalidates the image and Swapchain and emits no `IMAGE_RELEASED`. The internal terminal transition, image-state update, and release of backend references occur exactly once regardless of whether either event is selected or can be delivered. The same cleanup requirement applies after the originating X11 client disconnects: event delivery is detached immediately, but accepted presentation callbacks retain their operation identity and backend/resource references until their own terminal and image-release milestones have completed. A late callback may finish internal cleanup, but MUST NOT enqueue events or resolve resources through a newly reused client connection or XID.

`DestroySwapchain` MUST reject while any accepted presentation still lacks either its terminal outcome or proof that backend image access has ended. Disconnect and Device Loss do not waive this blocker. Once both milestones have drained, destruction may invalidate the image and release the remaining Swapchain storage. Duplicate or delayed callbacks after that point MUST be rejected against the original operation identity and MUST NOT affect a newly created Swapchain that reuses the XID. The operation identity MUST include a server-side Swapchain generation (or an equivalent non-reusable lifetime identifier) in addition to the client-supplied presentation token and public XID. Every asynchronous terminal, image-release, and wait callback MUST carry or resolve to that captured generation. Comparing only the XID and token is insufficient because both may be reused after destruction. A callback whose captured generation does not match the live resource generation MUST be discarded without changing image state, terminal/release records, semaphore reservations, Device state, or event delivery.

When a Swapchain XID is reused, the new resource starts a fresh generation with independent image and presentation-token state. Device Loss, Surface loss, or release callbacks from the retired generation MUST NOT propagate into the new generation. The server MUST retain enough generation identity in callback-owned references to reject stale completions even after the old public XID has been removed and reallocated.



## 5.3 Request validation, status precedence, and atomic acceptance

All seven presentation requests use the normative validation stages in [the error mapping](errors.md#normative-validation-precedence-for-the-seven-presentation-requests): wire length and checked arithmetic; scalar/reserved-field validation; XID resolution in the defined order; type and ownership validation; Device availability; immutable request constraints; lifecycle/capability status; then mutable state and synchronization eligibility. No later stage may mask an earlier error. A rejected request or non-success status leaves no partial object, reference, image, semaphore, or token mutation attributable to that request; independent asynchronous lifecycle transitions are not rolled back.

The status precedence for requests with status replies is deterministic:

- `GetSurfaceCapabilities`: after valid XIDs, types, and ownership, `DEVICE_LOST` takes precedence over `SURFACE_LOST`. `TEMPORARILY_NOT_PRESENTABLE` applies only to a live Surface with zero extent. Every non-`SUCCESS` result returns zero in all capability fields except `status`, including all counts and variable arrays; the reply length is therefore exactly 64 bytes (`reply.length = 8`) for these statuses.
- `CreateSwapchain`: after syntactic and XID/ownership validation, `DEVICE_LOST` takes precedence over `SURFACE_LOST`; `SURFACE_LOST` takes precedence over `OUT_OF_DATE`; `OUT_OF_DATE` takes precedence over `UNSUPPORTED_CONFIGURATION`. A valid but unsupported configuration returns `UNSUPPORTED_CONFIGURATION` only when the Device and Surface are usable and the requested extent is current. `ALLOCATION_FAILED` is reserved for allocation failure after all validation succeeds. Every non-success reply has `actual_image_count = 0` and leaves `swapchain_xid` unallocated.
- `AcquireNextImage`: after validation, `DEVICE_LOST` takes precedence over `SURFACE_LOST`, which takes precedence over `OUT_OF_DATE`; these lifecycle outcomes precede image availability and timeout handling. `DEVICE_DESTROYED` is reserved for a pending acquire registration terminalized by `DestroyDevice`; it wins only if that terminal result is serialized first and never overrides an already-terminal result. Only a usable Swapchain is polled for an image. A zero timeout returns `NOT_READY` if no image is immediately available; a finite positive timeout returns `TIMEOUT` only when it expires. Every non-success reply has `image_index = 0`, `reserved = 0`, and signals neither optional synchronization object.
- `QueuePresent`: after valid XIDs, resource types, and ownership, `DEVICE_LOST` takes precedence over queue/index validity and all later state checks. Once the Device is usable, nonexistent queue-family/index or out-of-range image index is `BadValue`; then `SURFACE_LOST` takes precedence over `OUT_OF_DATE`. These normal lifecycle status replies precede token-reuse, mutable image-state, and wait-semaphore eligibility checks. A valid queue tuple with no presentation support is a synchronous `BadMatch` before token-reuse and image-state checks. Reuse of a token from an earlier accepted presentation is `BadValue` only after the queue presentation-support check and the higher-priority lifecycle checks, but before image-state/wait eligibility checks. A status reply does not itself mutate image or semaphore state, does not consume/reserve waits, and does not reserve the token; an independent lifecycle transition (especially Device loss) may already have invalidated the image and is not rolled back.


For AcquireNextImage and the pre-acceptance lifecycle check of QueuePresent, the lifecycle decision MUST use one serialized snapshot of the Device, Surface, and Swapchain state. If more than one lifecycle condition is present in that snapshot, the effective status is DEVICE_LOST first, then SURFACE_LOST, then OUT_OF_DATE, independent of the order in which the lower-priority resize and Window-destruction notifications originally arrived. This rule does not reorder validation stages: for QueuePresent, Device loss still precedes queue/index validation, while invalid queue/index values on a usable Device remain X11 errors before Surface/extent status is examined. Lifecycle status is determined before token reuse, image-state, wait-semaphore, image-availability, or timeout checks as applicable.

For an open pending acquire or an accepted presentation, the first terminal outcome committed in the operation's serialization domain remains final. If multiple lifecycle conditions have already been serialized before that operation terminalizes, the same DEVICE_LOST > SURFACE_LOST > OUT_OF_DATE precedence selects its lifecycle outcome. A later higher-priority transition MUST NOT rewrite an already committed SURFACE_LOST or OUT_OF_DATE result; likewise, a later resize or Window destruction MUST NOT rewrite a committed DEVICE_LOST result. For accepted QueuePresent, terminal status and image release remain separate milestones: selecting a terminal status does not authorize image reuse or IMAGE_RELEASED.

For `CreateSurface`, validate `surface_xid` as a create-XID before resolving `window_xid`; failure leaves the target unallocated and retains no Window reference. For `CreateSwapchain`, validate in this order after scalar syntax: `device_xid`, target `swapchain_xid`, then `surface_xid`. `DestroySurface` and `DestroySwapchain` validate the referenced resource before testing whether pending references prevent destruction; a rejected destroy leaves the resource live and all references unchanged.

For `QueuePresent`, `presentation_token = 0` and duplicate wait-semaphore XIDs are `BadValue` during scalar validation. Reuse of a token from an earlier accepted presentation is a stateful acceptance check: after higher-priority XID, Device, queue/index, lifecycle, and presentation-support checks, it returns `BadValue` before image-state or wait-semaphore eligibility checks. A token mentioned only in a rejected request is not reserved and may be retried. Acceptance is one indivisible transition: reserve the token and every wait slot, retain all required resources, and transition the image from `ACQUIRED` to `PRESENT_PENDING`; if any precondition fails, none of these changes occur. After acceptance, the request cannot produce a synchronous X11 error; exactly one terminal presentation outcome is serialized through the presentation state machine.

## 5.3 Cross-operation serialization of acquisition and presentation

All image-state transitions performed by `AcquireNextImage`, `QueuePresent`, and presentation image release MUST use one authoritative serialization order per Swapchain. This is the same order used for pending-acquire terminalization and lifecycle invalidation; separate request-dispatch, queue, or callback threads MUST NOT make independent decisions from stale image-state snapshots. Each operation has one linearization point:

- An immediate `AcquireNextImage` success linearizes when one `AVAILABLE` image changes to `ACQUIRED` and its supplied signal objects are committed.
- A pending acquire success linearizes when an image-release transition assigns one image to that registration, changes it from `AVAILABLE` to `ACQUIRED`, commits its signal objects, and terminalizes the registration.
- `QueuePresent` acceptance linearizes when the image changes from `ACQUIRED` to `PRESENT_PENDING` together with reservation of its token, wait slots, and required references.
- Image release linearizes when backend access has ended and the image either becomes `AVAILABLE` or is atomically assigned to one open acquire registration as specified in section 5.1.

For the same image, these transitions MUST be observed in that order, without an externally observable intermediate state that permits two owners. If `AcquireNextImage` commits first, a later `QueuePresent` may accept that image only after the acquire commit and only if all present dependencies are valid; the accepted present then changes the image to `PRESENT_PENDING`. If `QueuePresent` acceptance commits first, the image is `PRESENT_PENDING` and cannot satisfy an acquire until a later eligible image-release transition. A `QueuePresent` that serializes before an acquire has assigned the image MUST NOT anticipate or wait for that acquire: it is rejected with `INVALID_SYNCHRONIZATION_STATE` because the image is not yet `ACQUIRED`, and it reserves neither token nor waits. A `QueuePresent` serialized after the acquire-success commit observes the `ACQUIRED` state and is validated normally.

If an acquire registration is open while a different already-acquired image is presented, acceptance of that presentation does not complete, cancel, or reserve an image for the acquire. The acquire remains open until an image-release transition assigns an eligible image, its timeout wins, or a lifecycle transition terminalizes it. If presentation release and acquire timeout/lifecycle terminalization race, the common serialization order decides which commits first. If release/assignment wins, the acquire succeeds exactly once and later timeout/lifecycle callbacks cannot revoke it; if timeout/lifecycle wins, the release follows the ordinary no-waiter path and the terminalized registration receives no image or signal.

The request stream's ordering does not create an implicit wait between these operations and does not imply GPU completion. A client that submits `QueuePresent` before the acquire-success commit cannot use request order as a substitute for image ownership or a semaphore dependency. Likewise, an acquire success does not imply that prior presentation completion has occurred; it proves only that backend access ended and the image was made reusable under the release contract. Replies and events report their respective operation outcomes but do not alter these linearization rules.


## 5.4 Serialization with Swapchain and Device destruction

DestroySwapchain, DestroyDevice, AcquireNextImage, and QueuePresent MUST participate in the same authoritative resource-state serialization order as the image transitions in section 5.3. Validation, lifecycle checks, public-XID invalidation, acquire terminalization, and present acceptance MUST NOT be split across independently ordered snapshots. The applicable linearization point is the atomic state transition described below; backend preparation or callback arrival is not itself a commit point.

- **DestroySwapchain versus AcquireNextImage:** If DestroySwapchain commits before AcquireNextImage resolves its swapchain_xid, the XID is no longer live and the acquire fails synchronously with BadValue; it MUST NOT return OUT_OF_DATE, DEVICE_DESTROYED, or another status for the retired object. If an acquire registration is already open when DestroySwapchain is checked, destruction is rejected with INVALID_SYNCHRONIZATION_STATE and leaves the Swapchain XID, image states, registration, and signal reservations unchanged. The rejection does not cancel or terminalize the acquire. If an immediate acquire-success transition commits first, its SUCCESS reply and image index remain final. Because an acquired-but-idle image alone is not a destruction blocker, a subsequent DestroySwapchain may succeed and atomically invalidate that image and all image indices; a later QueuePresent naming the retired Swapchain then fails XID resolution with BadValue. If the acquire first terminalizes with TIMEOUT, NOT_READY, OUT_OF_DATE, or SURFACE_LOST, that terminal result remains final and destruction may proceed once no other blocker remains.

- **DestroySwapchain versus QueuePresent:** If destruction commits before QueuePresent resolves the Swapchain XID, the request fails with BadValue and creates no presentation operation, token reservation, wait reservation, or backend reference. If QueuePresent acceptance commits first, the image is PRESENT_PENDING and the accepted operation blocks DestroySwapchain until both its terminal outcome and proof that backend image access has ended have been serialized. A destroy attempted during that interval returns INVALID_SYNCHRONIZATION_STATE without invalidating the XID or changing the operation. Once both milestones have committed, DestroySwapchain may succeed; it invalidates the public XID and every image index atomically. A terminal callback alone, or image release alone, is insufficient to unblock destruction.

- **DestroyDevice versus AcquireNextImage:** If successful DestroyDevice commits before the acquire resolves its Device/Swapchain XIDs, both public resources are already invalid and the request fails synchronously with BadValue; it MUST NOT install a registration or return DEVICE_DESTROYED. If an acquire is pending when DestroyDevice commits, the cascade terminalizes that still-open registration with DEVICE_DESTROYED, signals neither optional object, invalidates the Swapchain and all its images, and releases registration-only references exactly once. If immediate acquire success commits first, its SUCCESS reply and signals remain final; the subsequent Device cascade invalidates the acquired image and prevents further use. A timeout or other terminal result committed before the cascade likewise remains unchanged. A later destroy transition MUST NOT rewrite any already-terminal acquire reply.

- **DestroyDevice versus QueuePresent:** If DestroyDevice commits before QueuePresent resolves its XIDs, the request fails with BadValue and has no acceptance side effects. If QueuePresent acceptance commits first, the accepted presentation is not retroactively rejected and its token/wait reservations and operation identity remain associated with the retired Device/Swapchain generations until safely terminalized and released. The Device cascade immediately invalidates the public Device, Swapchain, and image identities and suppresses new event enqueue/delivery for that Device. It does not treat destruction as Device Loss: DestroyDevice alone MUST NOT rewrite the accepted presentation's terminal result to DEVICE_LOST. The operation still reaches exactly one internal terminal outcome from its backend/lifecycle processing; if it can no longer complete because the backend operation is abandoned solely as a consequence of destruction, its internal outcome is PRESENTATION_FAILED. No IMAGE_RELEASED event is emitted for an image invalidated by the cascade, and no event naming the destroyed Device or Swapchain is newly queued after the destroy linearization point. Backend access and captured references remain retained until quiescence, irrespective of public invalidation or event suppression. If the presentation terminal outcome or image-release milestone committed before DestroyDevice, that milestone is not repeated or rewritten; the cascade still invalidates the image and suppresses later event delivery.

For all four race pairs, the first committed transition determines the result; there is no rollback of an independent transition. Requests that lose to successful public destruction observe an invalid XID, whereas operations already accepted or terminalized retain their recorded outcome. A rejected DestroySwapchain is mutation-free. A successful DestroyDevice is a cascade, not an ordinary DestroySwapchain request, and is not blocked by pending acquires or accepted presentations; it invalidates public identities while preserving the internal references needed to finish cleanup. XID reuse MUST NOT redirect any acquire registration, presentation operation, semaphore reservation, or callback to a replacement resource.



## 5.5 Serialization of presentation operations with Surface destruction

`DestroySurface` MUST participate in the same resource-lifecycle serialization order used to resolve the Surface identity for `AcquireNextImage` and `QueuePresent`. It is not an asynchronous Surface-loss notification and MUST NOT be translated into the `SURFACE_LOST` status. Explicit destruction is permitted only when no live Swapchain references the Surface; a live Swapchain is a destruction blocker even when all its images are idle, all acquires have terminalized, and all presentations have completed. The Surface destroy check and public-XID invalidation are one atomic transition.

- **DestroySurface versus AcquireNextImage:** Every valid acquire names a live Swapchain, and that Swapchain holds a live reference to its Surface. Therefore, while the acquire can resolve a live Swapchain, `DestroySurface` MUST be rejected with `INVALID_SYNCHRONIZATION_STATE`, leaving the Surface XID and its retained Window identity unchanged. This applies to immediate acquire, an open pending registration, and an acquire whose success or non-success reply has already committed while the Swapchain remains live. The rejection MUST NOT terminalize an acquire, alter its reply, signal or unsignal its Semaphore/Fence, or change any image state. If `DestroySurface` commits successfully first, no live Swapchain can reference that Surface; a later acquire naming a retired Swapchain fails XID resolution with `BadValue` and MUST NOT return `SURFACE_LOST` for the destroyed Surface. If the Swapchain XID has been reused, the request is evaluated only against the new resource's captured Surface identity.

- **DestroySurface versus QueuePresent:** Every valid present likewise requires a live Swapchain that retains its Surface. Thus `DestroySurface` MUST be rejected with `INVALID_SYNCHRONIZATION_STATE` while that Swapchain exists, including when QueuePresent is rejected before acceptance, when a presentation is accepted, and after its terminal and image-release milestones have both committed. A rejected Surface destroy MUST NOT alter the Surface/Window identity, image state, presentation token, wait reservations, operation terminal status, or event decisions. If `DestroySurface` commits successfully first, no valid Swapchain can remain through which a later QueuePresent could name that Surface; a request using a retired Swapchain fails with `BadValue` and has no token, wait, or backend side effects. If a Swapchain is destroyed first, a later Surface destroy may succeed only after all other Surface references required by the common resource-lifetime rules are quiescent; a QueuePresent racing after the Swapchain destroy observes the invalid Swapchain XID and fails with `BadValue`.

The serialization outcome is therefore constrained by the resource graph: a successful `DestroySurface` cannot overtake a valid acquire or present through a live Swapchain. The only successful order is retirement of every referencing Swapchain before Surface invalidation. A pending acquire or accepted presentation can delay that retirement indirectly by blocking `DestroySwapchain`; an acquired-but-idle image does not block Swapchain destruction by itself, but it does not permit direct Surface destruction while the Swapchain still exists. Window destruction is a separate asynchronous transition to `SURFACE_LOST`: it may race acquire/present and is resolved by their existing lifecycle precedence and serialization rules. Explicit `DestroySurface` MUST NOT synthesize that status or rewrite an already committed acquire/present result. Internal Window identity references remain retained until all operations and resource references are quiescent, and XID reuse MUST NOT redirect them.

## 6. Completion is three different things
Terminalization and image release are independent, serialized milestones and may occur in either order. A successful terminal outcome MUST NOT by itself make an image AVAILABLE or authorize IMAGE_RELEASED while backend access may continue. If release commits first, the image becomes reusable only after backend access has ended and the Swapchain, Surface, and Device are still usable; a later terminal callback MUST NOT repeat that release. If terminal SUCCESS commits first, the image remains PRESENT_PENDING until the release milestone. A resize, zero extent, Surface loss, or Device loss serialized between those milestones leaves the terminal status unchanged but invalidates the image/Swapchain and suppresses IMAGE_RELEASED. For PRESENTATION_FAILED, release is permitted only when the backend independently proves both that access has ended and that the image remains reusable in a usable Swapchain.


The presentation contract MUST distinguish at least these milestones:

- **GPU submission completion** — rendering commands have reached their terminal GPU outcome.
- **Image release / reacquisition eligibility** — the presentation system no longer needs the image and it can be acquired again.
- **Presentation completion** — the image has reached the presentation system's defined completion point for the target window.

These milestones may occur at different times. A normal QueueSubmit terminal event is not, by itself, proof that a submitted image has been displayed or released for reacquisition. Likewise, a successful present request reply should mean only what its normative reply contract says (for example, request accepted or operation queued), not necessarily that pixels have reached the screen.

Accepted presentation failures set the internal terminal status (`OUT_OF_DATE`, `SURFACE_LOST`, `DEVICE_LOST`, or `PRESENTATION_FAILED`) exactly once. If the image can be safely reused, the server performs the internal release transition; if not, it invalidates that image and the Swapchain instead. The server enqueues `PRESENTATION_COMPLETE` only when Queue mask bit 3 is set at the terminal point, and enqueues `IMAGE_RELEASED` only when the image is reusable and Queue mask bit 2 is set at the release point. Each event also requires that the original connection remains deliverable and that Device lifecycle rules permit event creation. Masking or suppressed delivery never skips terminal state changes, semaphore resolution, or backend-reference cleanup. These transitions never block the X11 request dispatcher.

## 7. Resize and swapchain replacement

A resize can make the old swapchain extent unsuitable while GPU work or presentation operations still refer to its images. The API must support a controlled replacement path: stop new acquisitions from the old swapchain, create a replacement using current capabilities, and destroy the old swapchain once all recording-command-buffer, submission, pending-acquire, accepted-presentation, and backend references that block destruction have drained. An acquired-but-idle image does not itself block destruction; successful `DestroySwapchain` invalidates that image and all image indices, so the client need not present or separately release it merely to retire the old swapchain.

The server must not free image backing storage while a queue submission, presentation operation, or backend access can still reference it. Public XIDs, if used for swapchains or surfaces, follow the existing immediate-public-invalidation and delayed-internal-release model. A logical Device has an independent, monotonically increasing internal generation (or equivalent non-reusable lifetime identity), distinct from every Swapchain generation. Every accepted QueuePresent operation and every terminal, image-release, and wait callback MUST capture both the Device identity/generation and the Swapchain identity/generation, as well as the accepted presentation token. Resolving a callback by a public Device XID, Swapchain XID, or token alone is forbidden. After DestroyDevice linearizes, the old Device XID may be reused for a newly created Device, but callbacks captured by the old Device MUST remain bound to the old internal object and its original semaphore objects. A callback whose captured Device generation does not match the target operation MUST be discarded without changing image state, terminal status, wait reservations, semaphore payload/trust state, device-loss state, or event delivery. Device loss reported by an old-generation callback MUST NOT propagate through semaphore-owner indexes into a replacement Device; semaphore ownership and callback holds are scoped to the exact Device/resource generation. The old callback MUST still be allowed to retire its own captured backend references and reservations. A replacement Swapchain may be created while the old Swapchain still exists, provided the new configuration passes validation against the current Surface state; creation does not implicitly destroy, retire, or transfer ownership from the old Swapchain.

A zero-sized or temporarily unpresentable window marks associated Swapchains OUT_OF_DATE and makes capabilities report temporarily not presentable. It must not force the client to destroy and recreate the X11 window. The client can retry after a later resize. Window destruction marks the Surface SURFACE_LOST and all associated Swapchains unusable; no new acquire or present is accepted, but already accepted operations still require a terminal outcome and safe backend release.

## 8. Initial scope and explicit non-goals

The presentation-capable profile should initially target presentation into ordinary X11 windows only. The following are not implied by this chapter and require separate design work:

- client-native VkXlibSurfaceKHR handles or client-side Vulkan WSI;
- pixmap presentation, XRender Pictures, RandR transforms, and arbitrary external image sharing;
- implicit cross-client or cross-device sharing of XAverius resources;
- a guarantee that every compute-capable physical device is also presentation-capable;
- a guarantee of a particular display timing, refresh interval, tearing policy, or physical scanout completion point unless explicitly reported by a future capability/extension contract.


## 10. Request/reply wire layouts

This section defines the fixed and variable layouts for the seven presentation-profile requests against the common XAverius header and X11 reply framing. Their subopcodes 41–47 are assigned append-only in the central registry. These requests remain profile-gated and are not part of the compute-only v0.1 request set. All offsets below include the standard 8-byte request header.

### CreateSurface — Void, 16 bytes

- Offset 8: XID `surface_xid` — client-allocated target XID
- Offset 12: XID `window_xid` — existing core X11 Window

On success, creates a connection-owned Surface and retains the exact internal Window identity. The `window_xid` must name a live core Window owned by the requesting X11 client connection. The target XID remains unallocated on failure.

### DestroySurface — Void, 12 bytes

- Offset 8: XID `surface_xid`

The Device is not part of this request because Surface is connection-owned rather than Device-owned. A live Swapchain referencing the Surface causes atomic rejection.

### GetSurfaceCapabilities — Request 16 bytes; variable-length Reply

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
| 60 | CARD32 | `queue_family_count` |

Variable payload follows at offset 64: `format_pair_count` records of 8 bytes (`CARD32 format_id`, `CARD32 color_space_id`), followed by `present_mode_count` CARD32 values, followed by `queue_family_count` records of 8 bytes (`CARD32 queue_family_index`, `CARD32 present_supported` where 0 means unsupported and 1 means supported). Each format/color-space pair MUST be assigned by the presentation format and mode registry, and each pair MUST occur at most once. Each presentation-mode ID MUST be assigned by that registry and MUST occur at most once. Unknown, reserved, or duplicate IDs are malformed capability replies. A successful capability reply MUST contain at least one queue-family record, and MUST contain exactly one record for every family returned by `GetPhysicalDeviceQueueFamilyProperties`, ordered by ascending index with no duplicates; a zero `queue_family_count` is invalid for a physical device. `present_supported` is 1 if and only if at least one queue-family record has `present_supported = 1`. Total reply size is `64 + 8 * format_pair_count + 4 * present_mode_count + 8 * queue_family_count`; therefore `reply.length = 8 + 2 * format_pair_count + present_mode_count + 2 * queue_family_count`. Counts and total size must be checked with wide arithmetic before allocation or serialization.

Status values: 0 SUCCESS; 1 TEMPORARILY_NOT_PRESENTABLE; 2 SURFACE_LOST; 3 DEVICE_LOST. CreateSwapchain status values are 0 SUCCESS; 1 OUT_OF_DATE; 2 SURFACE_LOST; 3 DEVICE_LOST; 4 UNSUPPORTED_CONFIGURATION; 5 ALLOCATION_FAILED. SUCCESS with `present_supported = 0` means the Device/Surface pair is valid but cannot present. TEMPORARILY_NOT_PRESENTABLE means the window has zero extent; it must set present_supported to 0 and all extent/count/format/mode/usage/queue-family fields to zero. SURFACE_LOST and DEVICE_LOST likewise return zero capability fields. Unknown or foreign resource XIDs are synchronous X11 errors, not status values.

### CreateSwapchain — Request 48 bytes; Reply 40 bytes

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

Reply payload at offset 32 is two CARD32 values: `status`, `actual_image_count`; total reply size is 40 bytes and `reply.length = 2`. The unused bytes at offsets 8–31 in this fixed reply MUST be zero. Before creation, the server validates the requested configuration against current capabilities: `image_count` must be within the reported minimum/maximum (where maximum 0 means unbounded), width and height must be within the reported extent bounds, the format/color-space pair and present mode must be reported, and every requested usage bit must be advertised. A zero-sized window or requested extent outside the current supported bounds returns `OUT_OF_DATE`; however, a requested width or height of zero is rejected earlier as `BadValue` during scalar validation. A syntactically valid but unsupported count, format/color-space pair, mode, usage combination, or Device/Surface pair returns `UNSUPPORTED_CONFIGURATION`. Success reports `actual_image_count` exactly equal to the requested `image_count`; every non-success reply sets `actual_image_count = 0` and leaves the target XID unallocated.

### DestroySwapchain — Void, 12 bytes

- Offset 8: XID `swapchain_xid`

Device ownership is inferred from the resource. Destruction is rejected while pending acquisition, queue work, accepted presentation, or backend access can still use its images. Acquired-but-idle images are invalidated with the Swapchain and do not independently prevent destruction.

### AcquireNextImage — Request 32 bytes; Reply 44 bytes

- Offset 8: XID `device_xid`
- Offset 12: XID `swapchain_xid`
- Offset 16: CARD64 `timeout_ns`; all ones means infinite
- Offset 24: XID `semaphore_xid`; zero means absent
- Offset 28: XID `fence_xid`; zero means absent

Reply payload at offset 32 is three CARD32 values: `status`, `image_index`, `reserved = 0`; total reply size is 44 bytes and `reply.length = 3`. The unused bytes at offsets 8–31 in this fixed reply MUST be zero. The image index is meaningful only for SUCCESS and must be zero on every non-success result. If both semaphore and fence are nonzero, both must be valid and eligible for acquisition signaling; neither is signaled on any non-success result, including DEVICE_DESTROYED. The semaphore, when present, must be binary.

### QueuePresent — Request variable length; Reply 36 bytes

Fixed request fields:

- Offset 8: XID `device_xid`
- Offset 12: CARD32 `queue_family_index`
- Offset 16: CARD32 `queue_index`
- Offset 20: XID `swapchain_xid`
- Offset 24: CARD32 `image_index`
- Offset 28: CARD32 `wait_semaphore_count`
- Offset 32: CARD64 `presentation_token` (nonzero and unique for the connection lifetime)
- Offset 40: `wait_semaphore_count` XID values for binary semaphores

Total request size is `40 + 4 * wait_semaphore_count`. The count must be positive only if the client uses explicit waits; zero is permitted when the image needs no additional queue dependency. Duplicate semaphore XIDs are invalid, and `presentation_token` must be nonzero. A token already used by an accepted presentation on this connection is rejected with `BadValue`; tokens from rejected attempts are not reserved. A reply contains one CARD32 status at offset 32; total reply size is 36 bytes and `reply.length = 1`. The unused bytes at offsets 8–31 in this fixed reply MUST be zero. QueuePresent reply status values are 0 SUCCESS, 1 OUT_OF_DATE, 2 SURFACE_LOST, and 3 DEVICE_LOST; these are local to this reply field and are not X11 error codes or presentation-event status values. SUCCESS means accepted, not displayed. OUT_OF_DATE, SURFACE_LOST, and DEVICE_LOST are status outcomes and do not consume waits or mutate image state as part of the rejected request. An independent lifecycle transition, especially Device loss, may already have invalidated the image. Synchronous validation errors are X11 errors and likewise leave all state unchanged. The nonzero `presentation_token` is reserved for uniqueness only when the request is accepted: the server checks it against tokens of previously accepted presentations and records it atomically with acceptance. A rejected request, including one returning a normal non-success status, does not reserve its token, so the client may use that token in a later attempt.

### Cross-request wire-length audit

The titles and framing are normative as follows; “request length” includes the eight-byte X11/XAverius request header, while reply length includes the standard 32-byte X11 reply header.

| Request | Request length | Reply length | Kind |
|---|---:|---:|---|
| CreateSurface | 16 bytes | none | Void |
| DestroySurface | 12 bytes | none | Void |
| GetSurfaceCapabilities | 16 bytes | variable: 64 bytes plus records | Reply |
| CreateSwapchain | 48 bytes | 40 bytes | Reply |
| DestroySwapchain | 12 bytes | none | Void |
| AcquireNextImage | 32 bytes | 44 bytes | Reply |
| QueuePresent | 40 + 4 × wait_semaphore_count bytes | 36 bytes | Reply |

The GetSurfaceCapabilities fixed reply is 64 bytes before any variable records, so its base reply length field is 8; the variable payload formula in the capability section adds the record contributions. All request-size calculations use checked wide arithmetic before reading variable arrays. The CreateSwapchain request's 48-byte size and 40-byte reply are distinct: the request carries ten CARD32/XID fields from offsets 8 through 44, while the reply carries status and actual_image_count after the 32-byte reply header. The QueuePresent reply is always 36 bytes regardless of wait count.

The protocol kind is determined by the response behavior, not by the request's own byte length. A reply-bearing request must send exactly one normal reply on success or a documented status outcome; an X11 error replaces that reply and MUST NOT be followed by a normal reply for the same request. Void requests send no normal reply.

The seven requests above are assigned append-only subopcodes 41–47 in the order listed above. The checker, request-audit matrix, error map, and conformance cases cover their layouts and assignments. These requests remain unavailable to compute-only servers; only a server advertising the presentation-capable profile may accept them.

## 11. Remaining validation work

The request subopcodes and presentation command-entry ID are assigned. Remaining work is implementation-level validation and maintenance of the profile-gated ABI:

1. Keep the seven request layouts and error precedence synchronized with the central registry, checker, and golden tests.
2. Run and retain CI evidence for the full static checker and wire-vector suite after ABI changes.
3. Test the profile against a real X11/XGE implementation and a Vulkan presentation backend; static checks do not prove runtime interoperability.
4. Add runtime tests for window resize/loss, acquisition timeout, semaphore consumption, and the distinct image-release/presentation-completion milestones.

The numeric assignments are stable and append-only. A compute-only implementation must continue rejecting presentation-only requests and event-mask bits.
