#!/usr/bin/env python3
"""Structural linter for session checkpoint files.

Checks the shape a checkpoint needs to be readable cold: every required
section present and carrying real content, an absolute `updated:` date in
frontmatter, no relative time words (they are meaningless to a reader who
arrives days later), and enough substance to be worth resuming from.

Stdlib only. Exit 0 when clean, 1 on any failure.

Usage:
    python3 tools/checkpoint_lint.py CHECKPOINT.md [more.md ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# A checkpoint missing any of these cannot restore a session at depth.
# Matched as a header prefix, so "Decisions and why" satisfies "Decisions".
REQUIRED_SECTIONS = ("Objective", "State", "Decisions", "Open threads", "Gotchas")

FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\s*$", re.S | re.M)
UPDATED = re.compile(r"^updated:\s*(\S+)\s*$", re.M)
ISO_DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
HEADER = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
FENCED_BLOCK = re.compile(r"^(```|~~~).*?^\1\s*$", re.M | re.S)

# Time words that only mean something to the session that wrote them.
# "The migration broke yesterday" is unreadable a week later; the date is not.
RELATIVE_DATES = re.compile(
    r"\b(yesterday|today|tomorrow|tonight"
    # "the next session" is checkpoint vocabulary, not a date claim, so
    # `session` is deliberately absent from these two groups.
    r"|last (?:night|week|month|time)"
    r"|next (?:week|month)"
    r"|this (?:morning|afternoon|evening|week|month)"
    r"|(?:a|two|three|few|several|couple of) (?:days?|weeks?|months?) ago"
    r"|just now|earlier today|the other day)\b",
    re.I,
)

# Below this, a checkpoint is a summary wearing a checkpoint's headings.
# Advisory: a genuinely short session can produce a short honest checkpoint.
THIN_WORD_COUNT = 150


def prose_only(text: str) -> str:
    # Fenced blocks hold commands and log excerpts, not narrative claims.
    return FENCED_BLOCK.sub("", text)


def body_without_frontmatter(text: str) -> str:
    match = FRONTMATTER.search(text)
    return text[match.end():] if match else text


def sections(text: str) -> list[tuple[str, str]]:
    """(header title, body) pairs, in document order."""
    marks = list(HEADER.finditer(text))
    out = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((mark.group(2), text[mark.end():end]))
    return out


def check_frontmatter(text: str, name: str) -> list[str]:
    match = FRONTMATTER.search(text)
    if not match:
        return [f"{name}: no YAML frontmatter (needs an `updated:` date)"]
    found = UPDATED.search(match.group(1))
    if not found:
        return [f"{name}: frontmatter has no `updated:` line"]
    if not ISO_DATE.match(found.group(1)):
        return [f"{name}: `updated: {found.group(1)}` is not an absolute YYYY-MM-DD date"]
    return []


def check_sections(text: str, name: str) -> list[str]:
    found = sections(body_without_frontmatter(text))
    fails = []
    for required in REQUIRED_SECTIONS:
        matches = [body for title, body in found if title.startswith(required)]
        if not matches:
            fails.append(f"{name}: missing section '{required}'")
        elif not any(prose_only(body).strip() for body in matches):
            fails.append(f"{name}: section '{required}' is empty")
    return fails


def check_relative_dates(text: str, name: str) -> list[str]:
    fails = []
    for number, line in enumerate(prose_only(text).splitlines(), start=1):
        for hit in RELATIVE_DATES.finditer(line):
            fails.append(
                f"{name}:{number}: relative date '{hit.group(0)}' "
                f"(use an absolute YYYY-MM-DD date)"
            )
    return fails


def warn_thin(text: str, name: str) -> list[str]:
    words = len(body_without_frontmatter(text).split())
    if words >= THIN_WORD_COUNT:
        return []
    return [
        f"{name}: {words} words across {len(REQUIRED_SECTIONS)} required sections "
        f"— thin enough to be a summary, not a checkpoint"
    ]


def lint(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    name = str(path)
    fails = (
        check_frontmatter(text, name)
        + check_sections(text, name)
        + check_relative_dates(text, name)
    )
    return fails, warn_thin(text, name)


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        print("usage: checkpoint_lint.py CHECKPOINT.md [more.md ...]")
        return 1

    fails, warns = [], []
    for path in paths:
        if not path.is_file():
            fails.append(f"{path}: no such file")
            continue
        file_fails, file_warns = lint(path)
        fails += file_fails
        warns += file_warns

    for line in fails:
        print(f"FAIL {line}")
    for line in warns:
        print(f"WARN {line}")
    verdict = "FAIL" if fails else "PASS"
    print(f"{verdict}: {len(paths)} checkpoint(s), {len(fails)} failures, {len(warns)} warnings")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
