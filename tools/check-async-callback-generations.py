#!/usr/bin/env python3
"""Require generation capture/validation for asynchronous native callbacks.

C/C++, Rust and Zig are scanned using language-specific function discovery.
Annotations remain a reviewable contract because callback registration APIs
and ownership models differ between backends.
"""
import re
import subprocess
import sys
from pathlib import Path

SOURCE_SUFFIXES = {
    ".c", ".h", ".cc", ".hh", ".cpp", ".hpp", ".cxx", ".hxx", ".rs", ".zig",
}
SKIP_PARTS = {
    ".git", "build", "build-debug", "build-release", "out", "target",
    "vendor", "third_party", "third-party", "generated", "autogen",
    "tests", "test", "fixtures", "mock", "mocks", "stubs",
}
ASYNC_SIGNAL = re.compile(
    r"\b(?:vkQueueSubmit2?|vkQueuePresentKHR|vkWaitForFences|"
    r"vkWaitSemaphores|vkGetSemaphoreCounterValue|vkDeviceWaitIdle|"
    r"std::async|std::thread::spawn|thread::spawn|tokio::spawn|"
    r"spawn_blocking|JoinHandle|Future|async\s+fn|\.await|"
    r"@asyncCall|Thread\.spawn|std\.Thread\.spawn|"
    r"dispatch_async|async_submit|submit_async|"
    r"register_callback|set_callback|add_callback|completion_callback|"
    r"on_complete|on_completion|callback|completion|"
    r"fence|semaphore|queue_submit|queue_present)\b",
    re.I,
)
ANNOTATION = re.compile(
    r"XAV_ASYNC_CALLBACK_(REGISTER|VALIDATE)\s*:\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*;\s*([^*\r\n]+)"
)
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def tracked_sources(root):
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--",
         "*.c", "*.h", "*.cc", "*.hh", "*.cpp", "*.hpp", "*.cxx", "*.hxx",
         "*.rs", "*.zig"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        rel = Path(raw.decode("utf-8"))
        if rel.suffix not in SOURCE_SUFFIXES or any(p in SKIP_PARTS for p in rel.parts):
            continue
        paths.append(root / rel)
    return sorted(paths)


def strip_comments_and_literals(source):
    # Preserve newlines and offsets sufficiently for brace-based body scanning.
    pattern = re.compile(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|'
        r"'(?:\\.|[^'\\])*'",
        re.S,
    )
    return pattern.sub(lambda m: "\n" * m.group(0).count("\n"), source)


def function_body(source, name, suffix):
    escaped = re.escape(name)
    if suffix == ".rs":
        definition = re.compile(
            r"\b(?:pub\s+)?(?:unsafe\s+)?(?:async\s+)?fn\s+" + escaped
            + r"\s*(?:<[^>{}]*>)?\s*\([^{};]*\)[^{;]*\{", re.S,
        )
    elif suffix == ".zig":
        definition = re.compile(
            r"\b(?:pub\s+)?fn\s+" + escaped
            + r"\s*\([^{};]*\)[^{;]*\{", re.S,
        )
    else:
        definition = re.compile(
            r"\b" + escaped + r"\s*\([^;{}]*\)\s*\{", re.S,
        )
    for match in definition.finditer(source):
        start = source.find("{", match.start())
        depth = 0
        for i in range(start, len(source)):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    return source[start + 1:i]
    return None


def audit_file(path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    code = strip_comments_and_literals(raw)
    if not ASYNC_SIGNAL.search(code):
        return []
    annotations = {}
    for match in ANNOTATION.finditer(raw):
        kind, callback, values = match.groups()
        names = [item.strip() for item in values.split(";")]
        if not names or any(not IDENT.fullmatch(x) for x in names):
            return [f"{path}: malformed {kind} annotation for {callback}"]
        if kind in annotations.setdefault(callback, {}):
            return [f"{path}: duplicate {kind} annotation for {callback}"]
        annotations[callback][kind] = set(names)

    if not annotations:
        return [f"{path}: asynchronous callback path detected but no XAV_ASYNC_CALLBACK_REGISTER/VALIDATE annotations found"]

    errors = []
    for callback, entries in sorted(annotations.items()):
        registered = entries.get("REGISTER")
        validated = entries.get("VALIDATE")
        if registered is None:
            errors.append(f"{path}: {callback}: missing REGISTER capture annotation")
            continue
        if validated is None:
            errors.append(f"{path}: {callback}: missing VALIDATE annotation")
            continue
        if "device_generation" not in registered:
            errors.append(f"{path}: {callback}: registration does not capture device_generation")
        if "device_generation" not in validated:
            errors.append(f"{path}: {callback}: callback does not validate device_generation")
        missing = registered - validated
        if missing:
            errors.append(f"{path}: {callback}: captured generations not validated: {', '.join(sorted(missing))}")
        body = function_body(code, callback, path.suffix)
        if body is None:
            errors.append(f"{path}: {callback}: annotated callback function definition not found")
            continue
        if len(re.findall(r"\b" + re.escape(callback) + r"\b", code)) < 2:
            errors.append(f"{path}: {callback}: callback symbol is not referenced by a registration/dispatch site")
        if re.search(r"\b(?:buffer|memory|fence|semaphore|swapchain|image|resource)\b", body, re.I) and "resource_generation" not in registered:
            errors.append(f"{path}: {callback}: resource-bearing callback must capture resource_generation")
        if re.search(r"\b(?:command_buffer|recording)\b", body, re.I) and "recording_epoch" not in registered:
            errors.append(f"{path}: {callback}: command-buffer callback must capture recording_epoch")
        for generation in sorted(registered):
            if not re.search(r"\b" + re.escape(generation) + r"\b", body):
                errors.append(f"{path}: {callback}: callback body does not use captured {generation}")
                continue
            if not re.search(
                r"(?:\b" + re.escape(generation) + r"\b[^;{}]{0,160}(?:==|!=)|"
                r"(?:==|!=)[^;{}]{0,160}\b" + re.escape(generation) + r"\b|"
                r"(?:validate|check|matches|is_current)[A-Za-z0-9_]*\s*\([^;]*\b"
                + re.escape(generation) + r"\b)",
                body, re.I,
            ):
                errors.append(f"{path}: {callback}: no comparison/current-generation validation for {generation} found in callback body")
    return errors


def main(argv):
    root = Path(argv[0] if argv else ".").resolve()
    try:
        sources = tracked_sources(root)
    except RuntimeError as error:
        print(f"async callback generation audit: ERROR: {error}", file=sys.stderr)
        return 2
    checked = 0
    errors = []
    for path in sources:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            asynchronous = bool(ASYNC_SIGNAL.search(strip_comments_and_literals(source)))
            file_errors = audit_file(path)
        except OSError as error:
            errors.append(f"{path}: cannot read source: {error}")
            continue
        if asynchronous:
            checked += 1
        errors.extend(file_errors)
    if errors:
        for error in errors:
            print("ERROR: " + error)
        return 1
    print(f"async callback generation audit: PASS ({checked} asynchronous source file(s), {len(sources)} tracked native source file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
