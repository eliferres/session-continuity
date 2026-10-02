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


if __name__ == "__main__":
    unittest.main()
