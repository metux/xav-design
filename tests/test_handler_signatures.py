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

    print("handler signature regression tests: PASS")


if __name__ == "__main__":
    main()
