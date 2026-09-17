"""Tests that the shipped Markdown renders the way it reads.

An unclosed or overlong code fence turns the prose after it into one grey
code block on GitHub, and nothing else in the suite would notice. These
tests scan the real files with the CommonMark fence rules.
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# CommonMark: up to three spaces of indent, then three or more backticks or
# tildes. A closing fence uses the same character, is at least as long as
# the opener, and carries nothing but whitespace after it.
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*$")


def fenced_lines(path):
    """(line number, text, open fence or None) for every line, plus the
    fence still open at end of file, if any."""
    rows, opener = [], None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = FENCE.match(line)
        if opener is None:
            if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
                opener = (number, match.group(1))
                rows.append((number, line, None))
                continue
        elif (
            match
            and match.group(1)[0] == opener[1][0]
            and len(match.group(1)) >= len(opener[1])
            and not match.group(2).strip()
        ):
            rows.append((number, line, None))
            opener = None
            continue
        rows.append((number, line, opener))
    return rows, opener


def fenced_headings(path):
    rows, _ = fenced_lines(path)
    return [
        (number, HEADING.match(line).group(2))
        for number, line, opener in rows
        if opener and HEADING.match(line)
    ]


class DocsFenceTest(unittest.TestCase):
    def test_every_fence_in_readme_and_docs_closes(self):
        for path in [REPO / "README.md", *sorted((REPO / "docs").glob("*.md"))]:
            _, still_open = fenced_lines(path)
            with self.subTest(file=path.name):
                self.assertIsNone(
                    still_open,
                    f"{path.name}:{still_open and still_open[0]} opens a fence that never closes",
                )

    def test_readme_outline_headings_sit_outside_fences(self):
        # The only headings allowed inside a README fence are the ones in the
        # template example, and docs/anatomy.md is the source of truth for it.
        template = {title for _, title in fenced_headings(REPO / "docs" / "anatomy.md")}
        stray = [
            f"README.md:{number}: '{title}'"
            for number, title in fenced_headings(REPO / "README.md")
            if title not in template
        ]
        self.assertEqual(stray, [], "README headings rendered as code")


if __name__ == "__main__":
    unittest.main()
