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
mkdir -p "$cmake/src" "$cmake/tests" "$cmake/generated" "$meson/src" "$meson/target"
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
printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/present_request.c' >/dev/null || { echo "FAIL: Xorg dispatch-table handler not recognized" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'X11-HANDLER: src/xtest_request.c' >/dev/null || { echo "FAIL: switch-dispatched Xorg handlers not recognized" >&2; exit 1; }
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
fallback=$(USE_GREP=1 MAX_DEPTH=8 sh "$SCRIPT" "$cmake" "$meson" 2>&1)
printf '%s\n' "$fallback" | grep -F "PROJECT: $cmake" >/dev/null || { echo "FAIL: first explicit root with spaces not discovered" >&2; exit 1; }
printf '%s\n' "$fallback" | grep -F "PROJECT: $meson" >/dev/null || { echo "FAIL: second explicit root not discovered by grep fallback" >&2; exit 1; }
printf '%s\n' "$fallback" | grep -F 'VK-CALL: src/backend.rs' >/dev/null || { echo "FAIL: grep fallback missed Vulkan symbol boundaries" >&2; exit 1; }

if MAX_DEPTH=invalid sh "$SCRIPT" "$fixture" >/dev/null 2>&1; then
    echo "FAIL: invalid MAX_DEPTH was accepted" >&2
    exit 1
fi
echo "find-xav-backend regression tests: PASS"
