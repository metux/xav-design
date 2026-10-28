#!/bin/sh
# Find likely XAverius server / Vulkan backend implementations.
# Read-only; searches Git worktrees and CMake/Meson projects without Git metadata.
# Usage: tools/find-xav-backend.sh [--all] [search-root ...]
# MAX_DEPTH controls project discovery depth (default: 8).
set -eu
PROGRAM=${0##*/}
MAX_DEPTH=${MAX_DEPTH:-8}
ALL=0
ROOTS=""
usage() {
    cat <<EOF
Usage: $PROGRAM [--all] [search-root ...]
Search Git repositories and CMake/Meson projects for XAverius server code and
Vulkan backend calls. Filters test, specification, generated, and build files.
With no roots, searches existing paths among HOME/src, HOME/dev, HOME/git,
HOME/projects, HOME/work, and /media.
Options: --all (also search /opt, /srv, /workspace, /workspaces), -h/--help
Environment: MAX_DEPTH (default 8)
EOF
}
while [ "$#" -gt 0 ]; do
    case "$1" in
        --all) ALL=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; while [ "$#" -gt 0 ]; do ROOTS="$ROOTS
$1"; shift; done ;;
        -*) echo "$PROGRAM: unknown option: $1" >&2; usage >&2; exit 2 ;;
        *) ROOTS="$ROOTS
$1"; shift ;;
    esac
done
if [ -z "$ROOTS" ]; then
    for d in "$HOME/src" "$HOME/dev" "$HOME/git" "$HOME/projects" "$HOME/work" /media; do
        [ ! -d "$d" ] || ROOTS="$ROOTS
$d"
    done
    if [ "$ALL" -eq 1 ]; then
        for d in /opt /srv /workspace /workspaces; do
            [ ! -d "$d" ] || ROOTS="$ROOTS
$d"
        done
    fi
fi
[ -n "$ROOTS" ] || { echo "$PROGRAM: pass at least one search root" >&2; exit 2; }
SEARCHER=grep
command -v rg >/dev/null 2>&1 && SEARCHER=rg
tmp=${TMPDIR:-/tmp}/find-xav-backend.$$
(umask 077 && mkdir "$tmp") || { echo "$PROGRAM: cannot create temporary directory" >&2; exit 2; }
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
repos="$tmp/repos"; projects="$tmp/projects"; markers="$tmp/markers"; matches="$tmp/matches"
: >"$repos"; : >"$projects"; : >"$markers"; : >"$matches"
pruned='node_modules|.cache|.local|target|build|out|.venv|venv|vendor|third_party|third-party|generated|autogen|gen|dist|coverage|.zig-cache|zig-out|CMakeFiles|meson-private|meson-logs|_build'
find_repo_dirs() {
    root=$1; [ -d "$root" ] || return
    find "$root" -maxdepth "$MAX_DEPTH" \
        \( -type d \( -name node_modules -o -name .cache -o -name .local -o -name target -o -name build -o -name out -o -name .venv -o -name venv \) -prune \) -o \
        \( -type d -name .git -print -prune \) -o \( -type f -name .git -print \) 2>/dev/null
}
find_build_projects() {
    root=$1; [ -d "$root" ] || return
    find "$root" -maxdepth "$MAX_DEPTH" \
        \( -type d \( -name .git -o -name node_modules -o -name .cache -o -name .local -o -name target -o -name build -o -name out -o -name .venv -o -name venv -o -name vendor -o -name third_party -o -name third-party -o -name generated -o -name autogen -o -name gen -o -name dist \) -prune \) -o \
        \( -type f \( -name CMakeLists.txt -o -name meson.build \) -print \) 2>/dev/null
}
printf '%s\n' "$ROOTS" | while IFS= read -r root; do [ -z "$root" ] || find_repo_dirs "$root"; done |
while IFS= read -r p; do case "$p" in */.git) printf '%s\n' "${p%/.git}";; *) dirname "$p";; esac; done | sort -u >"$repos"
printf '%s\n' "$ROOTS" | while IFS= read -r root; do [ -z "$root" ] || find_build_projects "$root"; done |
while IFS= read -r p; do dirname "$p"; done | sort -u >"$markers"
cat "$repos" >"$projects"
while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    nested=0
    while IFS= read -r gitrepo; do case "$candidate/" in "$gitrepo/"*) nested=1; break;; esac; done <"$repos"
    [ "$nested" -eq 1 ] || printf '%s\n' "$candidate" >>"$projects"
done <"$markers"
sort -u "$projects" -o "$projects"
[ -s "$projects" ] || { echo "No Git repositories or CMake/Meson projects found."; exit 1; }

is_excluded() {
    case "$1" in
      */.git/*|*/build/*|*/build-*/*|*/out/*|*/target/*|*/node_modules/*|*/vendor/*|*/third_party/*|*/third-party/*|*/external/*|*/generated/*|*/autogen/*|*/auto-generated/*|*/gen/*|*/dist/*|*/coverage/*|*/.cache/*|*/.venv/*|*/venv/*|*/.zig-cache/*|*/zig-out/*|*/CMakeFiles/*|*/meson-private/*|*/meson-logs/*|*/_build/*|*/bazel-*/*|*/test/*|*/tests/*|*/testing/*|*/spec/*|*/specs/*|*/docs/*|*/doc/*|*/documentation/*|*/audit/*|*/wip/*|*/fixtures/*|*/golden/*|*/reference-model/*|*/reference_model/*|*/benchmark/*|*/benchmarks/*|*/examples/*|*/samples/*) return 0 ;;
      *.md|*.rst|*.txt|*.adoc|*.json|*.yaml|*.yml|*.toml|*.xml|*.svg|*.lock|*.map|*.min.js|*.min.css|*.pb.go|*.generated.go|*.designer.cs|*.g.cs|*.gen.cs|*.freezed.dart|*.g.dart|*.moc.cpp|moc_*.cpp|qrc_*.cpp|ui_*.h|*_pb2.py|*_generated.*|*.generated.*|*.gen.*|*.autogen.*|*.freezed.*|*.gr.dart|*test*.c|*test*.h|*test*.cc|*test*.cpp|*test*.hpp|*test*.rs|*test*.zig|*test*.go|*_test.*|*_spec.*|*.spec.*|*.tests.*|*_mock.*|*_stub.*|mock_*.c|mock_*.cpp|stub_*.c|stub_*.cpp) return 0 ;;
      *state_model*|*wire_layout*|*protocol_spec*|*golden_wire*|*mock*|*stub*) return 0 ;;
      *) return 1 ;;
    esac
}
is_source() {
    case "$1" in
      *.c|*.h|*.cc|*.hh|*.cpp|*.hpp|*.cxx|*.hxx|*.rs|*.zig|*.go|*.m|*.mm|*.swift|*.java|*.kt|*.kts|*.cs|*.py|*.pyi|*.js|*.jsx|*.ts|*.tsx|*.d|*.nim|*.odin|*.v|*.vala|*.pas|*.pp|*.f|*.f90|*.f95|*.f03|*.adb|*.ads) return 0 ;;
      *) return 1 ;;
    esac
}
scan_project() {
    repo=$1
    remote=$(git -C "$repo" remote get-url origin 2>/dev/null || :)
    branch=$(git -C "$repo" branch --show-current 2>/dev/null || :)
    if git -C "$repo" rev-parse --show-toplevel >/dev/null 2>&1; then kind="Git project"; else kind="CMake/Meson project (no Git metadata)"; fi
    printf '\n=== PROJECT: %s ===\ntype: %s\n' "$repo" "$kind"
    [ -z "$remote" ] || printf 'origin: %s\n' "$remote"
    [ -z "$branch" ] || printf 'branch: %s\n' "$branch"
    files="$tmp/files"
    if [ "$kind" = "Git project" ]; then
      git -C "$repo" ls-files --cached --others --exclude-standard 2>/dev/null |
      while IFS= read -r f; do is_source "$f" || continue; is_excluded "/$f" && continue; printf '%s\n' "$f"; done >"$files"
    else
      find "$repo" \( -type d \( -name .git -o -name node_modules -o -name .cache -o -name target -o -name build -o -name out -o -name vendor -o -name third_party -o -name third-party -o -name generated -o -name autogen -o -name gen -o -name dist -o -name coverage -o -name .venv -o -name venv -o -name .zig-cache -o -name zig-out \) -prune \) -o \( -type f -print \) 2>/dev/null |
      while IFS= read -r full; do f=${full#"$repo"/}; is_source "$f" || continue; is_excluded "/$f" && continue; printf '%s\n' "$f"; done >"$files"
    fi
    score=0; xav=0; x11=0; vk=0; sync=0; calls=0; dispatch=0; : >"$matches"
    while IFS= read -r f; do
      full="$repo/$f"; [ -f "$full" ] || continue
      case "$f" in *state_model*|*wire_layout*|*protocol_spec*|*golden_wire*|*mock*|*stub*) continue;; esac
      if [ "$SEARCHER" = rg ]; then
        a=$(rg -n -i 'XAverius|Xaverius|xav_[[:alnum:]_]*|XAV_[[:alnum:]_]*' "$full" 2>/dev/null || :)
        b=$(rg -n 'AddExtension|CreateExtension|ProcVector|SProcVector|Dispatch.*Request|dixLookupResource|Xvfb' "$full" 2>/dev/null || :)
        c=$(rg -n '\b(vk[A-Z][A-Za-z0-9_]*|VK_[A-Z0-9_]+)\b' "$full" 2>/dev/null || :)
        d=$(rg -n -i 'semaphore|queue.?submit|queue.?present|device.?lost|device.?loss|wait_semaphores|signal_semaphore|cmd_dispatch|dispatch_workgroups|create_device|create_instance' "$full" 2>/dev/null || :)
        code=$(rg -n -v '^\s*(//|/\*|\*|\*/|#|--|;)' "$full" 2>/dev/null || :)
      else
        a=$(grep -n -i -E 'XAverius|Xaverius|xav_[[:alnum:]_]*|XAV_[[:alnum:]_]*' "$full" 2>/dev/null || :)
        b=$(grep -n -E 'AddExtension|CreateExtension|ProcVector|SProcVector|Dispatch.*Request|dixLookupResource|Xvfb' "$full" 2>/dev/null || :)
        c=$(grep -n -E '\b(vk[A-Z][A-Za-z0-9_]*|VK_[A-Z0-9_]+)\b' "$full" 2>/dev/null || :)
        d=$(grep -n -i -E 'semaphore|queue.?submit|queue.?present|device.?lost|device.?loss|wait_semaphores|signal_semaphore|cmd_dispatch|dispatch_workgroups|create_device|create_instance' "$full" 2>/dev/null || :)
        code=$(grep -n -E -v '^[[:space:]]*(//|/\*|\*|\*/|#|--|;)' "$full" 2>/dev/null || :)
      fi
      if [ -n "$a" ]; then xav=$((xav+1)); printf '  XA: %s\n%s\n' "$f" "$a" >>"$matches"; fi
      if [ -n "$b" ]; then x11=$((x11+1)); printf '  X11: %s\n%s\n' "$f" "$b" >>"$matches"; fi
      if [ -n "$c" ]; then vk=$((vk+1)); printf '  VK: %s\n%s\n' "$f" "$c" >>"$matches"; fi
      if [ -n "$d" ]; then sync=$((sync+1)); printf '  SYNC: %s\n%s\n' "$f" "$d" >>"$matches"; fi
      if [ -n "$code" ]; then
        call=$(printf '%s\n' "$code" | grep -E '(vk[A-Z][A-Za-z0-9_]*|queue_submit(_2)?|queueSubmit(_2)?|queue_present|queuePresent|wait_semaphores|waitSemaphores|signal_semaphore|signalSemaphore|cmd_dispatch|dispatch_workgroups|create_device|createDevice|create_instance|createInstance)[[:space:]]*\(' 2>/dev/null || :)
        call=$(printf '%s\n' "$call" | grep -E '(=|return[[:space:]]|\{|\}|unsafe[[:space:]]*\{|try!?[[:space:]]*\(|\.)' 2>/dev/null || :)
        if [ -n "$call" ]; then calls=$((calls+1)); printf '  VK-CALL: %s\n%s\n' "$f" "$call" >>"$matches"; fi
        req=$(printf '%s\n' "$code" | grep -E '(Proc|SProc)[A-Za-z0-9_]*(Req|Request)|REQUEST_(SIZE|HEADER|DATA|FIXED_SIZE)|REQUEST_AT_LEAST_SIZE|REQUEST_FIXED_SIZE|REQUEST_SIZE_MATCH|dispatch.*request|request.*dispatch|proc_vector|sproc_vector|ProcVector|SProcVector' 2>/dev/null || :)
        if [ -n "$req" ]; then dispatch=$((dispatch+1)); printf '  X11-DISPATCH: %s\n%s\n' "$f" "$req" >>"$matches"; fi
      fi
    done <"$files"
    [ "$xav" -eq 0 ] || score=$((score+3))
    [ "$x11" -eq 0 ] || score=$((score+1))
    [ "$vk" -eq 0 ] || score=$((score+1))
    [ "$sync" -eq 0 ] || score=$((score+1))
    [ "$dispatch" -eq 0 ] || score=$((score+6))
    [ "$calls" -eq 0 ] || score=$((score+7))
    [ "$xav" -eq 0 ] || [ "$dispatch" -eq 0 ] || score=$((score+4))
    [ "$xav" -eq 0 ] || [ "$calls" -eq 0 ] || score=$((score+5))
    [ "$dispatch" -eq 0 ] || [ "$calls" -eq 0 ] || score=$((score+5))
    printf 'Signals: XAverius-files=%s X11-files=%s X11-dispatch-files=%s Vulkan-symbol-files=%s Vulkan-call-files=%s sync-files=%s SCORE=%s\n' "$xav" "$x11" "$dispatch" "$vk" "$calls" "$sync" "$score"
    [ "$score" -eq 0 ] || cat "$matches"
}
while IFS= read -r p; do [ -z "$p" ] || scan_project "$p"; done <"$projects"
exit 0
