#!/usr/bin/env bash
# PreCompact hook: runs just before the harness compacts the context.
#
# A shell hook cannot write a good checkpoint - the depth comes from the
# agent, not from a script. What it can do is make sure a compaction never
# destroys state silently: archive whatever curated checkpoint exists, keep
# the raw transcript, and stamp when the compaction happened so the next
# session can tell whether the checkpoint predates the lost work.
#
# Wiring: see docs/hooks.md. Never blocks; always exits 0.
set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
CHECKPOINT="${SESSION_CHECKPOINT_FILE:-$PROJECT_DIR/CHECKPOINT.md}"
ARCHIVE="${SESSION_CHECKPOINT_ARCHIVE:-$PROJECT_DIR/.checkpoints}"

input=$(cat)
transcript=$(printf '%s' "$input" | python3 -c \
  'import json,sys;print(json.load(sys.stdin).get("transcript_path",""))' 2>/dev/null)
stamp=$(date +%Y-%m-%d-%H%M%S)

mkdir -p "$ARCHIVE/raw" 2>/dev/null || {
  echo "precompact-checkpoint: cannot create $ARCHIVE — nothing archived this compaction" >&2
  exit 0
}

if [ -f "$CHECKPOINT" ]; then
  cp "$CHECKPOINT" "$ARCHIVE/$stamp-checkpoint.md"
else
  # An unmarked gap is the dangerous case: the next session would resume
  # from nothing and never learn that a compaction ate the state.
  printf -- '---\ntype: session-checkpoint\nupdated: %s\n---\n\n# Compaction at %s with no checkpoint\n\nThe context was compacted and no curated checkpoint existed. Recover from the raw transcript in %s/raw if the work matters.\n' \
    "$(date +%Y-%m-%d)" "$stamp" "$ARCHIVE" > "$ARCHIVE/$stamp-no-checkpoint.md"
fi

if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  cp "$transcript" "$ARCHIVE/raw/$stamp.jsonl"
fi

# The breadcrumb the SessionStart hook compares against the checkpoint's
# own mtime to decide whether a resume would be running on stale state.
date +%s > "$ARCHIVE/last-compaction.txt"
exit 0
