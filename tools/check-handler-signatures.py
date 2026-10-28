#!/usr/bin/env python3
"""Find conflicting C handler signatures and dispatch function-pointer types.

This lightweight source audit compares handler declarations and function-pointer
table entries across the supplied translation-unit sources. It complements,
but does not replace, the compiler's C type checker.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

NAME = r"(?:Proc|SProc|proc_|sproc_)[A-Za-z0-9_]*(?:Req|Request)?"
FUNCTION = re.compile(
    rf"(?P<ret>[A-Za-z_][A-Za-z0-9_ \t\*]*?)\s+"
    rf"(?P<name>{NAME})\s*\((?P<args>[^;{{}}]*)\)\s*(?=[{{;])"
)
TABLE = re.compile(
    r"(?P<ret>[A-Za-z_][A-Za-z0-9_ \t\*]*?)\(\s*\*\s*"
    r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^]]*\])?\s*\)"
    r"\s*\((?P<args>[^()]*)\)\s*=\s*\{(?P<body>[^}]*)\}",
    re.S,
)
HANDLER_REF = re.compile(rf"\b{NAME}\b")


def compact(value):
    return re.sub(r"\s+", " ", value.strip())


def normalize_args(value):
    value = compact(value)
    if value in ("", "void", "..."):
        return value
    parts = []
    for item in value.split(","):
        item = compact(item)
        item = re.sub(r"\s+[A-Za-z_][A-Za-z0-9_]*$", "", item)
        parts.append(item)
    return ", ".join(parts)


def normalize_return(value):
    value = compact(value)
    return re.sub(r"^(?:(?:static|extern|inline|register|const)\s+)+", "", value)


def scan(path):
    source = Path(path).read_text(encoding="utf-8", errors="replace")
    source = re.sub(r"/\*.*?\*/|//[^\n]*", " ", source, flags=re.S)
    source = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', " ", source)
    signatures = defaultdict(set)
    origins = defaultdict(set)
    for match in FUNCTION.finditer(source):
        name = match.group("name")
        signature = f"{normalize_return(match.group('ret'))} (*)({normalize_args(match.group('args'))})"
        signatures[name].add(signature)
        origins[name].add(str(path))
    for match in TABLE.finditer(source):
        pointer_type = f"{normalize_return(match.group('ret'))} (*)({normalize_args(match.group('args'))})"
        for name in HANDLER_REF.findall(match.group("body")):
            signatures[name].add(pointer_type)
            origins[name].add(f"{path} [{match.group('table')}]")
    return signatures, origins


def main(paths):
    if not paths:
        print(f"usage: {Path(sys.argv[0]).name} source.c [...]", file=sys.stderr)
        return 2
    signatures = defaultdict(set)
    origins = defaultdict(set)
    for path in paths:
        found, locations = scan(path)
        for name, types in found.items():
            signatures[name].update(types)
            origins[name].update(locations[name])
    conflicts = [(name, sorted(types)) for name, types in sorted(signatures.items()) if len(types) > 1]
    for name, types in conflicts:
        print(f"CONFLICT: {name}")
        for value in types:
            print(f"  type: {value}")
        for origin in sorted(origins[name]):
            print(f"  seen in: {origin}")
    if conflicts:
        return 1
    print(f"handler signature check: PASS ({len(signatures)} handler names)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
