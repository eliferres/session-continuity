#!/usr/bin/env bash
# PreCompact hook: runs just before the harness compacts the context.
#
# A shell hook cannot write a good checkpoint - the depth comes from the
# agent, not from a script. What it can do is make sure a compaction never
# destroys state silently: archive whatever curated checkpoint exists, keep
# the raw transcript, and stamp when the compaction happened so the next
# session can tell whether the checkpoint predates the lost work.
#
# A session started with SESSION_CHECKPOINT_NAME=billing owns
# CHECKPOINT-billing.md and archives only that file, so parallel sessions
# never touch each other's state. A session with no name cannot know which
# checkpoint is its own, so it archives all of them.
#
# Wiring: see docs/hooks.md. Never blocks; always exits 0.
set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
ARCHIVE="${SESSION_CHECKPOINT_ARCHIVE:-$PROJECT_DIR/.checkpoints}"
NAME="${SESSION_CHECKPOINT_NAME:-}"

# The name becomes part of a file name, so it may not carry a path.
if [ -n "$NAME" ] && ! printf '%s' "$NAME" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]*$'; then
  echo "precompact-checkpoint: SESSION_CHECKPOINT_NAME='$NAME' may hold only letters, digits, '.', '-' and '_'; ignored" >&2
  NAME=""
fi

if [ -n "${SESSION_CHECKPOINT_FILE:-}" ]; then
  checkpoints="$SESSION_CHECKPOINT_FILE"
elif [ -n "$NAME" ]; then
  checkpoints="$PROJECT_DIR/CHECKPOINT-$NAME.md"
else
  checkpoints=$(ls "$PROJECT_DIR"/CHECKPOINT.md "$PROJECT_DIR"/CHECKPOINT-*.md 2>/dev/null \
    | grep -v '/CHECKPOINT-TEMPLATE\.md$')
fi

input=$(cat)
transcript=$(printf '%s' "$input" | python3 -c \
  'import json,sys;print(json.load(sys.stdin).get("transcript_path",""))' 2>/dev/null)
stamp=$(date +%Y-%m-%d-%H%M%S)

mkdir -p "$ARCHIVE/raw" 2>/dev/null || {
  echo "precompact-checkpoint: cannot create $ARCHIVE — nothing archived this compaction" >&2
  exit 0
}

archived=0
while IFS= read -r checkpoint; do
  [ -f "$checkpoint" ] || continue
  base=$(basename "$checkpoint")
  case "$base" in
    CHECKPOINT-*.md) key=${base#CHECKPOINT-}; key=${key%.md} ;;
    *) key=$NAME ;;
  esac
  cp "$checkpoint" "$ARCHIVE/$stamp-${key:+$key-}checkpoint.md" && archived=1
done <<< "$checkpoints"

if [ "$archived" -eq 0 ]; then
  # An unmarked gap is the dangerous case: the next session would resume
  # from nothing and never learn that a compaction ate the state.
  printf -- '---\ntype: session-checkpoint\nupdated: %s\n---\n\n# Compaction at %s with no checkpoint\n\nThe context was compacted and no curated checkpoint existed. Recover from the raw transcript in %s/raw if the work matters.\n' \
    "$(date +%Y-%m-%d)" "$stamp" "$ARCHIVE" > "$ARCHIVE/$stamp-${NAME:+$NAME-}no-checkpoint.md"
fi

# The copy is labelled so two sessions compacting in the same second never
# share a file: the session's name, else its checkpoint file's own name
# reduced to characters that are safe in a file name.
label=$NAME
if [ -z "$label" ] && [ -n "${SESSION_CHECKPOINT_FILE:-}" ]; then
  label=$(printf '%s' "$(basename "$SESSION_CHECKPOINT_FILE" .md)" | tr -c 'A-Za-z0-9._-' '-')
fi
if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  cp "$transcript" "$ARCHIVE/raw/$stamp${label:+-$label}.jsonl"
fi

# The breadcrumb the SessionStart hook compares against the checkpoint's
# own mtime to decide whether a resume would be running on stale state. A
# named session leaves its own, so it marks only its own checkpoint stale.
date +%s > "$ARCHIVE/last-compaction${NAME:+-$NAME}.txt"
exit 0
