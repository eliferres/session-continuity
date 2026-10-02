"""Tests for the two resume hooks in hooks/.

Each case builds a real project directory with real files and runs the
real bash script on it, the way the harness calls it.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SESSION_START = REPO / "hooks" / "sessionstart-resume.sh"

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


class SessionStartTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_hook(self, env=None):
        full_env = {"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(self.project)}
        full_env.update(env or {})
        payload = {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"}
        out = subprocess.run(["bash", str(SESSION_START)], input=json.dumps(payload),
                             capture_output=True, text=True, env=full_env)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

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


if __name__ == "__main__":
    unittest.main()
