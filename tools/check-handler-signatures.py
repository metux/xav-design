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
RETURN = r"(?:(?:[A-Za-z_][A-Za-z0-9_]*\s+)*[A-Za-z_][A-Za-z0-9_]*\s*\*\s*|[A-Za-z_][A-Za-z0-9_ \t]*?)"
FUNCTION = re.compile(
    rf"(?P<ret>{RETURN})\s*(?P<name>{NAME})\s*\((?P<args>[^;{{}}]*)\)\s*(?=[{{;])"
)
TABLE = re.compile(
    r"(?P<ret>[A-Za-z_][A-Za-z0-9_ \t\*]*?)\(\s*\*\s*"
    r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^]]*\])?\s*\)"
    r"\s*\((?P<args>[^()]*)\)\s*=\s*\{(?P<body>[^}]*)\}",
    re.S,
)
# Simple typedef'd function pointers are common in dispatch tables. Keep this
# deliberately narrow: nested declarators still belong to the C compiler.
TYPEDEF = re.compile(
    r"\btypedef\s+(?P<ret>[A-Za-z_][A-Za-z0-9_ \t\*]*?)"
    r"\(\s*\*\s*(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\s*\)"
    r"\s*\((?P<args>[^()]*)\)\s*;",
    re.S,
)
ALIASED_TABLE = re.compile(
    r"\b(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s*"
    r"(?:\[[^]]*\])?\s*=\s*\{(?P<body>[^}]*)\}",
    re.S,
)
HANDLER_REF = re.compile(rf"\b{NAME}\b")


def compact(value):
    return re.sub(r"\s+", " ", value.strip())


def split_top_level(value):
    """Split a parameter list without treating nested commas as separators."""
    parts = []
    start = 0
    depth = 0
    for index, char in enumerate(value):
        if char in "([": 
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def normalize_args(value):
    value = compact(value)
    if value in ("", "void", "..."):
        return value
    parts = []
    for item in split_top_level(value):
        item = compact(item)
        item = re.sub(r"\(\s*\*\s*[A-Za-z_][A-Za-z0-9_]*\s*\)", "(*)", item)
        item = re.sub(r"\s+[A-Za-z_][A-Za-z0-9_]*$", "", item)
        parts.append(item)
    return ", ".join(parts)


def normalize_return(value):
    """Remove storage/function specifiers without erasing type qualifiers."""
    value = compact(value)
    while True:
        stripped = re.sub(r"^(static|extern|inline|register)\s+", "", value)
        if stripped == value:
            return value
        value = stripped


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

    typedefs = {}
    for match in TYPEDEF.finditer(source):
        typedefs[match.group("alias")] = (
            f"{normalize_return(match.group('ret'))} (*)({normalize_args(match.group('args'))})"
        )
    for match in TABLE.finditer(source):
        pointer_type = f"{normalize_return(match.group('ret'))} (*)({normalize_args(match.group('args'))})"
        for name in HANDLER_REF.findall(match.group("body")):
            signatures[name].add(pointer_type)
            origins[name].add(f"{path} [{match.group('table')}]")
    for match in ALIASED_TABLE.finditer(source):
        pointer_type = typedefs.get(match.group("alias"))
        if pointer_type is None:
            continue
        for name in HANDLER_REF.findall(match.group("body")):
            signatures[name].add(pointer_type)
            origins[name].add(f"{path} [{match.group('table')}: {match.group('alias')}]")
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
