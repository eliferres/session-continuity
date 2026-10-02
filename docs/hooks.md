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
cp hooks/precompact-checkpoint.sh hooks/sessionstart-resume.sh \
   hooks/context-watch.py /path/to/your/project/hooks/
chmod +x /path/to/your/project/hooks/*
echo '.checkpoints/' >> /path/to/your/project/.gitignore
```

The gitignore line matters: the archive holds raw session transcripts,
which can contain anything you and the agent discussed — keep it out of
version control. The context watch keeps its small per-session state in
`.checkpoints/sessions/` under the same rule, and deletes any of it left
untouched for 30 days, so the folder does not grow by one file per
session forever.

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
A warning is said only by the run that creates its marker file in
`.checkpoints/sessions/`, an exclusive create the filesystem grants once,
so hooks on parallel tool calls that fire at the same moment still say it
once.
After a tool call the check runs at most once a minute per session, so a
busy session does not re-read its transcript hundreds of times; a prompt
is always checked. The limit is kept per session because one shared limit
lets whichever session checked last mute every other session running in
parallel, which is exactly when context fills fastest.

Restart Claude Code, then check `/hooks` to confirm all of them are registered.

## What each hook does

| Hook | Event | Effect |
|---|---|---|
| `precompact-checkpoint.sh` | `PreCompact` | Archives the current `CHECKPOINT.md` under `.checkpoints/`, copies the raw transcript to `.checkpoints/raw/`, and stamps `.checkpoints/last-compaction.txt`. |
| `sessionstart-resume.sh` | `SessionStart` | Prints `RESUME AVAILABLE` with the checkpoint's `updated:` date and the exact resume cue (`continue from CHECKPOINT.md`), plus a staleness warning when a compaction happened after the last save. |
| `context-watch.py` | `UserPromptSubmit`, `PostToolUse` | Reads the real context size from the transcript and tells the agent once per session at each of two thresholds: a heads-up to plan a checkpoint, then a wind-down to write it now. |

## How the context watch measures

It does not estimate. Every assistant row in the session transcript
carries the usage of the model call that produced it, and the context the
next call will re-read is that last call's input tokens plus its cache
reads plus its cache writes. The script reads the transcript backwards,
in chunks, only as far as the newest real call (skipping the zero-usage
rows an API error leaves behind and a subagent's sidechain rows), and sums
those three. A fixed tail is not enough, because a single tool result can
run past a megabyte. When no call can be found the watch says nothing and
keeps its warnings as they were, rather than reading the silence as a
compaction. A transcript's byte size is a poor stand-in: large tool output
inflates the file without filling the context, and a size alarm set for
one session misses the next.

You can run the measurement by hand:

```bash
python3 hooks/context-watch.py --measure ~/.claude/projects/<project>/<session-id>.jsonl
```

It prints the token count and exits 0; a transcript with no model call
yet prints 0. Damaged rows are skipped in favour of the newest readable
call. A path it cannot read, or a file that is not a session transcript,
is one line on stderr and exit 2.

The defaults are half and three quarters of the 200,000-token window most
models run with: half leaves room to finish the task in hand and
checkpoint at a natural boundary, three quarters still leaves room for a
full checkpoint before automatic compaction fires near the top. If your
sessions run on a larger window, raise both. Each warning is said once per
session; if a compaction brings the context back under the first line,
both warnings are armed again for the refilled session. The messages carry
no token count, because an agent quotes a number back as fact long after
it stopped being true.

## A checkpoint owed after an idle gap

The costliest moment in a long session is the first prompt after a
break. The prompt cache has expired, so that turn re-reads the whole
context at full price, and everything since the last checkpoint still
lives only in that context. When a prompt arrives after the session has
been quiet for `SESSION_IDLE_SECONDS` (an hour by default, longer than
the prompt cache lives under either of its settings), the context is past
the heads-up line, and the checkpoint file has not been written since the
session's last work, the watch tells the agent once that a checkpoint is
owed and should come first. A checkpoint written after the last work
settles it; the next idle gap is judged on its own. The session's last work
is the timestamp on its newest assistant or system row, not the
transcript file's modification time: the harness writes your new prompt
into the transcript before the hook runs, so the file always looks fresh
at the moment the gap is measured.

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

## Parallel sessions

Two sessions in one project each rewrite their checkpoint in full, so a
shared `CHECKPOINT.md` holds whichever wrote last and the other arc is
gone. Start each session with its own name:

```bash
SESSION_CHECKPOINT_NAME=billing claude
SESSION_CHECKPOINT_NAME=search claude
```

The hooks inherit the variable from the session's environment, so each
session's hooks work on its own file only:

- `sessionstart-resume.sh` announces only `CHECKPOINT-billing.md`, and
  its resume cue names that file. Before that file exists, it tells the
  agent the file name to write, which the agent would otherwise not
  know. A session with no name is shown every checkpoint in the project,
  newest first, each with its own cue, and the person picks one.
- `precompact-checkpoint.sh` archives only that session's checkpoint, as
  `.checkpoints/<time>-billing-checkpoint.md`, copies its transcript to
  `.checkpoints/raw/<time>-billing.jsonl`, and leaves its own
  breadcrumb, `last-compaction-billing.txt`, so a compaction in one
  session never marks another's checkpoint stale. A session with no name
  archives every checkpoint and marks them all, because it cannot know
  which one it was working on.
- `context-watch.py` counts a checkpoint owed as settled only by that
  session's own file.

`CHECKPOINT-TEMPLATE.md` is never treated as a checkpoint, so the blank
can sit in the project root.

## Other harnesses

The scripts read the harness's JSON event on stdin and use
`CLAUDE_PROJECT_DIR`, so they are Claude Code specific. The protocols are
not. On any other harness, put the contract in the system prompt and call
the checkpoint step manually at session end — you lose the automatic
safety net, not the pattern.

## Environment overrides

| Variable | Default | Meaning |
|---|---|---|
| `SESSION_CHECKPOINT_NAME` | none | This session's name when several share a project; its checkpoint is `CHECKPOINT-<name>.md`. Letters, digits, `.`, `-` and `_` only. |
| `SESSION_CHECKPOINT_FILE` | none | An explicit checkpoint path that wins over the name. Unset, a named session uses `$CLAUDE_PROJECT_DIR/CHECKPOINT-<name>.md` and a session with no name uses every checkpoint in the project, `CHECKPOINT.md` included. Set without a name, the file's own name labels the raw transcript copy. |
| `SESSION_CHECKPOINT_ARCHIVE` | `$CLAUDE_PROJECT_DIR/.checkpoints` | Dated copies, raw transcripts, breadcrumb, context-watch state. |
| `SESSION_CONTEXT_HEADS_UP` | `100000` | Context tokens at which the heads-up is said. |
| `SESSION_CONTEXT_WIND_DOWN` | `150000` | Context tokens at which the wind-down is said; must be above the heads-up. |
| `SESSION_IDLE_SECONDS` | `3600` | Quiet time after which a large session with no fresh checkpoint is told it owes one. |
| `SESSION_CONTEXT_CHECK_SECONDS` | `60` | Least time between two checks after tool calls in one session; `0` checks after every call. |
