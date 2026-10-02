# Wiring the hooks into Claude Code

Optional. The protocols in [protocol.md](protocol.md) work with no hooks at
all — an agent that has read the contract writes checkpoints because it was
asked to. The hooks exist for the moments discipline reliably fails: a
context that fills up while the agent is busy, a compaction nobody saw
coming, and a fresh session that never thinks to look for a resume.

The two resume scripts are plain bash and the context watch is one Python
file using only the standard library. All three never block and always
exit 0. Read them before wiring them; they write only inside your project
directory.

## Install

```bash
cp hooks/precompact-checkpoint.sh hooks/sessionstart-resume.sh hooks/context-watch.py /path/to/your/project/hooks/
chmod +x /path/to/your/project/hooks/*
echo '.checkpoints/' >> /path/to/your/project/.gitignore
```

The gitignore line matters: the archive holds raw session transcripts,
which can contain anything you and the agent discussed — keep it out of
version control. The context watch keeps its small per-session state in
`.checkpoints/sessions/` under the same rule.

Then add this to `.claude/settings.json` in that project (or to
`~/.claude/settings.json` to run everywhere):

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/hooks/precompact-checkpoint.sh\""
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/hooks/sessionstart-resume.sh\""
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/hooks/context-watch.py\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/hooks/context-watch.py\""
          }
        ]
      }
    ]
  }
}
```

An empty `matcher` runs the hook on every occurrence of the event. Narrow
it if you want to — `PreCompact` distinguishes manual from automatic
compaction, and `SessionStart` distinguishes a cold start from a resume —
but the honest default is to run on all of them, because the case you
would exclude is the one that bites.

The context watch is wired twice on purpose. `PostToolUse` catches a
session filling up during a long run of tool calls with nobody typing;
`UserPromptSubmit` catches it on your own turns. Both read the same
per-session state, so a warning said on one is not repeated on the other.

Restart Claude Code, then check `/hooks` to confirm all of them are registered.

## What each hook does

| Hook | Event | Effect |
|---|---|---|
| `precompact-checkpoint.sh` | `PreCompact` | Archives the current `CHECKPOINT.md` under `.checkpoints/`, copies the raw transcript to `.checkpoints/raw/`, and stamps `.checkpoints/last-compaction.txt`. |
| `sessionstart-resume.sh` | `SessionStart` | Prints `RESUME AVAILABLE` with the checkpoint's `updated:` date, plus a staleness warning when a compaction happened after the last save. |
| `context-watch.py` | `UserPromptSubmit`, `PostToolUse` | Reads the real context size from the transcript and tells the agent once per session at each of two thresholds: a heads-up to plan a checkpoint, then a wind-down to write it now. |

## How the context watch measures

It does not estimate. Every assistant row in the session transcript
carries the usage of the model call that produced it, and the context the
next call will re-read is that last call's input tokens plus its cache
reads plus its cache writes. The script reads the tail of the transcript,
takes the newest real call (skipping the zero-usage rows an API error
leaves behind), and sums those three. A transcript's byte size is a poor
stand-in: large tool output inflates the file without filling the context,
and a size alarm set for one session misses the next.

You can run the measurement by hand:

```bash
python3 hooks/context-watch.py --measure ~/.claude/projects/<project>/<session-id>.jsonl
```

The defaults are half and three quarters of the 200,000-token window most
models run with: half leaves room to finish the task in hand and
checkpoint at a natural boundary, three quarters still leaves room for a
full checkpoint before automatic compaction fires near the top. If your
sessions run on a larger window, raise both. Each warning is said once per
session; if a compaction brings the context back under the first line,
both warnings are armed again for the refilled session. The messages carry
no token count, because an agent quotes a number back as fact long after
it stopped being true.

## What the PreCompact hook deliberately does not do

It does not write the checkpoint. A shell script has no idea which
decisions mattered or which dead end cost an hour — that judgment is the
entire product, and it comes from the agent. The hook's job is narrower
and achievable: as long as the archive directory is writable, a compaction
never destroys state silently, and the breadcrumbs left behind let the
next session tell what it lost. If the archive cannot be created, the hook
says so on stderr and stays out of the way rather than blocking the session.

If no checkpoint exists when a compaction fires, the hook writes a marker
file saying so. An unmarked gap is the dangerous case: the next session
resumes from nothing and never learns there was something to resume.

## Other harnesses

The scripts read the harness's JSON event on stdin and use
`CLAUDE_PROJECT_DIR`, so they are Claude Code specific. The protocols are
not. On any other harness, put the contract in the system prompt and call
the checkpoint step manually at session end — you lose the automatic
safety net, not the pattern.

## Environment overrides

| Variable | Default | Meaning |
|---|---|---|
| `SESSION_CHECKPOINT_FILE` | `$CLAUDE_PROJECT_DIR/CHECKPOINT.md` | The front door checkpoint. |
| `SESSION_CHECKPOINT_ARCHIVE` | `$CLAUDE_PROJECT_DIR/.checkpoints` | Dated copies, raw transcripts, breadcrumb, context-watch state. |
| `SESSION_CONTEXT_HEADS_UP` | `100000` | Context tokens at which the heads-up is said. |
| `SESSION_CONTEXT_WIND_DOWN` | `150000` | Context tokens at which the wind-down is said; must be above the heads-up. |
