#!/usr/bin/env python3
"""Find conflicting C handler signatures and dispatch function-pointer types.

This lightweight source audit compares handler declarations and function-pointer
table entries across the supplied translation-unit sources. It complements,
but does not replace, the compiler's C type checker.
"""
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

NAME = r"(?:Proc|SProc|proc_|sproc_)[A-Za-z0-9_]*(?:Req|Request)?"
IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
RETURN = r"(?:(?:[A-Za-z_][A-Za-z0-9_]*\s+)*[A-Za-z_][A-Za-z0-9_]*\s*\*\s*|[A-Za-z_][A-Za-z0-9_ \t]*?)"
FUNCTION = re.compile(
    rf"(?P<ret>{RETURN})\s*(?P<name>{NAME})\s*\((?P<args>[^;{{}}]*)\)\s*(?=[{{;])"
)
TABLE_PREFIX = re.compile(
    r"(?P<ret>[A-Za-z_][A-Za-z0-9_ \t\*]*?)\(\s*\*\s*"
    r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^]]*\])?\s*\)\s*"
)
TYPEDEF_PREFIX = re.compile(
    r"\btypedef\s+(?P<ret>[A-Za-z_][A-Za-z0-9_ \t\*]*?)"
    r"\(\s*\*\s*(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*"
)
TYPEDEF_ALIAS = re.compile(
    rf"\btypedef\s+(?P<base>{IDENT})\s+(?P<alias>{IDENT})\s*;"
)
INCLUDE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.M)
ALIASED_TABLE = re.compile(
    rf"\b(?P<alias>{IDENT})\s+(?P<table>{IDENT})\s*"
    r"(?:\[[^]]*\])?\s*=\s*\{(?P<body>[^}]*)\}",
    re.S,
)
HANDLER_REF = re.compile(rf"\b{NAME}\b")


def compact(value):
    return re.sub(r"\s+", " ", value.strip())


def matching_delimiter(source, start, opening="(", closing=")"):
    """Return the matching delimiter index, handling nested C declarators."""
    if start >= len(source) or source[start] != opening:
        return None
    depth = 0
    quote = None
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


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


def clean_text(source):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", " ", source, flags=re.S)
    return source


def clean_source(path):
    return clean_text(Path(path).read_text(encoding="utf-8", errors="replace"))


def iter_function_pointer_typedefs(source):
    for match in TYPEDEF_PREFIX.finditer(source):
        opening = match.end()
        while opening < len(source) and source[opening].isspace():
            opening += 1
        end = matching_delimiter(source, opening)
        if end is not None and re.match(r"\s*;", source[end + 1:]):
            yield match.group("alias"), (
                f"{normalize_return(match.group('ret'))} (*)({normalize_args(source[opening + 1:end])})"
            )
    for match in TYPEDEF_ALIAS.finditer(source):
        yield match.group("alias"), match.group("base")


def iter_dispatch_tables(source):
    for match in TABLE_PREFIX.finditer(source):
        opening = match.end()
        while opening < len(source) and source[opening].isspace():
            opening += 1
        end = matching_delimiter(source, opening)
        if end is None:
            continue
        tail = re.match(r"\s*=\s*\{(?P<body>[^}]*)\}", source[end + 1:], re.S)
        if tail:
            yield match.group("table"), (
                f"{normalize_return(match.group('ret'))} (*)({normalize_args(source[opening + 1:end])})"
            ), tail.group("body")


def resolve_alias(alias, aliases, seen=None):
    """Resolve a typedef chain only when every link has one unambiguous target."""
    seen = set() if seen is None else seen
    if alias in seen:
        return None
    targets = aliases.get(alias, set())
    if len(targets) != 1:
        return None
    target = next(iter(targets))
    if target.endswith(")") and "(*)" in target:
        return target
    if re.fullmatch(IDENT, target):
        return resolve_alias(target, aliases, seen | {alias})
    return None


def aliases_visible_from(path, sources, includes):
    """Collect typedefs in one translation unit and its supplied quoted headers."""
    aliases = defaultdict(set)
    visited = set()

    def visit(current):
        current = Path(current).resolve()
        if current in visited or current not in sources:
            return
        visited.add(current)
        source = sources[current]
        for alias, target in iter_function_pointer_typedefs(source):
            aliases[alias].add(target)
        for include in includes[current]:
            candidate = (current.parent / include).resolve()
            if candidate in sources:
                visit(candidate)

    visit(path)
    return aliases


def scan(path, source, aliases):
    signatures = defaultdict(set)
    origins = defaultdict(set)
    for match in FUNCTION.finditer(source):
        name = match.group("name")
        signature = f"{normalize_return(match.group('ret'))} (*)({normalize_args(match.group('args'))})"
        signatures[name].add(signature)
        origins[name].add(str(path))

    for table, pointer_type, body in iter_dispatch_tables(source):
        for name in HANDLER_REF.findall(body):
            signatures[name].add(pointer_type)
            origins[name].add(f"{path} [{table}]")
    for match in ALIASED_TABLE.finditer(source):
        pointer_type = resolve_alias(match.group("alias"), aliases)
        if pointer_type is None:
            continue
        for name in HANDLER_REF.findall(match.group("body")):
            signatures[name].add(pointer_type)
            origins[name].add(f"{path} [{match.group('table')}: {match.group('alias')}]")
    return signatures, origins


def preprocess(path, root):
    helper = Path(__file__).with_name("preprocess-xav-source.py")
    try:
        result = subprocess.run(
            [sys.executable, str(helper), str(root), str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    except OSError as error:
        print(f"handler signature check: cannot run preprocessor helper: {error}", file=sys.stderr)
        return None
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        print(f"handler signature check: preprocessing failed for {path}" +
              (f": {detail}" if detail else ""), file=sys.stderr)
        return None
    return result.stdout.decode("utf-8", errors="replace")


def main(argv):
    compile_root = None
    if len(argv) >= 2 and argv[0] == "--compile-db-root":
        compile_root = Path(argv[1]).resolve()
        argv = argv[2:]
    paths = argv
    if not paths:
        print(f"usage: {Path(sys.argv[0]).name} [--compile-db-root ROOT] source.c [...]", file=sys.stderr)
        return 2

    resolved_paths = [Path(path).resolve() for path in paths]
    sources = {}
    for original, resolved in zip(paths, resolved_paths):
        source = preprocess(resolved, compile_root) if compile_root else Path(resolved).read_text(
            encoding="utf-8", errors="replace"
        )
        if source is None:
            return 2
        sources[resolved] = clean_text(source)

    # Preprocessed translation units already contain their active header
    # definitions. Raw-source mode retains explicit quoted-include traversal.
    includes = {
        resolved: ([] if compile_root else INCLUDE.findall(
            Path(resolved).read_text(encoding="utf-8", errors="replace")
        ))
        for resolved in resolved_paths
    }
    signatures = defaultdict(set)
    origins = defaultdict(set)
    for original, resolved in zip(paths, resolved_paths):
        found, locations = scan(original, sources[resolved],
                                aliases_visible_from(resolved, sources, includes))
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
