# Xaverius exact-tip CI build repair — 2026-11-08

Status: ACTIVE, narrow build-fix follow-up.

## Authoritative target

- Repository: `X11Libre/xserver`
- Branch: `wip/xaverius`
- Exact inspected HEAD: `79e59e48b903655586e50bd93617dede382e6aa6`
- Spec/coordination repository: `metux/xav-design@docs/restructure-2026-10-21`
- This note is an executable implementation assignment for Defiant. Do not implement Xserver source in the spec repository.

## Evidence at the exact tip

GitHub Actions run [42409419430](https://github.com/X11Libre/xserver/actions/runs/42409419430), created 2026-11-07 20:08Z, is completed with conclusion `failure` for the exact target SHA. Ubuntu job `128514104736` and Ubuntu Valgrind job `128514104778` fail compiling `Xext/xaverius/registry.c`; Ubuntu no-GBM job `128514104878` reproduces the same registry compile failure. The SDK-image job passing is not evidence that the Xserver source compiles.

Exact diagnostics in the Ubuntu `-Werror` build:

- Missing previous prototypes: `xaverius_next_generation_id` (`registry.c:37`), `XaveriusPhysicalDeviceTypeInit` (`:95`), `xaverius_identity_has_pci` (`:170`), `xaverius_identity_equal` (`:177`), `xaverius_module_role_descriptor_valid` (`:220`), `xaverius_find_module_role_by_generation` (`:349`), `xaverius_binding_alloc` (`:368`).
- Unused local `dev` in `XaveriusPhysicalDeviceDIXDestroy` (`:80`).
- Nested `/*` comment diagnostic at `registry.c:731` (`-Werror=comment`).

## Required work

1. Before editing, report exact branch, HEAD, merge-base, dirty status, and the intended declaration placement for every missing prototype. Preserve any pre-existing work; do not infer ownership from Git author/committer.
2. Inspect current declarations and call sites. Put declarations in the correct private/internal header or make truly file-local helpers `static` where appropriate. Do not expose implementation-private functions merely to silence `-Wmissing-prototypes`.
3. Remove the unused local only after verifying the destructor's intended ownership behavior. Do not restore canonical registry unlink/free behavior that conflicts with the tombstone/server-lifetime model.
4. Repair the malformed nested comment without broad formatting churn.
5. Preserve the comparator/ordering semantics and ModuleRole-owned `owner_key` model from the existing commits. Do not reintroduce `owner_key` into `XaveriusDeviceBackendRegistration` or binding structures.
6. Make one focused atomic commit and push it to `wip/xaverius`.
7. Run the focused registry/comparator tests and trigger CI on the new exact branch head. Report exact commands, exit codes, workflow run ID, and Ubuntu/SDK `-Werror` job conclusions. A green unrelated job or old run is not acceptance.

## Scope exclusions

- No DDX discovery, modesetting, ScreenAttachment, protocol handlers, Compute Memory handlers, or backend implementation changes in this repair.
- No broad refactor, gratuitous rename/reformat, force-push, reset, destructive cleanup, or merge of historical branches.
- Do not restart, relaunch, detach, replace, duplicate, or approve any existing session or pending Ask. If blocked by an Ask, report its exact ID and text.

## Completion report

Provide the full commit SHA and parent SHA, changed files, the exact source-level correction for each diagnostic, focused test results, and CI evidence for the new exact tip. Keep this task open until the exact-tip source build passes.