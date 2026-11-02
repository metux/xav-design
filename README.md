# XAverius design

Working design repository for the XAverius X11 extension exposing a server-side Vulkan API.

## Documents

- [Project status](PROJECT_STATUS.md) — baseline and next steps.
- [Decision log](DECISIONS.md) — settled, provisional, and open design decisions.
- [Specification index](spec/README.md) — normative chapter order and links.
- [Request subopcode registry](registries/request-subopcodes.md) — central inventory of 48 assigned request subopcodes: common bootstrap QueryVersion 0, compute baseline 1–40, and presentation-profile-only 41–47; future additions are append-only. The v0.1 normative content is freeze-ready at exact candidate `61e4e5517c94074d11cb5319f747528a8fc3f148`, verified by [CI run 41442418120](https://github.com/metux/xav-design/actions/runs/41442418120): 4,823 static checks, 72 Timeline regressions, 685 Python tests, and required-check audit all passed. Implementation coordination still awaits Phase 1 ship confirmations and a named shared integration-interface owner; live X11/XGE and Vulkan acceptance remain separate. See the [freeze checklist](spec/freeze-checklist.md) and [request audit](spec/request-audit.md).
- [Historical consolidated draft](wip/wip-2026-10-20.md) — preserved snapshot from 2026-10-20, **for historical reference only**; it is not normative where it differs from the current chapters or registries.

The current chapters under `spec/`, central registries under `registries/`, and their conformance checks are authoritative for the working design. The historical WIP is not a second normative source. For example, its older statement that BIG-REQUESTS follows standard X11 rules is superseded: `spec/wire-protocol.md` and `DECISIONS.md` explicitly disable BIG-REQUESTS for v0.1 because its extended-length field conflicts with the XAverius common header. The chapter split is organizational; it does not freeze unresolved protocol details or imply that every current draft rule has been fully reconciled.
