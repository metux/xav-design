# Owner verification checkpoint — 2026-11-11

This is a source/CI verification update to the existing Stages 1–4 registry work and W0-117/W0-121 follow-up. It does not create a new implementation task.

## Current Xserver remote state

- `X11Libre/xserver:wip/xaverius` HEAD: `18499fad39d2084e2a1f14a846200432f978649d`.
- Parent: `40c9268d5a26e1a9bcc7aa2e8c56e0f20402f179`.
- New commits on this current line include `8ecaf8e` (Meson non-Xorg adjustment), `7d45545` (ABI/OpenBSD fix), `40c9268` (registry Stages 1–4 implementation), and `18499fad` (registry test source).
- The previously recorded tip `6fc6471a5e307b3b3287e03b100e2acef6e84537` is **not an ancestor** of the current tip. Compare reports a diverged history, merge base `ee4bb3f96eec3b21c1961d54fe45cb33dc402d00`, current side 14 commits ahead and prior side 36 commits ahead of that base. Both SHAs remain addressable. This note does not infer how the branch changed; Defiant should explain the ancestry transition and preserve both histories without destructive Git operations.

## Exact-head CI

Actions run [42873000680](https://github.com/X11Libre/xserver/actions/runs/42873000680) targets exactly `18499fad39d2084e2a1f14a846200432f978649d` and completed **success**. The reported job set is green, including Ubuntu normal/debug/Valgrind/no-GBM, OpenBSD, FreeBSD, macOS, Solaris, Cygwin, NetBSD, DragonFlyBSD, Hurd, Alpine, Arch, MinGW, RHEL, SDK image, ABI check and driver builds. This resolves the earlier OpenBSD static-assert failure and the W0-117 non-Xorg Meson failure for this exact tip.

## Verified ABI progress

- `query_physical_snapshot` is now the normative two-argument typed ABI-v1 callback and its call site passes the binding and snapshot. The former three-argument form was not ABI-v1 conformant.
- `XaveriusModuleRoleDescriptor` and `XaveriusDeviceBackendRegistration` in the current DDX header now match the normative v1 field widths, typed hooks, owner-role pointer and generation fields.

## Remaining acceptance gaps

1. `XaveriusDeviceBackendOps` in `Xext/xaverius/xaverius_intern.h` still declares 64-bit `struct_size`/`abi_version` fields, while the normative descriptor uses `uint32_t`. Most top-level and nested operation callbacks still use generic `void *` signatures and mutable nested-table pointers, while ABI v1 specifies typed callbacks and const nested operation tables. The snapshot callback correction does not settle the rest of this descriptor ABI.
2. `test/xaverius-registry-test.c` now declares and calls production helpers including `xaverius_create_ordering_key`, `xaverius_compare_ordering_key`, and `xaverius_identity_equal`; it is no longer merely a local `strcmp` comparator duplicate. However, its Meson target is guarded by `if false`, so the file is not built or run by the green CI. The test therefore provides no executed production-comparator coverage. Its registration-size check only verifies that two locally mirrored structs have positive size; it does not validate registration behavior or ABI layout against the production header.
3. The branch ancestry transition from the previously recorded `6fc6471` tip needs a factual checkpoint/explanation. Do not reset, force-push, or discard either history.

Continue the existing work only. Keep the production ABI aligned with the normative spec and provide an executable, minimal test seam that does not reintroduce the `xorg_inc` or FreeBSD link regressions. Report exact source/test evidence and the branch ancestry explanation. No new implementation stream is authorized by this checkpoint.
