#!/usr/bin/env python3
"""Regression tests for cross-translation-unit handler type conflicts."""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check-handler-signatures.py"


def run(files):
    return subprocess.run(
        [sys.executable, str(CHECKER), *(str(path) for path in files)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def main():
    with tempfile.TemporaryDirectory(prefix="xav-handler-types-") as directory:
        root = Path(directory)
        compatible_a = root / "compatible_a.c"
        compatible_b = root / "compatible_b.c"
        compatible_a.write_text(
            "int ProcSharedReq(ClientPtr client) { return Success; }\n"
            "static int (*ProcVectorA[])(ClientPtr) = { ProcSharedReq };\n",
            encoding="utf-8",
        )
        compatible_b.write_text(
            "int ProcSharedReq(ClientPtr other) { return Success; }\n"
            "static int (*ProcVectorB[])(ClientPtr) = { ProcSharedReq };\n",
            encoding="utf-8",
        )
        result = run([compatible_a, compatible_b])
        if result.returncode != 0:
            raise SystemExit("compatible declarations incorrectly rejected:\n" + result.stdout + result.stderr)

        conflict_a = root / "conflict_a.c"
        conflict_b = root / "conflict_b.c"
        conflict_a.write_text(
            "int ProcSharedReq(ClientPtr client) { return Success; }\n"
            "static int (*ProcVectorA[])(ClientPtr) = { ProcSharedReq };\n",
            encoding="utf-8",
        )
        conflict_b.write_text(
            "int ProcSharedReq(int client) { return Success; }\n"
            "static int (*ProcVectorB[])(int) = { ProcSharedReq };\n",
            encoding="utf-8",
        )
        result = run([conflict_a, conflict_b])
        if result.returncode != 1 or "CONFLICT: ProcSharedReq" not in result.stdout:
            raise SystemExit("incompatible cross-TU handler signature was not detected:\n" + result.stdout + result.stderr)
        if "ClientPtr" not in result.stdout or "int" not in result.stdout:
            raise SystemExit("conflict report omitted the incompatible types:\n" + result.stdout)

        table_a = root / "table_a.c"
        table_b = root / "table_b.c"
        table_a.write_text(
            "int ProcTableReq(ClientPtr client) { return Success; }\n"
            "static int (*RequestVectorA[])(ClientPtr) = { ProcTableReq };\n",
            encoding="utf-8",
        )
        table_b.write_text(
            "int ProcTableReq(ClientPtr client) { return Success; }\n"
            "static long (*RequestVectorB[])(ClientPtr) = { ProcTableReq };\n",
            encoding="utf-8",
        )
        result = run([table_a, table_b])
        if result.returncode != 1 or "CONFLICT: ProcTableReq" not in result.stdout:
            raise SystemExit("incompatible dispatch function-pointer type was not detected:\n" + result.stdout + result.stderr)

        nested_a = root / "nested_a.c"
        nested_b = root / "nested_b.c"
        nested_a.write_text(
            "int ProcNestedReq(void (*callback)(int, int)) { return Success; }\n",
            encoding="utf-8",
        )
        nested_b.write_text(
            "int ProcNestedReq(void (*other_callback)(int, int)) { return Success; }\n",
            encoding="utf-8",
        )
        result = run([nested_a, nested_b])
        if result.returncode != 0:
            raise SystemExit("equivalent nested callback types incorrectly rejected:\n" + result.stdout + result.stderr)

        nested_b.write_text(
            "int ProcNestedReq(void (*other_callback)(int, long)) { return Success; }\n",
            encoding="utf-8",
        )
        result = run([nested_a, nested_b])
        if result.returncode != 1 or "CONFLICT: ProcNestedReq" not in result.stdout:
            raise SystemExit("nested callback parameter conflict was not detected:\n" + result.stdout + result.stderr)

        return_a = root / "return_a.c"
        return_b = root / "return_b.c"
        return_a.write_text(
            "const char *ProcConstReq(ClientPtr client) { return 0; }\n",
            encoding="utf-8",
        )
        return_b.write_text(
            "char *ProcConstReq(ClientPtr client) { return 0; }\n",
            encoding="utf-8",
        )
        result = run([return_a, return_b])
        if result.returncode != 1 or "CONFLICT: ProcConstReq" not in result.stdout:
            raise SystemExit("const-qualified return type conflict was not detected:\n" + result.stdout + result.stderr)

        typedef_ok = root / "typedef_ok.c"
        typedef_ok.write_text(
            "typedef int (*HandlerProc)(ClientPtr);\n"
            "int ProcTypedefReq(ClientPtr client) { return Success; }\n"
            "static HandlerProc RequestVector[] = { ProcTypedefReq };\n",
            encoding="utf-8",
        )
        result = run([typedef_ok])
        if result.returncode != 0:
            raise SystemExit("compatible typedef-based dispatch type incorrectly rejected:\n" + result.stdout + result.stderr)

        typedef_bad = root / "typedef_bad.c"
        typedef_bad.write_text(
            "typedef long (*HandlerProc)(ClientPtr);\n"
            "int ProcTypedefReq(ClientPtr client) { return Success; }\n"
            "static HandlerProc RequestVector[] = { ProcTypedefReq };\n",
            encoding="utf-8",
        )
        result = run([typedef_bad])
        if result.returncode != 1 or "CONFLICT: ProcTypedefReq" not in result.stdout:
            raise SystemExit("typedef-based dispatch return-type conflict was not detected:\n" + result.stdout + result.stderr)

    print("handler signature regression tests: PASS")


if __name__ == "__main__":
    main()
