# Project status

**Project:** XAverius — an X11 extension for network-transparent Vulkan access  
**Specification baseline:** v0.1 consolidated working draft, 2026-10-20  
**Implementation target:** Xvfb, compute-only initial implementation  
**Status:** Design work in progress; wire protocol and registries are not frozen.

## Working rules

1. The historical consolidated draft remains unchanged as a reference baseline.
2. Chapter files are a structural split, not an assertion that every sentence is final.
3. Mark decisions as settled, provisional, or open; do not turn a proposal into a normative rule without review.
4. Before editing, reread the current repository state and check related chapters for consistency.
5. Keep changes on a topic branch and review the diff before merging to `master`.
6. Wire-format rules should be defined centrally and referenced from request descriptions rather than repeated.
7. Do not assign unregistered numeric opcodes or registry values ad hoc.

## Immediate next steps

- Review the chapter split and adjust boundaries if needed.
- Reconcile the 64 KiB XAverius request/segmentation proposal with the older BIG-REQUESTS wording in the historical draft.
- Finalize request/reply layouts and central registries.
- Resolve the open issues listed in [the specification](spec/08-reference-tests-open-issues.md).
- Add conformance tests alongside protocol decisions.
