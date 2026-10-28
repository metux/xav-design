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


def require_conflict(files, name, message):
    result = run(files)
    if result.returncode != 1 or f"CONFLICT: {name}" not in result.stdout:
        raise SystemExit(message + ":\n" + result.stdout + result.stderr)


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
        require_conflict([conflict_a, conflict_b], "ProcSharedReq",
                         "incompatible cross-TU handler signature was not detected")
        result = run([conflict_a, conflict_b])
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
        require_conflict([table_a, table_b], "ProcTableReq",
                         "incompatible dispatch function-pointer type was not detected")

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
        require_conflict([nested_a, nested_b], "ProcNestedReq",
                         "nested callback parameter conflict was not detected")

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
        require_conflict([return_a, return_b], "ProcConstReq",
                         "const-qualified return type conflict was not detected")

        typedef_header = root / "handler_types.h"
        typedef_header.write_text(
            "typedef int (*BaseHandler)(ClientPtr);\n"
            "typedef BaseHandler HandlerAlias;\n",
            encoding="utf-8",
        )
        typedef_tu = root / "typedef_tu.c"
        typedef_tu.write_text(
            '#include "handler_types.h"\n'
            "int ProcHeaderAliasReq(ClientPtr client) { return Success; }\n"
            "static HandlerAlias RequestVector[] = { ProcHeaderAliasReq };\n",
            encoding="utf-8",
        )
        result = run([typedef_tu, typedef_header])
        if result.returncode != 0:
            raise SystemExit("header typedef chain was not resolved across input files:\n" + result.stdout + result.stderr)

        mismatch_header = root / "mismatch_types.h"
        mismatch_header.write_text(
            "typedef long (*BaseHandler)(ClientPtr);\n"
            "typedef BaseHandler HandlerAlias;\n",
            encoding="utf-8",
        )
        mismatch_tu = root / "mismatch_tu.c"
        mismatch_tu.write_text(
            '#include "mismatch_types.h"\n'
            "int ProcHeaderAliasReq(ClientPtr client) { return Success; }\n"
            "static HandlerAlias RequestVector[] = { ProcHeaderAliasReq };\n",
            encoding="utf-8",
        )
        require_conflict([mismatch_tu, mismatch_header], "ProcHeaderAliasReq",
                         "incompatible typedef chain from a separate header was missed")

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
        require_conflict([typedef_bad], "ProcTypedefReq",
                         "typedef-based dispatch return-type conflict was not detected")

        nested_table = root / "nested_table.c"
        nested_table.write_text(
            "int ProcDeepReq(void (*callback)(int, int)) { return Success; }\n"
            "static int (*DeepVector[])(void (*callback)(int, long)) = { ProcDeepReq };\n",
            encoding="utf-8",
        )
        require_conflict([nested_table], "ProcDeepReq",
                         "nested function-pointer dispatch type conflict was not detected")

        nested_typedef = root / "nested_typedef.c"
        nested_typedef.write_text(
            "typedef int (*DeepHandler)(void (*callback)(int, long));\n"
            "int ProcDeepTypedefReq(void (*callback)(int, int)) { return Success; }\n"
            "static DeepHandler DeepVector[] = { ProcDeepTypedefReq };\n",
            encoding="utf-8",
        )
        require_conflict([nested_typedef], "ProcDeepTypedefReq",
                         "nested function-pointer typedef conflict was not detected")

        compatible_nested = root / "compatible_nested.c"
        compatible_nested.write_text(
            "typedef int (*DeepHandler)(void (*callback)(int, int));\n"
            "int ProcDeepCompatibleReq(void (*other)(int, int)) { return Success; }\n"
            "static DeepHandler DeepVector[] = { ProcDeepCompatibleReq };\n",
            encoding="utf-8",
        )
        result = run([compatible_nested])
        if result.returncode != 0:
            raise SystemExit("compatible nested function-pointer typedef rejected:\n" + result.stdout + result.stderr)

    print("handler signature regression tests: PASS")


if __name__ == "__main__":
    main()
