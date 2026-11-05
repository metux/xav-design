# OpenBSD CI repair — fallback static assertion macro

**Assignment:** one agent, one patch. Repository `X11Libre/xserver`, branch `wip/xaverius`, clean baseline `f6f3e87aa81724208496d539e40d2eee2c3d2641`.

## Observed failure

The baseline OpenBSD job in workflow run [42052262759](https://github.com/X11Libre/xserver/actions/runs/42052262759) fails compiling `Xext/xaverius/xaverius_proto.h`. The fallback macro currently token-pastes `__LINE__` directly:

```c
#define XAV_STATIC_ASSERT(c, m) \\
    typedef char xav_static_assert_##__LINE__[(c) ? 1 : -1]
```

Because a macro argument adjacent to `##` is not expanded first, every assertion declares the literal identifier `xav_static_assert___LINE__`. OpenBSD reports repeated typedef/redefinition errors. This is a source portability defect, not a VM provisioning failure.

## Required change

Make the smallest possible change in `Xext/xaverius/xaverius_proto.h`: use two-level token concatenation so `__LINE__` expands before it is pasted. Suggested implementation:

```c
#define XAV_STATIC_ASSERT_JOIN_IMPL(a, b) a##b
#define XAV_STATIC_ASSERT_JOIN(a, b) XAV_STATIC_ASSERT_JOIN_IMPL(a, b)
#define XAV_STATIC_ASSERT(c, m) \\
    typedef char XAV_STATIC_ASSERT_JOIN(xav_static_assert_, __LINE__)[(c) ? 1 : -1]
```

Keep the C++ `static_assert` and C11 `_Static_assert` branches unchanged. Keep the fallback C99-compatible. Undefine the two helper macros after the final assertions (alongside the existing assertion macro cleanup), so they do not leak into includers.

## Scope and prohibitions

- One file only unless a test genuinely requires a separate minimal test file.
- No wire layout, protocol constants, request/reply structures, ABI, or behavior changes.
- No formatting churn, renames, comment rewrites, or unrelated cleanup.
- Preserve license header, include order, and EOF newline.
- Do not touch Cygwin files or workflow configuration.
- Do not cherry-pick discarded registry commits or work on another branch.

## Verification

1. Build the full OpenBSD workflow job against this patch.
2. Exercise the fallback branch explicitly with a C99 compile/preprocess test on at least one available compiler; verify that multiple assertions produce distinct generated identifiers and compile cleanly. If OpenBSD is available, use its native compiler too.
3. Run the ordinary XAverius/Xserver build relevant to the branch.
4. Report exact commands, compiler versions, exit statuses, CI run/job links, and the resulting commit SHA.

**Deliverable:** one atomic commit on `wip/xaverius`, no PR split required; report before pushing if the expected file or macro differs from this baseline.