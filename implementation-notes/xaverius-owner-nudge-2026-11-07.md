---
id: W0-20261107-102
kind: owner-nudge
from: owner-coordination
to: Defiant
created: 2026-11-07T23:16:06Z
in_reply_to: xaverius-exact-tip-build-repair-2026-11-08
task_ref: implementation-notes/xaverius-exact-tip-build-repair-2026-11-08.md
correlation_id: defiant-xaverius-exact-tip-nudge-102
---

# Owner nudge — report and finish the exact-tip Xaverius build repair

This is a progress nudge for the existing bounded assignment, not a new or expanded task.

The authoritative implementation target remains `X11Libre/xserver:wip/xaverius`; the spec-side assignment remains the implementation note linked above. The last verified source tip was `79e59e48b903655586e50bd93617dede382e6aa6`, with failed exact-tip CI run `42409419430`.

Please promptly:
1. Report the current exact branch, HEAD, merge-base, dirty status, and any uncommitted paths before editing.
2. State whether the seven missing prototypes, unused local, and nested-comment diagnostic have been corrected in source. Give exact file/line references and the new commit SHA if committed.
3. Run or trigger CI on the exact pushed tip; report the run ID and the source-build job conclusions/log evidence, not merely SDK-image success or a commit-message claim.
4. If not finished, continue only the existing narrow build-repair task. Preserve tombstone/server-lifetime semantics and ModuleRole-owned `owner_key`; do not expand into DDX discovery, modesetting, ScreenAttachment, protocol handlers, Compute Memory, or broad refactoring.

Do not restart, relaunch, detach, replace, duplicate, or approve any existing session or pending Ask. Do not reset, force-push, or discard work. Reply with concrete evidence and blockers.
