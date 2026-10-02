"""Tests for hooks/context-watch.py.

Every case writes a real transcript file in the harness's JSONL shape and
runs the real script on it as a subprocess, the way the harness calls it.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "hooks" / "context-watch.py"


def assistant(input_tokens, cache_read=0, cache_write=0, **extra):
    usage = {
        "input_tokens": input_tokens,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_write,
        "output_tokens": 50,
    }
    usage.update(extra.pop("usage_extra", {}))
    row = {"type": "assistant", "message": {"model": "m", "usage": usage}}
    row.update(extra)
    return row


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.transcript = self.dir / "session.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def write_transcript(self, rows):
        self.transcript.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def measure(self, path=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--measure", str(path or self.transcript)],
            capture_output=True, text=True,
        )


class MeasureTest(Base):
    def test_sums_input_cache_read_and_cache_write_of_the_last_call(self):
        self.write_transcript([
            assistant(10, 1000, 100),
            user("next"),
            assistant(3, 150000, 2000),
        ])
        out = self.measure()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "152003")

    def test_skips_a_synthetic_error_row_with_zero_usage(self):
        # A rate-limit error is written as an assistant row with zero usage;
        # read as the context it would report an empty session.
        self.write_transcript([
            assistant(5, 90000, 0),
            {"type": "assistant", "isApiErrorMessage": True,
             "message": {"model": "<synthetic>", "usage": {"input_tokens": 0}}},
        ])
        self.assertEqual(self.measure().stdout.strip(), "90005")

    def test_reads_the_last_iteration_when_usage_is_summed_over_several(self):
        # When one turn makes more than one model call, the top-level usage
        # sums them and roughly doubles the count; the last message
        # iteration is the context the next call re-reads.
        self.write_transcript([
            assistant(20, 200000, 0, usage_extra={"iterations": [
                {"type": "message", "input_tokens": 10,
                 "cache_read_input_tokens": 99000, "cache_creation_input_tokens": 0},
                {"type": "message", "input_tokens": 10,
                 "cache_read_input_tokens": 101000, "cache_creation_input_tokens": 0},
            ]}),
        ])
        self.assertEqual(self.measure().stdout.strip(), "101010")

    def test_reads_only_the_tail_of_a_large_transcript(self):
        # The early call is far outside the tail window; only the last one counts.
        filler = [user("x" * 1000) for _ in range(400)]
        self.write_transcript([assistant(1, 1, 1)] + filler + [assistant(7, 70000, 0)])
        self.assertEqual(self.measure().stdout.strip(), "70007")

    def test_transcript_with_no_model_call_measures_zero(self):
        self.write_transcript([user("hello")])
        self.assertEqual(self.measure().stdout.strip(), "0")

    def test_missing_transcript_is_a_usage_error(self):
        out = self.measure(self.dir / "nope.jsonl")
        self.assertEqual(out.returncode, 2)
        self.assertEqual(out.stdout, "")
        self.assertIn("nope.jsonl", out.stderr)
        self.assertEqual(len(out.stderr.strip().splitlines()), 1)


class HookBase(Base):
    def setUp(self):
        super().setUp()
        self.project = self.dir / "project"
        self.project.mkdir()

    def hook(self, tokens, event="UserPromptSubmit", session="s1", env=None):
        self.write_transcript([assistant(0, tokens, 0)])
        payload = {"hook_event_name": event, "session_id": session,
                   "transcript_path": str(self.transcript)}
        full_env = {"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(self.project)}
        full_env.update(env or {})
        out = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(payload),
                             capture_output=True, text=True, env=full_env)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out


class WarningTest(HookBase):
    def test_below_the_first_threshold_says_nothing(self):
        self.assertEqual(self.hook(50000).stdout, "")

    def test_heads_up_is_said_once_per_session(self):
        first = self.hook(110000)
        self.assertIn("heads-up", first.stdout.lower())
        self.assertEqual(self.hook(115000).stdout, "")

    def test_wind_down_follows_the_heads_up_once(self):
        self.hook(110000)
        second = self.hook(160000)
        self.assertIn("wind-down", second.stdout.lower())
        self.assertEqual(self.hook(170000).stdout, "")

    def test_a_jump_past_both_lines_says_only_the_wind_down(self):
        out = self.hook(180000)
        self.assertIn("wind-down", out.stdout.lower())
        self.assertNotIn("heads-up", out.stdout.lower())
        self.assertEqual(self.hook(110000).stdout, "")

    def test_each_session_is_warned_on_its_own(self):
        self.hook(110000, session="a")
        self.assertIn("heads-up", self.hook(110000, session="b").stdout.lower())

    def test_a_compaction_rearms_the_warnings(self):
        # Context only falls back under the first line when the harness
        # compacted it; the refilled session deserves the warnings again.
        self.hook(110000)
        self.assertEqual(self.hook(40000).stdout, "")
        self.assertIn("heads-up", self.hook(110000).stdout.lower())

    def test_messages_carry_no_token_count(self):
        # A number in the message gets quoted back as fact; the instruction is the point.
        for tokens in (110000, 160000):
            out = self.hook(tokens, session=str(tokens))
            self.assertNotRegex(out.stdout, r"\d")

    def test_post_tool_use_answers_in_the_hook_json_shape(self):
        out = self.hook(110000, event="PostToolUse")
        body = json.loads(out.stdout)
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("heads-up", body["hookSpecificOutput"]["additionalContext"].lower())

    def test_thresholds_are_configurable(self):
        env = {"SESSION_CONTEXT_HEADS_UP": "500000", "SESSION_CONTEXT_WIND_DOWN": "700000"}
        self.assertEqual(self.hook(450000, env=env).stdout, "")
        self.assertIn("heads-up", self.hook(550000, env=env).stdout.lower())

    def test_a_bad_threshold_falls_back_to_the_defaults_with_one_line(self):
        out = self.hook(110000, env={"SESSION_CONTEXT_HEADS_UP": "lots"})
        self.assertIn("heads-up", out.stdout.lower())
        self.assertIn("SESSION_CONTEXT_HEADS_UP", out.stderr)
        self.assertEqual(len(out.stderr.strip().splitlines()), 1)

    def test_a_missing_transcript_is_silent_and_never_blocks(self):
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s",
                   "transcript_path": str(self.dir / "gone.jsonl")}
        out = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(payload),
                             capture_output=True, text=True,
                             env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(self.project)})
        self.assertEqual((out.returncode, out.stdout), (0, ""))


class ThrottleTest(HookBase):
    def test_tool_calls_are_checked_at_most_once_a_minute_per_session(self):
        # A session runs hundreds of tool calls; reading the transcript after
        # each one is wasted work when nothing can have changed much.
        self.hook(50000, event="PostToolUse")
        self.assertEqual(self.hook(110000, event="PostToolUse").stdout, "")

    def test_a_prompt_is_always_checked(self):
        self.hook(50000, event="PostToolUse")
        self.assertIn("heads-up", self.hook(110000).stdout.lower())

    def test_one_session_never_silences_another(self):
        # The gate is per session: a shared one let any session's check
        # mute every parallel session for the whole window.
        self.hook(50000, event="PostToolUse", session="a")
        out = self.hook(110000, event="PostToolUse", session="b")
        self.assertIn("heads-up", out.stdout.lower())

    def test_the_interval_is_configurable(self):
        env = {"SESSION_CONTEXT_CHECK_SECONDS": "0"}
        self.hook(50000, event="PostToolUse", env=env)
        self.assertIn("heads-up", self.hook(110000, event="PostToolUse", env=env).stdout.lower())


if __name__ == "__main__":
    unittest.main()
