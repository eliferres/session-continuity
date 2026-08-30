"""Tests for checkpoint_lint.

Every case writes a real checkpoint file to disk and runs the real checks
on it, including two differential tests against what this repo ships: the
worked example and the blank template must both pass their own linter.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import checkpoint_lint  # noqa: E402


GOOD = """---
type: session-checkpoint
updated: 2026-03-11
---

# Checkpoint — parser rewrite

## Objective
Replace the hand-rolled config parser with a schema-validated one.

## State
`src/config.py` parses the new schema and `python3 -m pytest tests/` is
green, 24 passed. The CLI in `src/cli.py` still reads the old keys, so
`--profile` is the one flag that has not been ported. Nothing on the
service side has been touched.

## Decisions and why
Validate the whole schema at the boundary rather than checking fields
where they are used. Four call sites would each have grown their own
coercion rules and drifted apart, and a single failure point is the only
version anyone can audit later.

Keep the old key names as aliases for one release. Renaming them now
would break every deployed config file for a cosmetic gain.

## Open threads
1. Port the `--profile` flag in `src/cli.py` to the new loader.
2. Delete the alias table once the release after this one ships.

## Gotchas and dead ends
`pytest -k config` passes even when coercion is wrong, because the
fixtures use strings that happen to round-trip through both parsers. Run
the whole file and assert on typed values.

Loading the schema at import time was tried and reverted: it makes the
error surface at import rather than at the call, and the traceback then
points at the wrong module entirely.
"""


class CheckpointLintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, text):
        path = self.dir / "CHECKPOINT.md"
        path.write_text(text, encoding="utf-8")
        return path

    def lint(self, text):
        return checkpoint_lint.lint(self.write(text))

    def run_cli(self, *paths):
        return subprocess.run(
            [sys.executable, str(REPO / "tools" / "checkpoint_lint.py"), *map(str, paths)],
            capture_output=True,
            text=True,
        )

    def test_shipped_example_passes(self):
        # End to end through the CLI, exit code included: the example this
        # repo ships must satisfy the format this repo specifies.
        example = next((REPO / "examples").glob("*.md"))
        proc = self.run_cli(example)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

    def test_shipped_template_passes(self):
        proc = self.run_cli(REPO / "CHECKPOINT-TEMPLATE.md")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_good_checkpoint_passes(self):
        self.assertEqual(self.lint(GOOD), ([], []))

    def test_missing_section_fails(self):
        fails, _ = self.lint(GOOD.replace("## Gotchas and dead ends", "## Notes"))
        self.assertTrue(any("missing section 'Gotchas'" in f for f in fails))

    def test_empty_section_fails(self):
        body_start = GOOD.index("## Open threads")
        body_end = GOOD.index("## Gotchas")
        emptied = GOOD[:body_start] + "## Open threads\n\n" + GOOD[body_end:]
        fails, _ = self.lint(emptied)
        self.assertTrue(any("'Open threads' is empty" in f for f in fails))

    def test_relative_date_flagged(self):
        fails, _ = self.lint(GOOD.replace("green, 24 passed.", "green as of yesterday."))
        self.assertTrue(any("yesterday" in f for f in fails))

    def test_relative_date_inside_code_fence_ignored(self):
        fenced = GOOD.replace(
            "## Open threads\n",
            "## Open threads\n```\ngit log --since=yesterday\n```\n",
        )
        self.assertEqual(self.lint(fenced), ([], []))

    def test_missing_frontmatter_date_fails(self):
        fails, _ = self.lint(GOOD.replace("updated: 2026-03-11\n", ""))
        self.assertTrue(any("no `updated:` line" in f for f in fails))

    def test_relative_frontmatter_date_fails(self):
        fails, _ = self.lint(GOOD.replace("2026-03-11", "March-ish"))
        self.assertTrue(any("not an absolute" in f for f in fails))

    def test_thin_checkpoint_warns_without_failing(self):
        thin = """---
type: session-checkpoint
updated: 2026-03-11
---

## Objective
Ship it.

## State
Mostly done.

## Decisions and why
None.

## Open threads
Finish.

## Gotchas and dead ends
None.
"""
        fails, warns = self.lint(thin)
        self.assertEqual(fails, [])
        self.assertTrue(any("thin enough" in w for w in warns))

    def test_missing_file_fails_cli(self):
        proc = self.run_cli(self.dir / "nope.md")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no such file", proc.stdout)


if __name__ == "__main__":
    unittest.main()
