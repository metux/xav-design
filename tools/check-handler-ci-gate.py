#!/usr/bin/env python3
"""Require the handler signature audit when tracked C/C++ sources exist."""
import os
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "third_party", "third-party",
    "generated", "target", ".cache", ".venv", "venv",
}
SOURCE_GLOBS = ("*.c", "*.cc", "*.cpp", "*.cxx")


def tracked_sources(root):
    command = ["git", "-C", str(root), "ls-files", "-z", "--"]
    command.extend(SOURCE_GLOBS)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError("cannot list tracked C/C++ sources" + (": " + detail if detail else ""))
    return sorted(
        (root / name.decode("utf-8")).resolve()
        for name in result.stdout.split(b"\0") if name
        if not any(part in SKIP_DIRS for part in Path(name.decode("utf-8")).parts)
    )


def compile_databases(root):
    found = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if "compile_commands.json" in files:
            found.append(Path(current) / "compile_commands.json")
    return found


def main(argv):
    root = Path(argv[0] if argv else ".").resolve()
    try:
        sources = tracked_sources(root)
    except RuntimeError as error:
        print(f"handler CI gate: ERROR: {error}", file=sys.stderr)
        return 2

    if not sources:
        print("handler CI gate: SKIP (no tracked C/C++ source files in this checkout)")
        return 0

    databases = compile_databases(root)
    if not databases:
        print(
            f"handler CI gate: ERROR: found {len(sources)} tracked C/C++ source file(s), "
            "but no compile_commands.json; refusing to pass without the build configuration",
            file=sys.stderr,
        )
        return 1

    checker = Path(__file__).with_name("check-handler-signatures.py")
    command = [
        sys.executable, str(checker), "--compile-db-root", str(root),
        *(str(source) for source in sources),
    ]
    result = subprocess.run(command, cwd=root, check=False)
    if result.returncode:
        print("handler CI gate: ERROR: compile-database handler audit failed", file=sys.stderr)
        return result.returncode
    print(
        f"handler CI gate: PASS ({len(sources)} tracked C/C++ source file(s), "
        f"{len(databases)} compile database(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
