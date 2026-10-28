#!/bin/sh
# Find likely XAverius server / Vulkan backend implementations.
# Read-only; searches Git worktrees and CMake/Meson projects without Git metadata.
# Usage: tools/find-xav-backend.sh [--all] [search-root ...]
# MAX_DEPTH controls project discovery depth (default: 8).
set -eu
PROGRAM=${0##*/}
MAX_DEPTH=${MAX_DEPTH:-8}
case "$MAX_DEPTH" in ""|*[!0-9]*) echo "$PROGRAM: MAX_DEPTH must be a non-negative integer" >&2; exit 2 ;; esac
ALL=0
ROOTS=""
NL='
'
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
        --) shift; while [ "$#" -gt 0 ]; do ROOTS="${ROOTS}${NL}$1"; shift; done ;;
        -*) echo "$PROGRAM: unknown option: $1" >&2; usage >&2; exit 2 ;;
        *) ROOTS="${ROOTS}${NL}$1"; shift ;;
    esac
done
if [ -z "$ROOTS" ]; then
    for d in "$HOME/src" "$HOME/dev" "$HOME/git" "$HOME/projects" "$HOME/work" /media; do
        [ ! -d "$d" ] || ROOTS="${ROOTS}${NL}$d"
    done
    if [ "$ALL" -eq 1 ]; then
        for d in /opt /srv /workspace /workspaces; do
            [ ! -d "$d" ] || ROOTS="${ROOTS}${NL}$d"
        done
    fi
fi
[ -n "$ROOTS" ] || { echo "$PROGRAM: pass at least one search root" >&2; exit 2; }
SEARCHER=grep
if [ "${USE_GREP:-0}" != 1 ] && command -v rg >/dev/null 2>&1; then SEARCHER=rg; fi
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
      *.md|*.rst|*.txt|*.adoc|*.json|*.yaml|*.yml|*.toml|*.xml|*.svg|*.lock|*.map|*.min.js|*.min.css|*.pb.go|*.generated.go|*.designer.cs|*.g.cs|*.gen.cs|*.freezed.dart|*.g.dart|*.moc.cpp|moc_*.cpp|qrc_*.cpp|ui_*.h|*_pb2.py|*_generated.*|*.generated.*|*.gen.*|*.autogen.*|*.freezed.*|*.gr.dart|test*.c|test*.h|test*.cc|test*.cpp|test*.hpp|test*.rs|test*.zig|test*.go|*_test.*|*_spec.*|*.spec.*|*.tests.*|*_mock.*|*_stub.*|mock_*.c|mock_*.cpp|stub_*.c|stub_*.cpp) return 0 ;;
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
        c=$(rg -n '(^|[^[:alnum:]_])(vk[A-Z][A-Za-z0-9_]*|VK_[A-Z0-9_]+)([^[:alnum:]_]|$)' "$full" 2>/dev/null || :)
        d=$(rg -n -i 'semaphore|queue.?submit|queue.?present|device.?lost|device.?loss|wait_semaphores|signal_semaphore|cmd_dispatch|dispatch_workgroups|create_device|create_instance' "$full" 2>/dev/null || :)
      else
        a=$(grep -n -i -E 'XAverius|Xaverius|xav_[[:alnum:]_]*|XAV_[[:alnum:]_]*' "$full" 2>/dev/null || :)
        b=$(grep -n -E 'AddExtension|CreateExtension|ProcVector|SProcVector|Dispatch.*Request|dixLookupResource|Xvfb' "$full" 2>/dev/null || :)
        c=$(grep -n -E '(^|[^[:alnum:]_])(vk[A-Z][A-Za-z0-9_]*|VK_[A-Z0-9_]+)([^[:alnum:]_]|$)' "$full" 2>/dev/null || :)
        d=$(grep -n -i -E 'semaphore|queue.?submit|queue.?present|device.?lost|device.?loss|wait_semaphores|signal_semaphore|cmd_dispatch|dispatch_workgroups|create_device|create_instance' "$full" 2>/dev/null || :)
      fi
      # Mask comments and quoted literals before syntax classification. This
      # preserves line numbers; it is a lightweight lexer, not a full parser.
      code=$(awk '
        BEGIN { block=0; quote=""; esc=0; sq=sprintf("%c",39) }
        {
          line=$0; out=""
          for (i=1; i<=length(line); i++) {
            ch=substr(line,i,1); nx=substr(line,i+1,1)
            if (block) { if (ch=="*" && nx=="/") { block=0; i++ }; out=out " "; continue }
            if (quote!="") {
              if (esc) esc=0
              else if (ch=="\\") esc=1
              else if (ch==quote) quote=""
              out=out " "; continue
            }
            if (ch=="/" && nx=="*") { block=1; i++; out=out " "; continue }
            if (ch=="/" && nx=="/") { while (i<=length(line)) { out=out " "; i++ }; break }
            if (ch==sprintf("%c",34) || ch==sq) { quote=ch; out=out " "; continue }
            out=out ch
          }
          print out
        }' "$full" | grep -n -E -v '^[[:space:]]*(#|--|;)' || :)
      if [ -n "$a" ]; then xav=$((xav+1)); printf '  XA: %s\n%s\n' "$f" "$a" >>"$matches"; fi
      if [ -n "$b" ]; then x11=$((x11+1)); printf '  X11: %s\n%s\n' "$f" "$b" >>"$matches"; fi
      if [ -n "$c" ]; then vk=$((vk+1)); printf '  VK: %s\n%s\n' "$f" "$c" >>"$matches"; fi
      if [ -n "$d" ]; then sync=$((sync+1)); printf '  SYNC: %s\n%s\n' "$f" "$d" >>"$matches"; fi
      if [ -n "$code" ]; then
        # Count direct Vulkan API invocations only; project wrapper methods
        # are reported separately and never boost the backend score.
        call=$(printf '%s\n' "$code" | grep -E '(^|[^[:alnum:]_])vk[A-Z][A-Za-z0-9_]*[[:space:]]*\(' 2>/dev/null || :)
        call=$(printf '%s\n' "$call" | grep -E -v '^[0-9]+:[[:space:]]*(pub[[:space:]]+)?(unsafe[[:space:]]+)?(extern[[:space:]]+)?(static[[:space:]]+)?(VkResult|void|int|uint32_t|Vk[A-Za-z0-9_]+)[[:space:]]+vk[A-Z][A-Za-z0-9_]*[[:space:]]*\(' 2>/dev/null || :)
        if [ -n "$call" ]; then calls=$((calls+1)); printf '  VK-CALL: %s\n%s\n' "$f" "$call" >>"$matches"; fi
        wrappers=$(printf '%s\n' "$code" | grep -E '(queue_submit(_2)?|queueSubmit(_2)?|queue_present|queuePresent|wait_semaphores|waitSemaphores|signal_semaphore|signalSemaphore|cmd_dispatch|dispatch_workgroups|create_device|createDevice|create_instance|createInstance)[[:space:]]*\(' 2>/dev/null || :)
        wrappers=$(printf '%s\n' "$wrappers" | grep -E '(=|return[[:space:]]|try!?[[:space:]]*\(|\.)' 2>/dev/null || :)
        if [ -n "$wrappers" ]; then printf '  WRAPPER-CALL: %s\n%s\n' "$f" "$wrappers" >>"$matches"; fi
        # Distinguish concrete handlers from generic dispatch entry points.
        # Xorg extensions commonly use proc_*_vector tables; table members
        # count only when the same source file also defines the function body.
        req=$(printf '%s\n' "$code" | awk '
          {
            line[NR]=$0
            low=tolower($0)
            if (!table && low ~ /vector/ && $0 ~ /=/) {
              table=1
              if ($0 ~ /\{/) depth=1
            } else if (table && depth==0 && $0 ~ /\{/) depth=1
            if (table && depth>0) {
              rest=$0
              while (match(rest, /(Proc|SProc|proc_|sproc_)[A-Za-z0-9_]+/)) {
                name=substr(rest,RSTART,RLENGTH); entries[name]=1
                rest=substr(rest,RSTART+RLENGTH)
              }
              if ($0 ~ /\}/) { table=0; depth=0 }
            }
          }
          END {
            for (i=1; i<=NR; i++) {
              text=line[i]
              for (name in entries) {
                if (text ~ ("(^|[^[:alnum:]_])" name "[[:space:]]*\\(")) {
                  # Look forward from the function signature: a body must
                  # open before a semicolon, so prototypes/calls are rejected.
                  active=1
                  for (j=i; j<=NR && j<i+8; j++) {
                    if (line[j] ~ /\{/) { defined[name]=1; defline[name]=i; break }
                    if (line[j] ~ /;/) break
                  }
                }
              }
            }
            for (name in defined) {
              low=tolower(name)
              if (low ~ /dispatch|vector|wrapper|forward/) continue
              print defline[name] ":" name
            }
          }' 2>/dev/null || :)
        # Switch-based Xorg extensions call concrete handlers from case arms.
        # Require both switch/case syntax and a local function definition.
        switchreq=$(printf '%s\n' "$code" | awk '
          /switch[[:space:]]*\(/ { has_switch=1 }
          /case[[:space:]].*:/ { has_case=1 }
          /return[[:space:]]+Proc[A-Za-z0-9_]+[[:space:]]*\(/ {
            line=$0
            while (match(line, /Proc[A-Za-z0-9_]+[[:space:]]*\(/)) {
              name=substr(line,RSTART,RLENGTH); sub(/[[:space:]]*\($/, "", name)
              if (name !~ /Dispatch$/) targets[name]=1
              line=substr(line,RSTART+RLENGTH)
            }
          }
          { lines[NR]=$0 }
          END {
            if (!has_switch || !has_case) exit
            for (name in targets) {
              for (i=1; i<=NR; i++) {
                if (lines[i] ~ ("(^|[^[:alnum:]_])" name "[[:space:]]*\\(")) {
                  for (j=i; j<=NR && j<i+8; j++) {
                    if (lines[j] ~ /\{/) { print i ":" name; break }
                    if (lines[j] ~ /;/) break
                  }
                  break
                }
              }
            }
          }
        ' 2>/dev/null || :)
        # Classic core handlers use ProcFooReq/SProcFooReq names even when
        # no local vector initializer is visible in this translation unit.
        classic=$(printf '%s\n' "$code" | awk '
          /(^|[^[:alnum:]_])(Proc|SProc)[A-Za-z0-9_]*(Req|Request)[[:space:]]*\(/ {
            sig=$0; active=1
            if ($0 ~ /\{/) { print sig; active=0 }
            else {
              for (j=NR+1; j<=NR+8; j++) {
                if (getline nextline <= 0) break
                if (nextline ~ /\{/) { print sig; break }
                if (nextline ~ /;/) break
              }
            }
          }' 2>/dev/null || :)
        if [ -n "$req" ] || [ -n "$classic" ] || [ -n "$switchreq" ]; then
          dispatch=$((dispatch+1))
          [ -z "$req" ] || printf '  X11-HANDLER: %s\n%s\n' "$f" "$req" >>"$matches"
          [ -z "$classic" ] || printf '  X11-HANDLER: %s\n%s\n' "$f" "$classic" >>"$matches"
          [ -z "$switchreq" ] || printf '  X11-HANDLER: %s\n%s\n' "$f" "$switchreq" >>"$matches"
        fi
        generic=$(printf '%s\n' "$code" | grep -E '(^|[^[:alnum:]_])[A-Za-z_][A-Za-z0-9_]*(dispatch|Dispatch)[A-Za-z0-9_]*[[:space:]]*\\(' 2>/dev/null || :)
        if [ -n "$generic" ]; then printf '  X11-GENERIC-DISPATCH: %s\n%s\n' "$f" "$generic" >>"$matches"; fi
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
    printf 'Signals: XAverius-files=%s X11-files=%s X11-handler-files=%s Vulkan-symbol-files=%s Vulkan-call-files=%s sync-files=%s SCORE=%s\n' "$xav" "$x11" "$dispatch" "$vk" "$calls" "$sync" "$score"
    [ "$score" -eq 0 ] || cat "$matches"
}
while IFS= read -r p; do [ -z "$p" ] || scan_project "$p"; done <"$projects"
exit 0
