#!/usr/bin/env python3
"""Context watch: measure how full a session's context really is.

The size that matters is the one the next model call re-reads: the last
call's fresh input plus everything it read from and wrote to the prompt
cache. The harness records exactly that in the usage block of every
assistant row in the session transcript, so this reads it back instead of
estimating from the transcript's byte size. Byte size is a poor proxy: a
transcript full of large tool output can be many megabytes while the
context is modest, and the reverse, so a size-based alarm fires late or
never.

Usage:
    python3 hooks/context-watch.py --measure TRANSCRIPT.jsonl

Stdlib only. Exit codes: 0 measured, 2 usage or input error.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

# Only the tail is read: the last model call is near the end, and a long
# session's transcript runs to tens of megabytes.
TAIL_BYTES = 256 * 1024


def _last_call_usage(lines: list) -> Optional[dict]:
    for line in reversed(lines):
        if '"assistant"' not in line or '"usage"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue  # the first line of the tail is usually cut mid-row
        message = row.get("message") or {}
        # An API error (a rate limit, an overload) is written as an assistant
        # row with zero usage. It says nothing about the context, and read
        # as if it did, the session would look empty.
        if row.get("isApiErrorMessage") or message.get("model") == "<synthetic>":
            continue
        usage = message.get("usage")
        if usage:
            return usage
    return None


def context_tokens(transcript: str) -> int:
    """Tokens the last model call in the transcript read as context.

    Returns 0 when the transcript holds no model call yet.
    """
    size = os.path.getsize(transcript)
    with open(transcript, "rb") as fh:
        fh.seek(max(0, size - TAIL_BYTES))
        lines = fh.read().decode("utf-8", "replace").splitlines()
    usage = _last_call_usage(lines)
    if usage is None:
        return 0
    # A turn that made several model calls reports their sum at the top
    # level, which runs about double the real context; the last message
    # iteration is the one the next call builds on.
    iterations = usage.get("iterations")
    if isinstance(iterations, list):
        calls = [i for i in iterations if isinstance(i, dict) and i.get("type") == "message"]
        if calls:
            usage = calls[-1]
    return (usage.get("input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0))


def main(argv: list) -> int:
    if len(argv) == 2 and argv[0] == "--measure":
        try:
            print(context_tokens(argv[1]))
        except OSError as exc:
            print("context-watch: cannot read %s: %s" % (argv[1], exc.strerror), file=sys.stderr)
            return 2
        return 0
    print("usage: context-watch.py --measure TRANSCRIPT.jsonl", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
