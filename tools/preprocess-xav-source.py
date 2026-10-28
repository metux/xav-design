#!/usr/bin/env python3
"""Preprocess one C source using its build-system compile_commands.json entry."""
import json
import os
import shlex
import subprocess
import sys

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "third_party", "third-party",
    "generated", "target", ".cache", ".venv", "venv",
}


def canonical(path, directory):
    if not os.path.isabs(path):
        path = os.path.join(directory, path)
    return os.path.realpath(path)


def databases(root):
    root = os.path.realpath(root)
    for current, dirs, files in os.walk(root):
        rel = os.path.relpath(current, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith("build-")]
        if depth >= 5:
            dirs[:] = []
        if "compile_commands.json" in files:
            yield os.path.join(current, "compile_commands.json")


def entry_for(root, source):
    source = os.path.realpath(source)
    for database in databases(root):
        try:
            with open(database, encoding="utf-8") as stream:
                entries = json.load(stream)
        except (OSError, ValueError):
            continue
        for entry in entries:
            directory = entry.get("directory") or os.path.dirname(database)
            filename = entry.get("file")
            if filename and canonical(filename, directory) == source:
                return entry, directory
    return None, None


def compiler_args(entry, directory, source):
    args = entry.get("arguments")
    if args is None:
        command = entry.get("command")
        if not command:
            return None
        args = shlex.split(command)
    if not args:
        return None
    compiler = args[0]
    result = []
    skip_next = False
    paired = {"-o", "-MF", "-MT", "-MQ", "-MJ"}
    dep_flags = {"-c", "-MD", "-MMD", "-MP", "-MG"}
    for arg in args[1:]:
        if skip_next:
            skip_next = False
            continue
        if arg in paired:
            skip_next = True
            continue
        if arg in dep_flags:
            continue
        if arg == source or canonical(arg, directory) == source:
            continue
        if arg.startswith(("-MF", "-MT", "-MQ", "-MJ")) and len(arg) > 3:
            continue
        result.append(arg)
    return [compiler, *result, "-E", source]


def main():
    if len(sys.argv) != 3:
        return 2
    root, source = sys.argv[1:]
    entry, directory = entry_for(root, source)
    if entry is None:
        return 2
    command = compiler_args(entry, directory, os.path.realpath(source))
    if command is None:
        return 2
    try:
        completed = subprocess.run(
            command, cwd=directory, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False,
        )
    except OSError:
        return 2
    if completed.returncode:
        return 2
    sys.stdout.buffer.write(completed.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
