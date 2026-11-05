# Cygwin CI repair — isolated patch

**Assignment:** one agent owns diagnosis and repair. Repository `X11Libre/xserver`. Do not overlap edits with the OpenBSD patch.

## Goal

Repair the Cygwin `xserver-build-cygwin` failure at `from lxml import etree` in `hw/xwin/glx/gen_gl_wrappers.py`, but only after establishing the exact technical cause. Coordinate with the independent attribution agent and the flagship before selecting the patch destination.

## Starting evidence

Workflow run [42052262759](https://github.com/X11Libre/xserver/actions/runs/42052262759), job `xserver-build-cygwin`, fails during generation of WGL/GL shim files. The job already requests `python312-lxml`; logs show `libxml2_2` and `libxslt` too. Do not simply add those package names again.

The workflow sets PATH using:

```sh
echo "PATH=/usr/bin:$(cygpath '$SYSTEMROOT')/system32" >> "$GITHUB_ENV"
```

A diagnostic preflight should run immediately after this step:

```sh
/usr/bin/python3.12.exe -c 'from lxml import etree; print(etree.LXML_VERSION)'
```

If that fails, locate the installed `etree*.dll` and use Cygwin `cygcheck` to identify the exact unresolved dependency. Capture Python executable/version/sys.path, package versions, PATH and the dependency output. The current DLL-loading hypothesis is not yet a proven diagnosis.

## Patch routing decision

Use the independent attribution report:
- If the same failure reproduces on an unchanged upstream `master` baseline, prepare a standalone general Xserver CI PR based on master. Do not mix it into XAverius-specific history.
- If evidence shows a regression introduced by `wip/xaverius`, prepare the fix as a separate commit/PR for the XAverius branch.
- If evidence is inconclusive, do not guess the destination or open a PR yet; report the blocker to the flagship.

The patch itself must remain independent from the OpenBSD patch.

## Acceptable repair

Only make the smallest change supported by evidence, for example correcting the Cygwin PATH/runtime dependency setup or adding a precise preflight/diagnostic that exposes the actual missing dependency. Add a package only if its absence is proven. Do not:
- add `python312-lxml` a second time;
- switch Python versions;
- replace Khronos XML parsing or vendor a new parser;
- mask import failures or skip wrapper generation;
- add broad PATH entries without explaining the DLL-resolution requirement;
- change unrelated Cygwin or non-Cygwin jobs.

## Verification

1. Reproduce the original failure before the fix, if the environment is available.
2. Verify the preflight succeeds after the fix and reports the lxml version.
3. Run the complete `xserver-build-cygwin` job on the selected target branch.
4. Ensure wrapper generation completes and the remaining Cygwin build and test steps pass.
5. If the fix is general, validate on master-based PR CI; if branch-specific, validate on `wip/xaverius`.
6. Report exact commit/base SHAs, commands, package/DLL evidence, CI run/job URL, and outcomes.

## Scope and hygiene

- One atomic patch, limited to the exact cause and required tests/diagnostics.
- Preserve workflow style and existing package list ordering.
- No formatting churn, cosmetic refactors, unrelated dependency upgrades, or changes to OpenBSD.
- Do not push to master. Open a PR only after attribution and target branch are agreed with the flagship.

**Deliverable:** one minimal Cygwin fix patch with evidence-backed PR destination, or a report explaining why no safe patch can yet be proposed.