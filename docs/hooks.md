# Wiring the hooks into Claude Code

Optional. The protocols in [protocol.md](protocol.md) work with no hooks at
all — an agent that has read the contract writes checkpoints because it was
asked to. The hooks exist for the two moments discipline reliably fails:
a compaction nobody saw coming, and a fresh session that never thinks to
look for a resume.

Both scripts are plain bash, never block, and always exit 0. Read them
before wiring them; they write only inside your project directory.

## Install

```bash
cp hooks/precompact-checkpoint.sh hooks/sessionstart-resume.sh /path/to/your/project/hooks/
chmod +x /path/to/your/project/hooks/*.sh
echo '.checkpoints/' >> /path/to/your/project/.gitignore
```

The gitignore line matters: the archive holds raw session transcripts,
which can contain anything you and the agent discussed — keep it out of
version control.

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
    ]
  }
}
```

An empty `matcher` runs the hook on every occurrence of the event. Narrow
it if you want to — `PreCompact` distinguishes manual from automatic
compaction, and `SessionStart` distinguishes a cold start from a resume —
but the honest default is to run on all of them, because the case you
would exclude is the one that bites.

Restart Claude Code, then check `/hooks` to confirm both are registered.

## What each hook does

| Hook | Event | Effect |
|---|---|---|
| `precompact-checkpoint.sh` | `PreCompact` | Archives the current `CHECKPOINT.md` under `.checkpoints/`, copies the raw transcript to `.checkpoints/raw/`, and stamps `.checkpoints/last-compaction.txt`. |
| `sessionstart-resume.sh` | `SessionStart` | Prints `RESUME AVAILABLE` with the checkpoint's `updated:` date, plus a staleness warning when a compaction happened after the last save. |

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
| `SESSION_CHECKPOINT_ARCHIVE` | `$CLAUDE_PROJECT_DIR/.checkpoints` | Dated copies, raw transcripts, breadcrumb. |
