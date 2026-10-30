# XAverius design

Working design repository for the XAverius X11 extension exposing a server-side Vulkan API.

## Documents

- [Project status](PROJECT_STATUS.md) — baseline and next steps.
- [Decision log](DECISIONS.md) — settled, provisional, and open design decisions.
- [Specification index](spec/README.md) — normative chapter order and links.
- [Request subopcode registry](registries/request-subopcodes.md) — central inventory of 47 assigned request subopcodes: compute baseline 1–40 and presentation-profile-only 41–47; future additions are append-only. The v0.1 specification is frozen at `0e0ced45371a2548031c4b9d1370c1dead69d724` (verified by [CI run 41109805393](https://github.com/metux/xav-design/actions/runs/41109805393)); post-checkpoint normative deltas are reviewed in [the delta audit](audit/post-freeze-normative-delta-audit-2026-10-30.md).
- [Historical consolidated draft](wip/wip-2026-10-20.md) — preserved snapshot from 2026-10-20, **for historical reference only**; it is not normative where it differs from the current chapters or registries.

The current chapters under `spec/`, central registries under `registries/`, and their conformance checks are authoritative for the working design. The historical WIP is not a second normative source. For example, its older statement that BIG-REQUESTS follows standard X11 rules is superseded: `spec/wire-protocol.md` and `DECISIONS.md` explicitly disable BIG-REQUESTS for v0.1 because its extended-length field conflicts with the XAverius common header. The chapter split is organizational; it does not freeze unresolved protocol details or imply that every current draft rule has been fully reconciled.
