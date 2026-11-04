# XAverius design

Working design repository for the XAverius X11 extension exposing a server-side Vulkan API.

## Documents

- [Shared protocol headers](protocol/README.md) — common C wire declarations for server and client consumers.
- [Project status](PROJECT_STATUS.md) — current branch verification and next steps.
- [Decision log](DECISIONS.md) — settled, provisional, and open design decisions.
- [Specification index](spec/README.md) — normative chapter order and links, including the registry API lifetime addendum.
- [Request subopcode registry](registries/request-subopcodes.md) — central inventory of 48 assigned request subopcodes: common bootstrap QueryVersion 0, compute baseline 1–40, and presentation-profile-only 41–47; future additions are append-only.
- [Registry API architecture](spec/device-registry-architecture.md) — server-wide PhysicalDevice inventory, DDX-owned direct device bindings, discovery, ScreenAttachment, and PresentationRoute ownership.
- [Registry API lifetime addendum](spec/registry-api-lifetime-addendum.md) — current direct-binding lifetime rules, module-role lease sharing, exact removal barriers, and token confinement.
- [DDX backend operation matrix](spec/provider-operation-matrix.md) — exhaustive mapping of all requests to DDX backend/server work and the concrete typed operation tables.
- [Historical consolidated draft](wip/wip-2026-10-20.md) — preserved snapshot from 2026-10-20, **for historical reference only**; it is not normative where it differs from the current chapters or registries.

The current chapters under `spec/`, central registries under `registries/`, and their conformance checks are authoritative for the working design. The historical WIP is not a second normative source. For example, its older statement that BIG-REQUESTS follows standard X11 rules is superseded: `spec/wire-protocol.md` and `DECISIONS.md` explicitly disable BIG-REQUESTS for v0.1 because its extended-length field conflicts with the XAverius common header. The chapter split is organizational; it does not freeze unresolved protocol details or imply that every current draft rule has been fully reconciled.
