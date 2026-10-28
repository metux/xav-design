#!/bin/sh
# Regression tests for tools/find-xav-backend.sh.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
SCRIPT="$ROOT/tools/find-xav-backend.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-find-xav-backend.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
fixture="$tmp/fixtures"
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
cat >"$cmake/src/declarations.h" <<'EOF'
VkResult vkQueueSubmit(VkQueue queue, uint32_t count, const VkSubmitInfo *info, VkFence fence);
EOF
cat >"$cmake/src/comments.rs" <<'EOF'
// vkQueueSubmit(device, 1, &submit, fence);
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
printf '%s\n' "$output" | grep -F 'X11-DISPATCH: src/request.c' >/dev/null || { echo "FAIL: X11 request handler not recognized" >&2; exit 1; }
printf '%s\n' "$output" | grep -F 'VK-CALL: src/backend.zig' >/dev/null || { echo "FAIL: Zig wrapper call not recognized" >&2; exit 1; }
if printf '%s\n' "$output" | grep -E 'tests/backend_test|generated/generated|target/build_output|VK-CALL: src/comments|VK-CALL: src/declarations' >/dev/null; then
    echo "FAIL: excluded/comment/declaration source was reported as a Vulkan call" >&2
    exit 1
fi
echo "find-xav-backend regression tests: PASS"
