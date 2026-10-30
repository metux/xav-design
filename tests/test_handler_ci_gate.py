#!/usr/bin/env python3
"""Regression tests for the required native-source handler audit CI gate."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tools" / "check-handler-ci-gate.py"


def git(root, *args):
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise SystemExit("git setup failed: " + result.stderr.decode("utf-8", errors="replace"))


def run_gate(root):
    return subprocess.run(
        [sys.executable, str(GATE), str(root)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def setup_repo(root):
    git(root, "init", "-q")
    git(root, "config", "user.email", "ci-gate-test@example.invalid")
    git(root, "config", "user.name", "CI gate regression test")


def main():
    with tempfile.TemporaryDirectory(prefix="xav-handler-ci-gate-") as temp:
        root = Path(temp) / "no-sources"
        root.mkdir()
        setup_repo(root)
        result = run_gate(root)
        if result.returncode != 0 or "SKIP" not in result.stdout:
            raise SystemExit("source-free checkout should skip cleanly:\n" + result.stdout + result.stderr)

        source_root = Path(temp) / "source-without-db"
        source_root.mkdir()
        setup_repo(source_root)
        source = source_root / "src" / "xav_handler.c"
        source.parent.mkdir()
        source.write_text(
            "int ProcGateReq(ClientPtr client) { return 0; }\n"
            "static int (*RequestVector[])(ClientPtr) = { ProcGateReq };\n",
            encoding="utf-8",
        )
        git(source_root, "add", "src/xav_handler.c")
        result = run_gate(source_root)
        if result.returncode != 1 or "no compile_commands.json" not in result.stderr:
            raise SystemExit("tracked native sources without a compile database must fail:\n" + result.stdout + result.stderr)

        db_root = Path(temp) / "source-with-db"
        db_root.mkdir()
        setup_repo(db_root)
        source = db_root / "src" / "xav_handler.c"
        source.parent.mkdir()
        source.write_text(
            "int ProcGateReq(ClientPtr client) { return 0; }\n"
            "static int (*RequestVector[])(ClientPtr) = { ProcGateReq };\n",
            encoding="utf-8",
        )
        git(db_root, "add", "src/xav_handler.c")
        (db_root / "compile_commands.json").write_text(json.dumps([
            {
                "directory": str(db_root),
                "file": str(source),
                "arguments": ["cc", "-c", str(source), "-o", "xav_handler.o"],
            }
        ]), encoding="utf-8")
        result = run_gate(db_root)
        if result.returncode != 0 or "PASS" not in result.stdout:
            raise SystemExit("source with a valid compile database should pass:\n" + result.stdout + result.stderr)

        # A database somewhere in the tree is not enough: the audit must be
        # able to preprocess each tracked source using an actual compile entry.
        uncovered_root = Path(temp) / "source-with-uncovered-db"
        uncovered_root.mkdir()
        setup_repo(uncovered_root)
        source = uncovered_root / "src" / "xav_handler.c"
        source.parent.mkdir()
        source.write_text("int ProcUncoveredReq(ClientPtr client) { return 0; }\n", encoding="utf-8")
        git(uncovered_root, "add", "src/xav_handler.c")
        (uncovered_root / "compile_commands.json").write_text("[]\n", encoding="utf-8")
        result = run_gate(uncovered_root)
        if result.returncode == 0:
            raise SystemExit("compile database without an entry for the tracked source must fail:\n" + result.stdout + result.stderr)

        async_root = Path(temp) / "source-with-unannotated-async-callback"
        async_root.mkdir()
        setup_repo(async_root)
        source = async_root / "src" / "xav_handler.c"
        source.parent.mkdir()
        source.write_text(
            "int ProcAsyncReq(ClientPtr client) { return 0; }\\n"
            "static int (*RequestVector[])(ClientPtr) = { ProcAsyncReq };\\n"
            "void on_done(void *ctx) { finish_submit(ctx); }\\n"
            "void submit(void) { vkQueueSubmit(queue, 1, submits, fence); register_callback(on_done); }\\n",
            encoding="utf-8",
        )
        git(async_root, "add", "src/xav_handler.c")
        (async_root / "compile_commands.json").write_text(json.dumps([{
            "directory": str(async_root), "file": str(source),
            "arguments": ["cc", "-c", str(source), "-o", "xav_handler.o"],
        }]), encoding="utf-8")
        result = run_gate(async_root)
        if result.returncode != 1 or "no XAV_ASYNC_CALLBACK_REGISTER/VALIDATE" not in result.stdout:
            raise SystemExit("native async callback without generation annotations must fail the integrated gate:\\n" + result.stdout + result.stderr)

        async_root_ok = Path(temp) / "source-with-annotated-async-callback"
        async_root_ok.mkdir()
        setup_repo(async_root_ok)
        source = async_root_ok / "src" / "xav_handler.c"
        source.parent.mkdir()
        source.write_text(
            "int ProcAsyncReq(ClientPtr client) { return 0; }\\n"
            "static int (*RequestVector[])(ClientPtr) = { ProcAsyncReq };\\n"
            "/* XAV_ASYNC_CALLBACK_REGISTER: on_done; device_generation */\\n"
            "/* XAV_ASYNC_CALLBACK_VALIDATE: on_done; device_generation */\\n"
            "void on_done(void *ctx) { if (device_generation != current_device_generation) return; }\\n"
            "void submit(void) { vkQueueSubmit(queue, 1, submits, fence); register_callback(on_done); }\\n",
            encoding="utf-8",
        )
        git(async_root_ok, "add", "src/xav_handler.c")
        (async_root_ok / "compile_commands.json").write_text(json.dumps([{
            "directory": str(async_root_ok), "file": str(source),
            "arguments": ["cc", "-c", str(source), "-o", "xav_handler.o"],
        }]), encoding="utf-8")
        result = run_gate(async_root_ok)
        if result.returncode != 0 or "callback generation audit passed" not in result.stdout:
            raise SystemExit("annotated async callback with generation validation should pass the integrated gate:\\n" + result.stdout + result.stderr)

    print("handler CI gate regression tests: PASS")


if __name__ == "__main__":
    main()
