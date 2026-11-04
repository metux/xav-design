# PresentationRoute probe, pin, and retirement conformance

These vectors supplement the presentation lifecycle cases in [the main conformance matrix](conformance.md#presentation-lifecycle-race-and-atomicity-vectors). They exercise the DDX-binding-facing PresentationRoute lifetime independently of the public request/reply layouts.

## Capability query is a probe, not a lease

1. Query the same valid Device/Surface pair repeatedly. Each query MUST evaluate every queue family against the exact retained Window/Screen generation and return a coherent capability snapshot. No persistent PresentationRoute, bridge-resource lease, or Swapchain reference may remain solely because a query succeeded.
2. While the Device/DDX backend and Surface are usable, report no valid route. GetSurfaceCapabilities MUST return SUCCESS, a complete queue-family record set, and no present-capable queue. It MUST NOT return UNSUPPORTED_CONFIGURATION; that status belongs to CreateSwapchain.
3. Make the selected DDX binding/route temporarily unavailable while the Window has zero extent. GetSurfaceCapabilities MUST return DEVICE_UNAVAILABLE, not TEMPORARILY_NOT_PRESENTABLE. With the DDX backend available but the Surface lost and the Window extent zero, it MUST return SURFACE_LOST. With only a live zero-extent Surface, it MUST return TEMPORARILY_NOT_PRESENTABLE.
4. For every non-success capability status, verify the fixed 64-byte reply and zero all capability fields, counts, and variable arrays.

## CreateSwapchain pins the route generation

1. After a successful capability query, change the Screen/scanout/bridge route generation before Swapchain commit. The server MUST NOT publish a Swapchain using the stale query snapshot or stale provisional route. It MUST return OUT_OF_DATE, leave the target XID unallocated, and retire all provisional route/swapchain objects and references exactly once.
2. Repeat with a route that remains current through commit. The successful Swapchain MUST capture the exact Device, Surface, Window, Screen, DDX backend, and PresentationRoute generations. A later route-generation change invalidates that Swapchain as OUT_OF_DATE; it MUST NOT transparently rebind it.
3. Inject temporary route unavailability during route preparation. Return DEVICE_UNAVAILABLE, not UNSUPPORTED_CONFIGURATION, and publish no Swapchain. Inject a currently unsupported route with no temporary outage and require UNSUPPORTED_CONFIGURATION.
4. Inject a DDX backend allocation failure after all validation and route eligibility checks. Return ALLOCATION_FAILED; leave the target XID unallocated and unwind provisional resources in reverse dependency order.

## Route retirement and quarantine

1. Accept QueuePresent on a live Swapchain, then begin Swapchain destruction through the permitted lifecycle path. Public invalidation MUST NOT destroy the DDX backend route while accepted operations or backend accesses can still reference it.
2. Once all accepted operation tokens have terminalized and successfully retired, destroy the DDX backend Swapchain before destroying its PresentationRoute. Only then may Screen/scanout/bridge references be released.
3. Make DDX backend Swapchain destruction fail or remain unproven. The route and all dependent references MUST remain retained/quarantined; do not call route destruction if it could invalidate resources still used by the DDX backend Swapchain.
4. Make route destruction fail or remain unproven after DDX backend Swapchain destruction. Keep the route, DDX backend context, and its Screen/scanout/bridge references quarantined. A terminal callback alone is not proof of quiescence.
5. Repeat through DestroyDevice and client disconnect. Public XIDs and event delivery are invalidated/suppressed according to their existing contracts, but captured DDX backend objects and route references remain until exact-token retirement and DDX backend destruction prove quiescence.
6. During failed CreateSwapchain preparation, if a DDX backend Swapchain was created, destroy it before destroying the provisional route. Verify each provisional reference is released exactly once and no failed request leaves a persistent PresentationRoute.

## Mixed lifecycle status precedence

For valid XIDs, types, and ownership, test all combinations and require:
- GetSurfaceCapabilities: DEVICE_LOST > DEVICE_UNAVAILABLE > SURFACE_LOST > TEMPORARILY_NOT_PRESENTABLE > SUCCESS.
- CreateSwapchain: DEVICE_LOST > DEVICE_UNAVAILABLE > SURFACE_LOST > OUT_OF_DATE > UNSUPPORTED_CONFIGURATION; allocation failure is reachable only after these checks.
- AcquireNextImage: DEVICE_LOST > DEVICE_UNAVAILABLE > SURFACE_LOST > OUT_OF_DATE, before synchronization eligibility or timeout.
- Pre-acceptance QueuePresent: DEVICE_LOST > DEVICE_UNAVAILABLE before queue/index validation; on a usable Device, invalid queue/index is BadValue, then SURFACE_LOST > OUT_OF_DATE, then unsupported queue presentation is BadMatch, then token/image/wait mutable-state checks.
- For an already accepted QueuePresent, preserve its first committed terminal outcome. Route-only unavailability without a more specific lifecycle cause produces PRESENTATION_FAILED; route-generation invalidation produces OUT_OF_DATE only when it wins the operation's terminalization gate. Neither result by itself declares the logical Device lost.

Every vector MUST assert public XID state, route/DDX backend/resource generations, operation-token retirement, and exactly-once reference release, not only the visible status.