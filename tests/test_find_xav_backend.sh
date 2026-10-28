#!/bin/sh
# Regression tests for tools/find-xav-backend.sh.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
SCRIPT="$ROOT/tools/find-xav-backend.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-find-xav-backend.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
fixture="$tmp/fixtures with spaces"
cmake="$fixture/cmake-project"
meson="$fixture/meson-project"
mkdir -p "$cmake/src" "$cmake/tests" "$cmake/generated" "$cmake/config/include" "$cmake/build" "$meson/src" "$meson/target"
cat >"$cmake/CMakeLists.txt" <<'EOF'
cmake_minimum_required(VERSION 3.16)
project(fake_xav_backend C)
EOF
cat >"$cmake/src/backend.rs" <<'EOF'
fn submit(device: Device, submit: SubmitInfo, fence: Fence) {
    unsafe { vkQueueSubmit(device, 1, &submit, fence) };
}
EOF
cat >"$cmake/src/request.c" <<'EOF'
int ProcXavQueueSubmitReq(ClientPtr client) {
    REQUEST_SIZE_MATCH(xXavQueueSubmitReq);
    return Success;
}
EOF
cat >"$cmake/src/latest.c" <<'EOF'
int submit_latest(void) {
    vkQueueSubmit(device, 1, &submit, fence);
    return 0;
}
EOF
cat >"$cmake/config/include/xav_build_config.h" <<'EOF'
#if defined(XAV_ENABLE_CONFIGURED)
#define XAV_CONFIGURED_HANDLER 1
#endif
EOF
cat >"$cmake/config/include/configured_handlers.h" <<'EOF'
#include <xav_build_config.h>
#ifdef XAV_CONFIGURED_HANDLER
static int (*ConfiguredProcVector[])(ClientPtr) = {
    ProcConfiguredHeaderReq,
};
static int ProcConfiguredHeaderReq(ClientPtr client)
{
    return Success;
}
#endif
EOF
cat >"$cmake/src/configured_dispatch.c" <<'EOF'
#include <configured_handlers.h>
int configured_translation_unit(void)
{
    return Success;
}
EOF
# Model the compile database emitted by CMake or Meson: its -D and -I
# options are essential to expose the real conditional dispatch table.
python3 - "$cmake" <<'PY'
import json
import os
import sys
root = os.path.realpath(sys.argv[1])
entry = {
    "directory": root,
    "file": os.path.join(root, "src", "configured_dispatch.c"),
    "arguments": [
        "cc", "-DXAV_ENABLE_CONFIGURED=1", "-I",
        os.path.join(root, "config", "include"), "-c",
        os.path.join(root, "src", "configured_dispatch.c"), "-o",
        os.path.join(root, "build", "configured_dispatch.o")
    ]
}
with open(os.path.join(root, "build", "compile_commands.json"), "w", encoding="utf-8") as f:
    json.dump([entry], f)
PY
cat >"$cmake/src/inline_comment.rs" <<'EOF'
let marker = 0; // vkQueueSubmit(device, 1, &submit, fence);
EOF
cat >"$cmake/src/string_literal.c" <<'EOF'
const char *example = "vkQueueSubmit(device, 1, &submit, fence);";
EOF
cat >"$cmake/src/block_comment.c" <<'EOF'
/*
vkQueueSubmit(device, 1, &submit, fence);
*/
int unrelated(void) { return 0; }
EOF
cat >"$cmake/src/declarations.h" <<'EOF'
VkResult vkQueueSubmit(VkQueue queue, uint32_t count, const VkSubmitInfo *info, VkFence fence);
VkResult vkQueueWaitIdle(VkQueue queue)
{
    return VK_SUCCESS;
}
EOF
cat >"$cmake/src/comments.rs" <<'EOF'
// vkQueueSubmit(device, 1, &submit, fence);
EOF
cat >"$cmake/src/bare_call.c" <<'EOF'
void submit(void) {
    vkQueueSubmit(device, 1, &submit, fence);
}
EOF
cat >"$cmake/src/request_prototype.c" <<'EOF'
int ProcXavFakeReq(ClientPtr client);
EOF
cat >"$cmake/src/macro_request.c" <<'EOF'
#include "dixstruct.h"
DISPATCH_PROC(ProcMacroGeneratedReq)
{
    REQUEST(xReq);
    return Success;
}
EOF
cat >"$cmake/src/request-macros.h" <<'EOF'
#define DISPATCH_PROC(func) int func(ClientPtr client)
EOF
cat >"$cmake/src/macro_header_request.c" <<'EOF'
#include "request-macros.h"
DISPATCH_PROC(ProcHeaderMacroReq)
{
    return Success;
}
EOF
cat >"$cmake/src/header_owned_handlers.h" <<'EOF'
static int (*HeaderProcVector[1])(ClientPtr) = {
    ProcHeaderOwnedReq,
};
static int ProcHeaderOwnedReq(ClientPtr client)
{
    return Success;
}
EOF
cat >"$cmake/src/header_includes_only.c" <<'EOF'
#include "header_owned_handlers.h"
int unrelated_translation_unit(void)
{
    return Success;
}
EOF
cat >"$cmake/src/tables.c" <<'EOF'
/* Mirrors the checked-in Xorg dix/tables.c request vector pattern. */
int (*ProcVector[2]) (ClientPtr) = {
    ProcRealOneReq,
    ProcRealTwoReq,
};
int ProcRealOneReq(ClientPtr client)
{
    return Success;
}
int ProcRealTwoReq(ClientPtr client)
{
    return Success;
}
EOF
cat >"$cmake/src/macro_table.h" <<'EOF'
#define XORG_HANDLER(name) name
#define XORG_HANDLER_GROUP(a, b) { a, b }
#define XORG_PASTE(prefix, suffix) prefix##suffix
EOF
cat >"$cmake/src/multiline_macro_table.c" <<'EOF'
#include "macro_table.h"
static const struct {
    int (*handler)(ClientPtr);
    int opcode;
} ProcVector[] =
{
    XORG_HANDLER(ProcMacroTableReq),
    XORG_PASTE(Proc, PastedMacroReq),
#if 0
    XORG_PASTE(Proc, DisabledMacroReq),
#endif
    XORG_HANDLER_GROUP(
        ProcNestedFirstReq,
        ProcNestedSecondReq
    ),
    ProcGenericDispatch,
};
int ProcPastedMacroReq(ClientPtr client)
{
    return Success;
}
int ProcMacroTableReq(ClientPtr client)
{
    return Success;
}
int ProcNestedFirstReq(ClientPtr client)
{
    return Success;
}
int ProcNestedSecondReq(ClientPtr client)
{
    return Success;
}
int ProcGenericDispatch(ClientPtr client)
{
    return Success;
}
EOF
cat >"$cmake/src/protocol_generated.c" <<'EOF'
int ProcNotRealSourceReq(ClientPtr client)
{
    return Success;
}
EOF
cat >"$cmake/src/xtest_request.c" <<'EOF'
static int ProcXTestGetVersion(ClientPtr client)
{
    return Success;
}
static int ProcXTestFakeInput(ClientPtr client)
{
    return Success;
}
static int ProcXTestDispatch(ClientPtr client)
{
    REQUEST(xReq);
    switch (stuff->data) {
    case X_XTestGetVersion:
        return ProcXTestGetVersion(client);
    case X_XTestFakeInput:
        return ProcXTestFakeInput(client);
    default:
        return BadRequest;
    }
}
EOF
cat >"$cmake/src/indirect_dispatch.c" <<'EOF'
static int ProcIndirectQuery(ClientPtr client)
{
    return Success;
}
static int ProcIndirectInput(ClientPtr client)
{
    return Success;
}
static int ProcIndirectWrapper(ClientPtr client)
{
    return ProcIndirectInput(client);
}
static int (*requestVector[2])(ClientPtr);
void RegisterIndirect(void)
{
    requestVector[0] = ProcIndirectQuery;
    requestVector[1] = ProcIndirectInput;
}
EOF
cat >"$cmake/src/present_request.c" <<'EOF'
static int
proc_present_pixmap(ClientPtr client)
{
    return Success;
}
static int
proc_present_dispatch(ClientPtr client)
{
    return (*proc_present_vector[0])(client);
}
static int
proc_present_query_version(ClientPtr client)
{
    return Success;
}
static int (*proc_present_vector[2]) (ClientPtr) = {
    proc_present_query_version,
    proc_present_pixmap,
};
EOF
cat >"$cmake/tests/backend_test.rs" <<'EOF'
unsafe { vkQueueSubmit(device, 1, &submit, fence) };
EOF
cat >"$cmake/generated/generated.zig" <<'EOF'
vkQueueSubmit(device, 1, &submit, fence);
EOF
cat >"$meson/meson.build" <<'EOF'
project('fake-zig-backend', 'c')
EOF
cat >"$meson/src/backend.zig" <<'EOF'
pub fn submit(device: Device, info: SubmitInfo) !void {
    try device.queue_submit(info);
}
EOF
cat >"$meson/target/build_output.zig" <<'EOF'
vkQueueSubmit(device, 1, &submit, fence);
EOF
output=$(MAX_DEPTH=8 sh "$SCRIPT" "$fixture" 2>&1)
printf '%s\n' "$output" | grep -F "PROJECT: $cmake" >/dev/null || { echo "FAIL: CMake project not discovered" >&2; exit 1; }
printf '%s\n' "$output" | grep -F "PROJECT: $meson" >/dev/null || { echo "FAIL: Meson project not discovered" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'VK-CALL: src/backend.rs' >/dev/null || { echo "FAIL: Rust Vulkan call not recognized" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/request.c' >/dev/null || { echo "FAIL: X11 request handler not recognized" >&2; exit 1; }
printf '%s\\n' "$output" | grep -F 'X11-HANDLER: config/include/configured_handlers.h' >/dev/null || { echo "FAIL: header without a compile database entry was not evaluated with its including translation unit's -D/-I flags" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/present_request.c' >/dev/null || { echo "FAIL: Xorg dispatch-table handler not recognized" >&2; exit 1; }
if printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/header_includes_only.c' >/dev/null; then
    echo "FAIL: handler defined only in an included header was attributed to the including source" >&2
    exit 1
fi
printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/xtest_request.c' >/dev/null || { echo "FAIL: switch-dispatched Xorg handlers not recognized" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/indirect_dispatch.c' >/dev/null || { echo "FAIL: function-pointer assignment targets not recognized" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'X11-HANDLER-MACRO: src/macro_request.c'
printf '%s\n' "$output" | grep -F 'X11-HANDLER-MACRO: src/macro_header_request.c' >/dev/null || { echo "FAIL: handler macro from a non-dixstruct header not recognized" >&2; exit 1; } >/dev/null || { echo "FAIL: macro-declared Xorg request handler not recognized" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/tables.c'
for handler in ProcPastedMacroReq ProcMacroTableReq ProcNestedFirstReq ProcNestedSecondReq; do
    printf '%s\n' "$output" | grep -F "X11-HANDLER: src/multiline_macro_table.c" -A8 | grep -F "$handler" >/dev/null || {
        echo "FAIL: multiline/macro dispatch handler $handler not recognized" >&2; exit 1;
    }
done
if printf '%s\n' "$output" | grep -F 'ProcDisabledMacroReq' >/dev/null; then
    echo "FAIL: disabled preprocessor branch was classified as a handler" >&2
    exit 1
fi
if printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/multiline_macro_table.c' -A8 | grep -F 'ProcGenericDispatch' >/dev/null; then
    echo "FAIL: generic dispatcher in macro table classified as concrete request handler" >&2; exit 1
fi >/dev/null || { echo "FAIL: checked-in Xorg ProcVector table not recognized" >&2; exit 1; }
if printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/protocol_generated.c' >/dev/null; then
    echo "FAIL: generated request artifact was treated as a real source handler" >&2; exit 1
fi
printf '%s\n' "$output" | grep -F 'X11-DISPATCH-ASSIGNMENT: src/indirect_dispatch.c' >/dev/null || { echo "FAIL: indirect dispatch assignments not reported" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'X11-WRAPPER-CALL: src/indirect_dispatch.c' >/dev/null || { echo "FAIL: wrapper forwarding calls not reported separately" >&2; exit 1; }
if printf '%s\n' "$output" | grep -E 'X11-HANDLER: src/present_request.c.*dispatch|X11-HANDLER: src/request_prototype' >/dev/null; then
    echo "FAIL: generic dispatcher or prototype was classified as a concrete handler" >&2
    exit 1
fi
printf '%s\n' "$output" | grep -F 'VK-CALL: src/bare_call.c' >/dev/null || { echo "FAIL: ordinary C Vulkan call not recognized" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'WRAPPER-CALL: src/backend.zig' >/dev/null || { echo "FAIL: Zig wrapper not classified separately" >&2; exit 1; }
if printf '%s\n' "$output" | grep -E 'tests/backend_test|generated/generated|target/build_output|X11-HANDLER: src/request_prototype|VK-CALL: src/(comments|inline_comment|string_literal|block_comment|declarations)|VK-CALL: src/backend.zig' >/dev/null; then
    echo "FAIL: excluded/comment/declaration source was reported as a Vulkan call" >&2
    exit 1
fi

# Exercise multiple independent roots and the portable grep fallback.
# Without a usable C compiler, source-text detection must remain usable.
fallback_cc=$(CC=missing-xav-cc MAX_DEPTH=8 sh "$SCRIPT" "$cmake" 2>&1)
printf '%s\n' "$fallback_cc" | grep -F "PROJECT: $cmake" >/dev/null || { echo "FAIL: compiler-free fallback failed" >&2; exit 1; }
printf '%s\n' "$fallback_cc" | grep -F 'ProcMacroTableReq' >/dev/null || { echo "FAIL: compiler-free fallback lost literal handlers" >&2; exit 1; }

fallback=$(USE_GREP=1 MAX_DEPTH=8 sh "$SCRIPT" "$cmake" "$meson" 2>&1)
printf '%s\n' "$fallback" | grep -F "PROJECT: $cmake" >/dev/null || { echo "FAIL: first explicit root with spaces not discovered" >&2; exit 1; }
printf '%s\n' "$fallback" | grep -F "PROJECT: $meson" >/dev/null || { echo "FAIL: second explicit root not discovered by grep fallback" >&2; exit 1; }
printf '%s\n' "$fallback" | grep -F 'VK-CALL: src/backend.rs' >/dev/null || { echo "FAIL: grep fallback missed Vulkan symbol boundaries" >&2; exit 1; }

# Relative search roots must still preprocess source files from the caller's cwd.
relative_output=$(cd "$tmp" && MAX_DEPTH=8 sh "$SCRIPT" "fixtures with spaces/cmake-project" 2>&1)
printf '%s\n' "$relative_output" | grep -F 'X11-HANDLER: src/multiline_macro_table.c' >/dev/null || {
    echo "FAIL: relative project root prevented C preprocessing" >&2; exit 1;
}
printf '%s\n' "$relative_output" | grep -F 'ProcPastedMacroReq' >/dev/null || {
    echo "FAIL: relative project root lost token-pasted handler detection" >&2; exit 1;
}

if MAX_DEPTH=invalid sh "$SCRIPT" "$fixture" >/dev/null 2>&1; then
    echo "FAIL: invalid MAX_DEPTH was accepted" >&2
    exit 1
fi
echo "find-xav-backend regression tests: PASS"
