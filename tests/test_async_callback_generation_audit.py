#!/usr/bin/env python3
"""Regression tests for asynchronous callback generation auditing."""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check-async-callback-generations.py"


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise SystemExit(result.stderr.decode("utf-8", errors="replace"))


def run(root):
    return subprocess.run([sys.executable, str(CHECKER), str(root)],
                          text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)


def setup(root, body, filename="backend.c"):
    git(root, "init", "-q")
    git(root, "config", "user.email", "callback-audit@example.invalid")
    git(root, "config", "user.name", "Callback audit test")
    source = root / "src" / filename
    source.parent.mkdir(parents=True)
    source.write_text(body, encoding="utf-8")
    git(root, "add", str(source.relative_to(root)))
    return source


def main():
    with tempfile.TemporaryDirectory(prefix="xav-async-generation-") as temp:
        root = Path(temp) / "valid"
        root.mkdir()
        setup(root, """
/* XAV_ASYNC_CALLBACK_REGISTER: on_submit_done; device_generation; resource_generation; recording_epoch */
/* XAV_ASYNC_CALLBACK_VALIDATE: on_submit_done; device_generation; resource_generation; recording_epoch */
void on_submit_done(void *ctx) {
    if (device_generation != current_device_generation) return;
    if (resource_generation != current_resource_generation) return;
    if (recording_epoch != current_recording_epoch) return;
}
void submit(void) { vkQueueSubmit(queue, 1, submits, fence); register_callback(on_submit_done); }
""")
        result = run(root)
        if result.returncode != 0 or "PASS" not in result.stdout:
            raise SystemExit("fully captured and validated callback should pass:\n" + result.stdout + result.stderr)

        missing = Path(temp) / "missing-capture"
        missing.mkdir()
        setup(missing, """
/* XAV_ASYNC_CALLBACK_REGISTER: on_done; resource_generation */
/* XAV_ASYNC_CALLBACK_VALIDATE: on_done; resource_generation */
void on_done(void *ctx) {
    if (resource_generation != current_resource_generation) return;
}
void submit(void) { vkQueueSubmit(queue, 1, submits, fence); }
""")
        result = run(missing)
        if result.returncode != 1 or "does not capture device_generation" not in result.stdout:
            raise SystemExit("missing Device generation capture must fail:\n" + result.stdout + result.stderr)

        no_validation = Path(temp) / "missing-validation"
        no_validation.mkdir()
        setup(no_validation, """
/* XAV_ASYNC_CALLBACK_REGISTER: on_done; device_generation; resource_generation */
void on_done(void *ctx) {
    if (device_generation != current_device_generation) return;
    if (resource_generation != current_resource_generation) return;
}
void submit(void) { register_callback(on_done); }
""")
        result = run(no_validation)
        if result.returncode != 1 or "missing VALIDATE annotation" not in result.stdout:
            raise SystemExit("missing validation annotation must fail:\n" + result.stdout + result.stderr)

        mismatch = Path(temp) / "mismatched-validation"
        mismatch.mkdir()
        setup(mismatch, """
/* XAV_ASYNC_CALLBACK_REGISTER: on_done; device_generation; resource_generation */
/* XAV_ASYNC_CALLBACK_VALIDATE: on_done; device_generation */
void on_done(void *ctx) {
    if (device_generation != current_device_generation) return;
}
void submit(void) { register_callback(on_done); }
""")
        result = run(mismatch)
        if result.returncode != 1 or "captured generations not validated: resource_generation" not in result.stdout:
            raise SystemExit("unvalidated captured resource generation must fail:\n" + result.stdout + result.stderr)

        no_annotations = Path(temp) / "unannotated"
        no_annotations.mkdir()
        setup(no_annotations, """
void on_done(void *ctx) { finish_submit(ctx); }
void submit(void) { vkQueueSubmit(queue, 1, submits, fence); register_callback(on_done); }
""")
        result = run(no_annotations)
        if result.returncode != 1 or "no XAV_ASYNC_CALLBACK_REGISTER/VALIDATE" not in result.stdout:
            raise SystemExit("unannotated async callback path must fail:\n" + result.stdout + result.stderr)


        # Rust async tasks and named completion callbacks are part of the same
        # tracked-source audit, not silently skipped as non-C/C++ files.
        rust = Path(temp) / "rust-backend"
        rust.mkdir()
        setup(rust, """
// XAV_ASYNC_CALLBACK_REGISTER: on_done; device_generation; resource_generation
// XAV_ASYNC_CALLBACK_VALIDATE: on_done; device_generation; resource_generation
fn on_done(ctx: &Context) {
    if ctx.device_generation != current_device_generation() { return; }
    let resource = ctx.resource;
    if ctx.resource_generation != current_resource_generation(resource) { return; }
}
fn submit() { tokio::spawn(async move { register_callback(on_done); }); }
""", "backend.rs")
        result = run(rust)
        if result.returncode != 0 or "PASS" not in result.stdout:
            raise SystemExit("annotated Rust async callback should pass:\\n" + result.stdout + result.stderr)

        rust_missing = Path(temp) / "rust-missing"
        rust_missing.mkdir()
        setup(rust_missing, """
fn on_done(ctx: &Context) { finish(ctx); }
fn submit() { tokio::spawn(async move { register_callback(on_done); }); }
""", "backend.rs")
        result = run(rust_missing)
        if result.returncode != 1 or "no XAV_ASYNC_CALLBACK_REGISTER/VALIDATE" not in result.stdout:
            raise SystemExit("unannotated Rust async callback must fail:\\n" + result.stdout + result.stderr)

        zig = Path(temp) / "zig-backend"
        zig.mkdir()
        setup(zig, """
// XAV_ASYNC_CALLBACK_REGISTER: on_done; device_generation; resource_generation
// XAV_ASYNC_CALLBACK_VALIDATE: on_done; device_generation; resource_generation
fn on_done(ctx: *Context) void {
    if (ctx.device_generation != current_device_generation()) return;
    const resource = ctx.resource;
    if (ctx.resource_generation != current_resource_generation(resource)) return;
}
fn submit() void { _ = std.Thread.spawn(.{}, on_done, .{ctx}); }
""", "backend.zig")
        result = run(zig)
        if result.returncode != 0 or "PASS" not in result.stdout:
            raise SystemExit("annotated Zig async callback should pass:\\n" + result.stdout + result.stderr)

        zig_missing = Path(temp) / "zig-missing"
        zig_missing.mkdir()
        setup(zig_missing, """
fn on_done(ctx: *Context) void { finish(ctx); }
fn submit() void { _ = std.Thread.spawn(.{}, on_done, .{ctx}); }
""", "backend.zig")
        result = run(zig_missing)
        if result.returncode != 1 or "no XAV_ASYNC_CALLBACK_REGISTER/VALIDATE" not in result.stdout:
            raise SystemExit("unannotated Zig async callback must fail:\\n" + result.stdout + result.stderr)

        source_free = Path(temp) / "no-native"
        source_free.mkdir()
        git(source_free, "init", "-q")
        result = run(source_free)
        if result.returncode != 0 or "PASS" not in result.stdout:
            raise SystemExit("source-free checkout should pass cleanly:\n" + result.stdout + result.stderr)

    print("async callback generation audit regression tests: PASS")


if __name__ == "__main__":
    main()
