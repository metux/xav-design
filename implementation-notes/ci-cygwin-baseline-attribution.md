# Cygwin CI failure — independent baseline attribution

**Assignment:** independent investigation only; do not edit source or workflow files. Repository `X11Libre/xserver`.

## Question to answer

Is the Cygwin failure seen in workflow run [42052262759](https://github.com/X11Libre/xserver/actions/runs/42052262759) caused by XAverius changes on `wip/xaverius`, or does it also occur on an independent upstream baseline and therefore need a separate general Xserver CI PR?

The active clean XAverius baseline is `wip/xaverius` at `f6f3e87aa81724208496d539e40d2eee2c3d2641`. Compare it with the current authoritative upstream branch (normally `X11Libre/xserver:master`); record the exact SHA of every ref used. Also inspect the parent/preceding clean baseline where useful.

## Known facts — do not rediscover by assumption

- Job: `xserver-build-cygwin`, runner `windows-latest`.
- The workflow installs `python312-lxml` and `khronos-opengl-registry`; the job log showed `python312-lxml`, `libxml2_2`, and `libxslt` installed. Adding the lxml package again is not an acceptable proposed fix.
- The PATH step writes `PATH=/usr/bin:$(cygpath '$SYSTEMROOT')/system32` to `GITHUB_ENV`.
- The failure occurs when `hw/xwin/glx/gen_gl_wrappers.py` executes `from lxml import etree`; Python reports `ImportError: No such file or directory`.
- This is consistent with a compiled extension or one of its dependent DLLs failing to load, but the exact cause is not yet established. Do not state a missing DLL as fact until identified.

## Investigation procedure

1. Compare the exact files between `wip/xaverius@f6f3e87...` and the recorded upstream `master` SHA:
   - `.github/workflows/build-xserver.yml`
   - `.github/scripts/Cygwin/build.sh`
   - `hw/xwin/glx/gen_gl_wrappers.py`
   - any directly imported helper/configuration files relevant to this generator.
2. Determine whether any XAverius commit changed those files or changed the Python environment/build ordering indirectly. Report a path-limited diff, not just a general branch comparison.
3. Inspect the latest master CI run for the exact `xserver-build-cygwin` job. Record whether it passed, failed at the same import, failed elsewhere, or was not run. A different failure later in the job does not prove this import succeeds.
4. If no useful master run exists, request/trigger an isolated build on a temporary branch based on the recorded master SHA, with no XAverius changes. Do not modify master. If this cannot be done, state the evidence limitation explicitly.
5. Reproduce the import preflight on the same runner/environment immediately after PATH setup:
   ```sh
   /usr/bin/python3.12.exe -c 'from lxml import etree; print(etree.LXML_VERSION)'
   ```
6. On failure, locate the installed `etree*.dll` extension and run `cygcheck` on it and its dependencies. Capture the exact missing DLL/path and package ownership. Also record `python3.12.exe -c 'import sys; print(sys.executable); print(sys.path)'`, package versions, and PATH.
7. Distinguish:
   - branch-introduced source/workflow regression;
   - pre-existing Cygwin environment/toolchain issue;
   - transient mirror/cache/package installation issue;
   - runner/image issue;
   - inconclusive.

## Rules

- No source edits, no package changes, no Python version switch, no parser replacement.
- Do not infer branch attribution merely because the failure was first noticed on the XAverius branch.
- Do not infer upstream health from a skipped job.
- Coordinate findings with the Cygwin repair agent through the flagship/comms bus before that agent chooses the PR destination.
- Deliver a concise evidence report with exact SHAs, workflow/job URLs, changed-file diff, import output, and DLL diagnosis (or explain why unavailable).

**Deliverable:** attribution report only. No commit and no PR.