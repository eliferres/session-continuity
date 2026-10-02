"""Tests for the two resume hooks in hooks/.

Each case builds a real project directory with real files and runs the
real bash script on it, the way the harness calls it.
"""

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SESSION_START = REPO / "hooks" / "sessionstart-resume.sh"
PRE_COMPACT = REPO / "hooks" / "precompact-checkpoint.sh"

CHECKPOINT = """---
type: session-checkpoint
updated: 2026-03-11
---

# Checkpoint - parser rewrite

## Objective
Replace the hand-rolled config parser with a schema-validated one.

## Open threads
1. Port the `--profile` flag in `src/cli.py`.
"""


class HookCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.archive = self.project / ".checkpoints"

    def tearDown(self):
        self._tmp.cleanup()

    def execute(self, script, payload, env=None):
        full_env = {"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(self.project)}
        full_env.update(env or {})
        out = subprocess.run(["bash", str(script)], input=json.dumps(payload),
                             capture_output=True, text=True, env=full_env)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out

    def checkpoint(self, filename, age=0):
        path = self.project / filename
        path.write_text(CHECKPOINT)
        if age:
            then = time.time() - age
            os.utime(path, (then, then))
        return path


class SessionStartTest(HookCase):
    def run_hook(self, env=None):
        payload = {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"}
        return self.execute(SESSION_START, payload, env).stdout

    def test_announces_the_checkpoint_with_its_date(self):
        (self.project / "CHECKPOINT.md").write_text(CHECKPOINT)
        self.assertIn("RESUME AVAILABLE", self.run_hook())
        self.assertIn("updated: 2026-03-11", self.run_hook())

    def test_prints_the_exact_resume_cue_to_paste_into_a_fresh_session(self):
        (self.project / "CHECKPOINT.md").write_text(CHECKPOINT)
        self.assertIn("Resume cue: continue from CHECKPOINT.md", self.run_hook())

    def test_the_cue_names_a_checkpoint_set_by_environment(self):
        (self.project / "state.md").write_text(CHECKPOINT)
        out = self.run_hook({"SESSION_CHECKPOINT_FILE": str(self.project / "state.md")})
        self.assertIn("Resume cue: continue from state.md", out)

    def test_no_checkpoint_prints_nothing(self):
        self.assertEqual(self.run_hook(), "")


class NamedCheckpointStartTest(HookCase):
    """Parallel sessions, each with its own CHECKPOINT-<name>.md."""

    run_hook = SessionStartTest.run_hook

    def test_lists_every_checkpoint_newest_first_with_its_cue(self):
        self.checkpoint("CHECKPOINT-billing.md", age=600)
        self.checkpoint("CHECKPOINT-search.md", age=60)
        out = self.run_hook()
        self.assertIn("Resume cue: continue from CHECKPOINT-billing.md", out)
        self.assertIn("Resume cue: continue from CHECKPOINT-search.md", out)
        self.assertLess(out.index("CHECKPOINT-search.md"), out.index("CHECKPOINT-billing.md"))

    def test_a_named_session_is_shown_only_its_own_checkpoint(self):
        self.checkpoint("CHECKPOINT-billing.md")
        self.checkpoint("CHECKPOINT-search.md")
        out = self.run_hook({"SESSION_CHECKPOINT_NAME": "billing"})
        self.assertIn("Resume cue: continue from CHECKPOINT-billing.md", out)
        self.assertNotIn("search", out)

    def test_a_named_session_with_no_checkpoint_yet_is_told_its_file(self):
        # Without this line the agent only knows the default file name and
        # would write into the shared CHECKPOINT.md.
        self.checkpoint("CHECKPOINT.md")
        out = self.run_hook({"SESSION_CHECKPOINT_NAME": "billing"})
        self.assertNotIn("RESUME AVAILABLE", out)
        self.assertIn("CHECKPOINT-billing.md", out)

    def test_the_template_is_never_offered_as_a_resume(self):
        self.checkpoint("CHECKPOINT-TEMPLATE.md")
        self.assertEqual(self.run_hook(), "")

    def test_a_compaction_in_one_named_session_marks_only_its_checkpoint_stale(self):
        self.checkpoint("CHECKPOINT-billing.md", age=600)
        self.checkpoint("CHECKPOINT-search.md", age=600)
        self.archive.mkdir()
        (self.archive / "last-compaction-billing.txt").write_text(str(int(time.time())))
        out = self.run_hook()
        warning = out.index("WARNING")
        self.assertGreater(warning, out.index("CHECKPOINT-billing.md"))
        self.assertEqual(out.count("WARNING"), 1)

    def test_a_bad_name_is_reported_and_every_checkpoint_listed(self):
        self.checkpoint("CHECKPOINT.md")
        payload = {"hook_event_name": "SessionStart", "session_id": "s1"}
        out = self.execute(SESSION_START, payload, {"SESSION_CHECKPOINT_NAME": "../etc"})
        self.assertIn("SESSION_CHECKPOINT_NAME", out.stderr)
        self.assertIn("Resume cue: continue from CHECKPOINT.md", out.stdout)


class PreCompactTest(HookCase):
    def run_hook(self, env=None):
        payload = {"hook_event_name": "PreCompact", "session_id": "s1", "trigger": "auto"}
        return self.execute(PRE_COMPACT, payload, env)

    def archived(self):
        return sorted(p.name for p in self.archive.glob("*.md"))

    def test_a_named_session_archives_only_its_own_checkpoint(self):
        self.checkpoint("CHECKPOINT-billing.md")
        self.checkpoint("CHECKPOINT-search.md")
        self.run_hook({"SESSION_CHECKPOINT_NAME": "billing"})
        names = self.archived()
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].endswith("-billing-checkpoint.md"), names)
        self.assertTrue((self.archive / "last-compaction-billing.txt").is_file())
        self.assertFalse((self.archive / "last-compaction.txt").exists())

    def test_an_unnamed_session_archives_every_checkpoint(self):
        self.checkpoint("CHECKPOINT.md")
        self.checkpoint("CHECKPOINT-search.md")
        self.checkpoint("CHECKPOINT-TEMPLATE.md")
        self.run_hook()
        names = self.archived()
        self.assertEqual(len(names), 2, names)
        self.assertTrue(any(n.endswith("-search-checkpoint.md") for n in names))
        self.assertTrue((self.archive / "last-compaction.txt").is_file())

    def test_a_named_session_without_its_checkpoint_leaves_the_marker(self):
        self.checkpoint("CHECKPOINT-search.md")
        self.run_hook({"SESSION_CHECKPOINT_NAME": "billing"})
        names = self.archived()
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].endswith("-billing-no-checkpoint.md"), names)


if __name__ == "__main__":
    unittest.main()
