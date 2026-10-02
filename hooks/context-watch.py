#!/usr/bin/env python3
"""Context watch: warn a session before its context runs out.

The size that matters is the one the next model call re-reads: the last
call's fresh input plus everything it read from and wrote to the prompt
cache. The harness records exactly that in the usage block of every
assistant row in the session transcript, so this reads it back instead of
estimating from the transcript's byte size. Byte size is a poor proxy: a
transcript full of large tool output can be many megabytes while the
context is modest, and the reverse, so a size-based alarm fires late or
never.

As a hook (no arguments, the harness's event JSON on stdin) it says two
things, each once per session: a heads-up at the first threshold, so the
agent plans a checkpoint at the next natural boundary, and a wind-down at
the second, so it writes the checkpoint before compaction decides for it.
On a prompt that arrives after a long idle gap, a session with a large
context and no checkpoint written since its last work is told once that
it owes one: the prompt cache has expired by then, so the turn re-reads
the whole context at full price, and the work since the last checkpoint
exists only in that context.

It never blocks and always exits 0; a hook that can stop the session is a
different tool with a different contract.

Usage:
    python3 hooks/context-watch.py < event.json        (as a hook)
    python3 hooks/context-watch.py --measure TRANSCRIPT.jsonl

Configuration, all optional:
    SESSION_CONTEXT_HEADS_UP    tokens for the heads-up   (default 100000)
    SESSION_CONTEXT_WIND_DOWN   tokens for the wind-down  (default 150000)
    SESSION_CONTEXT_CHECK_SECONDS  least time between two checks after
                                tool calls in one session (default 60)
    SESSION_IDLE_SECONDS        idle gap that makes a checkpoint owed
                                (default 3600)
    SESSION_CHECKPOINT_NAME     this session's name when parallel sessions
                                share a project; its checkpoint is
                                CHECKPOINT-<name>.md (default: no name, and
                                the newest checkpoint in the project counts)
    SESSION_CHECKPOINT_FILE     an explicit checkpoint path; wins over the name
    SESSION_CHECKPOINT_ARCHIVE  where per-session state is kept
                                (default $CLAUDE_PROJECT_DIR/.checkpoints)

Stdlib only. Exit codes for --measure: 0 measured, 2 usage or input error.
"""

from __future__ import annotations

import hashlib
import json
import os
import glob
import re
import sys
import time
from datetime import datetime
from typing import Optional

# The transcript is read backwards in chunks of this size and only as far
# as the last model call: a long session's transcript runs to tens of
# megabytes, but one tool result can also run past a megabyte, so no fixed
# tail is safe.
CHUNK_BYTES = 256 * 1024

# Half and three quarters of the 200,000-token window most models run
# with. Half leaves room to finish the task in hand and checkpoint at a
# boundary; three quarters still leaves room to write a full checkpoint
# before automatic compaction, which fires as the window nears full. On a
# larger window, raise both.
DEFAULT_HEADS_UP = 100_000
DEFAULT_WIND_DOWN = 150_000

# After a tool call the hook checks at most once a minute per session: a
# busy session makes hundreds of calls, and a minute of work rarely moves
# the context far enough to matter.
DEFAULT_CHECK_SECONDS = 60

# An hour outlasts the prompt cache under either of its lifetimes (five
# minutes by default, one hour extended), so by then the next turn is
# certain to re-read the whole context at full price.
DEFAULT_IDLE_SECONDS = 3600

# No token count in either message: a number in the agent's context gets
# quoted back as a fact long after it stopped being true, and the
# instruction is the whole point.
HEADS_UP = ("Context heads-up: this session's context is getting large. Plan a "
            "checkpoint at the next natural boundary. Nothing is blocked; keep "
            "working at full quality.")
WIND_DOWN = ("Context wind-down: compaction is getting close. Rewrite the "
             "checkpoint now, finish the step in flight, and start nothing new "
             "that would not survive a compaction.")
CHECKPOINT_OWED = ("Checkpoint owed: this session sat idle long enough for the prompt "
                   "cache to expire, with a large context and no checkpoint written "
                   "since its last work. Write the checkpoint before anything else. If "
                   "the old work is finished, a fresh session resumed from the "
                   "checkpoint is cheaper than continuing here.")


def _lines_backward(transcript: str):
    """Yield the transcript's lines as bytes, last line first."""
    with open(transcript, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        position, carry = fh.tell(), b""
        while position > 0:
            step = min(CHUNK_BYTES, position)
            position -= step
            fh.seek(position)
            pieces = (fh.read(step) + carry).split(b"\n")
            # The first piece may be the tail end of a longer line; it is
            # completed by the next chunk back.
            carry = pieces[0]
            for line in reversed(pieces[1:]):
                yield line
        if carry:
            yield carry


def _epoch(stamp: object) -> Optional[float]:
    """Seconds since the epoch for a row's ISO 8601 timestamp, or None."""
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def scan(transcript: str) -> tuple:
    """(usage of the last model call, time of the last work), either None.

    The last work is the newest assistant or system row's own timestamp.
    The file's modification time cannot stand in for it: the harness
    writes a new prompt into the transcript before the prompt hook runs,
    so the file always looks freshly touched at exactly the moment the
    idle gap is measured.
    """
    last_work = None
    for line in _lines_backward(transcript):
        if b'"assistant"' not in line and b'"system"' not in line:
            continue
        try:
            row = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("type") not in ("assistant", "system"):
            continue
        if last_work is None:
            last_work = _epoch(row.get("timestamp"))
        # A sidechain row is a subagent's own call, with its own context.
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        message = row.get("message") or {}
        # An API error (a rate limit, an overload) is written as an assistant
        # row with zero usage. It says nothing about the context, and read
        # as if it did, the session would look empty.
        if row.get("isApiErrorMessage") or message.get("model") == "<synthetic>":
            continue
        usage = message.get("usage")
        if usage:
            return usage, last_work
    return None, last_work


def tokens_from(usage: Optional[dict]) -> Optional[int]:
    """Tokens the call with this usage read as context; None for no call."""
    if usage is None:
        return None
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


def _setting(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    if re.fullmatch(r"[0-9]+", raw) and int(raw) >= minimum:
        return int(raw)
    print("context-watch: %s=%r is not a whole number of at least %d; using %d"
          % (name, raw, minimum, default), file=sys.stderr)
    return default


def thresholds() -> tuple:
    heads_up = _setting("SESSION_CONTEXT_HEADS_UP", DEFAULT_HEADS_UP)
    wind_down = _setting("SESSION_CONTEXT_WIND_DOWN", DEFAULT_WIND_DOWN)
    if heads_up >= wind_down:
        print("context-watch: the heads-up threshold must be below the wind-down "
              "threshold; using the defaults", file=sys.stderr)
        return DEFAULT_HEADS_UP, DEFAULT_WIND_DOWN
    return heads_up, wind_down


def state_dir() -> str:
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    archive = os.environ.get("SESSION_CHECKPOINT_ARCHIVE") or os.path.join(project, ".checkpoints")
    return os.path.join(archive, "sessions")


def _state_path(session_id: str) -> str:
    # The id names a file, so anything that is not a plain token is hashed
    # rather than trusted as a path component.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        session_id = hashlib.sha256(session_id.encode()).hexdigest()[:32]
    return os.path.join(state_dir(), session_id + ".json")


def load_state(session_id: str) -> dict:
    try:
        with open(_state_path(session_id)) as fh:
            state = json.load(fh)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(session_id: str, state: dict) -> None:
    path = _state_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, path)


def warning_for(tokens: int, heads_up: int, wind_down: int, state: dict) -> Optional[str]:
    """The warning this measurement earns, or None; updates state in place."""
    said = state.setdefault("said", [])
    if tokens < heads_up:
        # Only a compaction brings a session's context back under the first
        # line, and the refilled session should hear both warnings again.
        said.clear()
        return None
    # A session that jumps straight past both lines hears only the wind-down;
    # the heads-up would arrive too late to mean anything.
    level, message = ("wind-down", WIND_DOWN) if tokens >= wind_down else ("heads-up", HEADS_UP)
    if level in said:
        return None
    said.extend(name for name in ("heads-up", level) if name not in said)
    return message


def checkpoint_mtime() -> Optional[float]:
    """When this session's checkpoint was last written, or None if never.

    A named session owns CHECKPOINT-<name>.md and only that file counts,
    so one session's checkpoint never settles another's debt. A session
    with no name cannot tell which checkpoint is its own and takes the
    newest in the project.
    """
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    name = os.environ.get("SESSION_CHECKPOINT_NAME") or ""
    if name and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        print("context-watch: SESSION_CHECKPOINT_NAME=%r may hold only letters, digits, "
              "'.', '-' and '_'; ignored" % name, file=sys.stderr)
        name = ""
    if os.environ.get("SESSION_CHECKPOINT_FILE"):
        candidates = [os.environ["SESSION_CHECKPOINT_FILE"]]
    elif name:
        candidates = [os.path.join(project, "CHECKPOINT-%s.md" % name)]
    else:
        candidates = [os.path.join(project, "CHECKPOINT.md")] + [
            path for path in glob.glob(os.path.join(project, "CHECKPOINT-*.md"))
            if os.path.basename(path) != "CHECKPOINT-TEMPLATE.md"]
    times = [os.path.getmtime(path) for path in candidates if os.path.isfile(path)]
    return max(times) if times else None


def debt_for(tokens: int, heads_up: int, last_work: float, now: float,
             state: dict) -> Optional[str]:
    """The checkpoint-owed notice for a prompt after an idle gap, or None.

    `last_work` is when the session last did anything, from the
    transcript's own row timestamps. A session counts as large from the
    heads-up line. Said once per gap; updates state in place.
    """
    idle = _setting("SESSION_IDLE_SECONDS", DEFAULT_IDLE_SECONDS)
    if tokens < heads_up or now - last_work < idle:
        return None
    if state.get("debt_said_for") == last_work:
        return None
    saved = checkpoint_mtime()
    # No checkpoint at all is the plainest case of one owed.
    if saved is not None and saved >= last_work:
        return None
    state["debt_said_for"] = last_work
    return CHECKPOINT_OWED


def run_hook(event: dict) -> Optional[str]:
    transcript = event.get("transcript_path") or ""
    session_id = str(event.get("session_id") or "unknown")
    if not os.path.isfile(transcript):
        return None
    state = load_state(session_id)
    before = json.dumps(state, sort_keys=True)
    now = time.time()
    # A prompt is always checked: prompts are few, and the person typing is
    # the one who should see the warning. Only tool calls are rate-limited,
    # and per session, because one gate shared by every session let any
    # session's check mute all the others running in parallel.
    if event.get("hook_event_name") != "UserPromptSubmit":
        interval = _setting("SESSION_CONTEXT_CHECK_SECONDS", DEFAULT_CHECK_SECONDS, minimum=0)
        if now - float(state.get("checked_at", 0)) < interval:
            return None
        state["checked_at"] = now
    usage, last_work = scan(transcript)
    tokens = tokens_from(usage)
    if tokens is None:
        # Nothing measurable is not a compaction; leave the warnings armed
        # as they are.
        if json.dumps(state, sort_keys=True) != before:
            save_state(session_id, state)
        return None
    heads_up, wind_down = thresholds()
    messages = [warning_for(tokens, heads_up, wind_down, state)]
    if event.get("hook_event_name") == "UserPromptSubmit" and last_work is not None:
        messages.append(debt_for(tokens, heads_up, last_work, now, state))
    if json.dumps(state, sort_keys=True) != before:
        save_state(session_id, state)
    return "\n\n".join(m for m in messages if m) or None


def emit(event: dict, message: str) -> None:
    if event.get("hook_event_name") == "UserPromptSubmit":
        # On a prompt, plain stdout is what reaches the agent as context.
        print(message)
    else:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": event.get("hook_event_name") or "PostToolUse",
            "additionalContext": message}}))


def main(argv: list) -> int:
    if not argv:
        # Hook mode never fails the session: whatever goes wrong is one line
        # on stderr and exit 0.
        try:
            event = json.load(sys.stdin)
            message = run_hook(event) if isinstance(event, dict) else None
            if message:
                emit(event, message)
        except Exception as exc:  # noqa: BLE001 - a broken hook must not break the session
            print("context-watch: %s" % exc, file=sys.stderr)
        return 0
    if len(argv) == 2 and argv[0] == "--measure":
        try:
            print(tokens_from(scan(argv[1])[0]) or 0)
        except OSError as exc:
            print("context-watch: cannot read %s: %s" % (argv[1], exc.strerror), file=sys.stderr)
            return 2
        return 0
    print("usage: context-watch.py [--measure TRANSCRIPT.jsonl] (no arguments: hook event on stdin)",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
