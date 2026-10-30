# Final cross-document specification audit — 2026-10-30

## Scope

Completed the final content-consistency pass against candidate commit `6273ed8916b2c6053425bbc6afceb266c39c348e`. Reviewed the normative chapters under `spec/`, central registries under `registries/`, the request/error audit, conformance vectors, project status, decision log, freeze checklist, and existing focused audit records.

## Results

- **Request inventory:** all 47 assigned request contracts remain present and profile-correct: compute-baseline subopcodes 1–40 and presentation-capable-profile subopcodes 41–47. The central registry, request audit matrix, defining chapters, request-kind/reply-length contract, and checker inventory agree. No subopcode was added, removed, or renumbered in this pass.
- **Other numeric namespaces:** the compute event IDs remain 0–6; presentation event IDs remain 7–8 and profile-gated; error offsets remain contiguous 0–8; command-entry IDs remain 1–5 with entry 5 presentation-only. Descriptor, shader-stage, queue-flag, device-type, reason-code, and physical-device-property registries remain authoritative. The v0.1 feature-ID and optional device-extension registries remain intentionally empty.
- **Profile boundary:** the compute baseline remains the initial implementation target. The presentation-capable profile remains separately gated; its assigned request/event/command-entry contracts do not imply implementation support. Corrected the decision log so it no longer says presentation opcodes and layouts are unassigned.
- **Wire and error contracts:** the common framing and validation order remain consistent with request-specific exceptions; presentation layouts, request precedence, reply/event framing, and the resource/submission lifecycle rules agree with their registries and conformance sections. The prior focused audits for resource lifetime, retained layouts, QueueSubmit/destruction ordering, and presentation requests remain applicable.
- **Conformance hygiene:** removed duplicate ASYNC_ERROR prose, corrected two doubled terminal periods, strengthened the retained ASYNC_ERROR token requirement, and removed obsolete provisional labels from the assigned presentation request matrix, command entry, and profile conformance cases.
- **Status metadata:** corrected the overview's stale "design draft/not frozen" wording and the project status's stale checkpoint/next-step summary. Updated the style guide to preserve unambiguous legacy German passages during this finalization pass while requiring new or materially revised normative text to be English. This is editorial only; no protocol semantics or wire values changed.
- **Local references:** checked 180 local Markdown link occurrences across the specification, registry, and audit documents against the repository tree; no missing local targets were found. Checked the specification's explicit heading anchors; normalized the presentation-only command-entry heading so its registry link resolves unambiguously.

## Open items and scope boundary

No unresolved v0.1 wire-design decision or missing request assignment was identified in this pass. The remaining open items are implementation acceptance only:

1. Live X11/XGE interoperability, including dynamic extension-opcode discovery and event delivery.
2. End-to-end compute behavior against a real Vulkan backend, including visibility, synchronization, readback, and teardown.
3. Runtime concurrency, Device Loss, late callbacks, disconnect, and backend-quiescence behavior.
4. Presentation backend validation if the optional presentation-capable profile is implemented.

These gates must remain explicitly open until tested against an actual server/backend. Static tests and reference models do not establish runtime conformance.

## Verification

The final candidate commit `38587be1b70868224e8f8941750a7c1aa1e19dd7` passed [CI run 41088183365](https://github.com/metux/xav-design/actions/runs/41088183365): 4,695 wire-layout/documentation checks, 72 Timeline regression tests, 673 Python tests, and the required-check presence audit all succeeded. The specification-content freeze is recorded at that commit. No implementation acceptance gate is claimed as passed.
