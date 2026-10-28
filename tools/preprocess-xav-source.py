#!/usr/bin/env python3
"""Preprocess a C source/header using its translation unit's build flags."""
import json
import os
import re
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
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if depth >= 5:
            dirs[:] = []
        if "compile_commands.json" in files:
            yield os.path.join(current, "compile_commands.json")


def entries(root):
    for database in databases(root):
        try:
            with open(database, encoding="utf-8") as stream:
                commands = json.load(stream)
        except (OSError, ValueError):
            continue
        for entry in commands:
            directory = entry.get("directory") or os.path.dirname(database)
            filename = entry.get("file")
            if filename:
                yield entry, directory, canonical(filename, directory)


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


def run_preprocessor(entry, directory, translation_unit):
    command = compiler_args(entry, directory, translation_unit)
    if command is None:
        return None
    try:
        completed = subprocess.run(
            command, cwd=directory, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        if completed.stderr:
            sys.stderr.buffer.write(completed.stderr)
        return None
    return completed.stdout


def marker_path(line):
    match = re.match(rb'^#[ \\t]*[0-9]+[ \\t]+"([^"]+)"', line)
    if not match:
        return None
    try:
        return os.path.realpath(match.group(1).decode("utf-8"))
    except UnicodeDecodeError:
        return None


def mentions_file(output, target):
    # GCC/Clang line markers quote the resolved path; compare canonicalized
    # markers so relative build directories and symlinked roots both work.
    return any(marker_path(line) == target for line in output.splitlines())


def header_projection(output, target):
    """Return only lines originating in target, preserving target line markers."""
    projected = []
    active = False
    for line in output.splitlines(keepends=True):
        path = marker_path(line)
        if path is not None:
            active = path == target
            if active:
                projected.append(line)
            continue
        if active:
            projected.append(line)
    return b"".join(projected)


def projection_key(projection):
    # Ignore line-marker numbers/flags: identical header text can be reached
    # from TUs whose include stacks give it different marker metadata.
    return tuple(
        line for line in projection.splitlines()
        if marker_path(line) is None
    )


def main():
    if len(sys.argv) != 3:
        return 2
    root, requested = sys.argv[1:]
    requested = os.path.realpath(requested)
    candidates = list(entries(root))
    for entry, directory, source in candidates:
        if source == requested:
            output = run_preprocessor(entry, directory, source)
            if output is not None:
                sys.stdout.buffer.write(output)
                return 0
            return 2

    # Headers normally have no compile_commands.json entry. Preprocess actual
    # translation units and select one whose expanded include graph contains
    # this header. That preserves the TU's -D/-I/-include and language flags,
    # including macros established by preceding includes.
    if not requested.lower().endswith((".h", ".hh", ".hpp", ".hxx")):
        return 2
    # A header may be included by several translation units with different
    # -D/-U options. Keep every distinct preprocessing context; returning the
    # first match makes the discovery result depend on compile-database order
    # and can silently hide handlers enabled only in another translation unit.
    projections = []
    seen_projections = set()
    seen_contexts = set()
    for entry, directory, source in candidates:
        output = run_preprocessor(entry, directory, source)
        if output is None or not mentions_file(output, requested):
            continue
        # Avoid duplicate compile-database entries, then retain only the
        # requested header's active lines. Full TU output would repeat source
        # and unrelated include content, creating duplicate or misleading hits.
        args = entry.get("arguments")
        if args is None:
            args = shlex.split(entry.get("command", ""))
        context = (source, tuple(args))
        if context in seen_contexts:
            continue
        seen_contexts.add(context)
        projection = header_projection(output, requested)
        if not projection:
            continue
        key = projection_key(projection)
        if key in seen_projections:
            continue
        seen_projections.add(key)
        projections.append(projection)
    if projections:
        for projection in projections:
            sys.stdout.buffer.write(projection)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
