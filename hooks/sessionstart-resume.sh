#!/usr/bin/env bash
# SessionStart hook: announces that a resume is available.
#
# The point is that resuming costs the agent nothing to discover. Without
# this line a fresh session starts blank and only rehydrates if the human
# remembers to ask, which is exactly when they are least likely to.
#
# Parallel sessions in one project each keep their own checkpoint: a
# session started with SESSION_CHECKPOINT_NAME=billing writes
# CHECKPOINT-billing.md and is shown only that file. A session with no name
# is shown every checkpoint in the project, newest first, each with its
# own resume cue, so the person picks one rather than the agent blending
# two arcs.
#
# Wiring: see docs/hooks.md. Never blocks; always exits 0.
set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
ARCHIVE="${SESSION_CHECKPOINT_ARCHIVE:-$PROJECT_DIR/.checkpoints}"
NAME="${SESSION_CHECKPOINT_NAME:-}"

# The name becomes part of a file name, so it may not carry a path.
if [ -n "$NAME" ] && ! printf '%s' "$NAME" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]*$'; then
  echo "sessionstart-resume: SESSION_CHECKPOINT_NAME='$NAME' may hold only letters, digits, '.', '-' and '_'; ignored" >&2
  NAME=""
fi

if [ -n "${SESSION_CHECKPOINT_FILE:-}" ]; then
  checkpoints="$SESSION_CHECKPOINT_FILE"
elif [ -n "$NAME" ]; then
  checkpoints="$PROJECT_DIR/CHECKPOINT-$NAME.md"
else
  # The blank template lives beside real checkpoints in some projects and
  # is never something to resume.
  checkpoints=$(ls -t "$PROJECT_DIR"/CHECKPOINT.md "$PROJECT_DIR"/CHECKPOINT-*.md 2>/dev/null \
    | grep -v '/CHECKPOINT-TEMPLATE\.md$')
fi

found=0
while IFS= read -r checkpoint; do
  [ -f "$checkpoint" ] && found=$((found + 1))
done <<< "$checkpoints"
if [ "$found" -eq 0 ]; then
  # A named session's agent otherwise only knows the default file name and
  # would write into the shared CHECKPOINT.md on its first checkpoint.
  if [ -n "$NAME" ] && [ -z "${SESSION_CHECKPOINT_FILE:-}" ]; then
    echo "This session's checkpoint file is CHECKPOINT-$NAME.md (SESSION_CHECKPOINT_NAME=$NAME). Write checkpoints there, not to CHECKPOINT.md."
  fi
  exit 0
fi

if [ "$found" -gt 1 ]; then
  echo "RESUME AVAILABLE - $found checkpoints, one per parallel session, newest first. Resume the one the person names, never a blend."
fi

# The time of the last compaction that could have outrun this checkpoint:
# its own session's, or one from a session with no name, which could have
# been working on anything.
last_compaction() { # <name or empty>
  local newest=0 file value
  for file in "$ARCHIVE/last-compaction.txt" ${1:+"$ARCHIVE/last-compaction-$1.txt"}; do
    value=$(cat "$file" 2>/dev/null || echo 0)
    [ "$value" -gt "$newest" ] 2>/dev/null && newest=$value
  done
  echo "$newest"
}

while IFS= read -r checkpoint; do
  [ -f "$checkpoint" ] || continue
  updated=$(sed -n 's/^updated:[[:space:]]*//p' "$checkpoint" | head -1)
  echo "RESUME AVAILABLE - $checkpoint (updated: ${updated:-unknown})"
  # One exact cue line, so the agent hands the person the same words every
  # time instead of improvising them; protocol.md says where it goes.
  echo "Resume cue: continue from ${checkpoint#"$PROJECT_DIR"/}"

  base=$(basename "$checkpoint")
  case "$base" in
    CHECKPOINT-*.md) key=${base#CHECKPOINT-}; key=${key%.md} ;;
    *) key=$NAME ;;
  esac
  compacted=$(last_compaction "$key")
  # A compaction after the last save means work exists that the checkpoint
  # never saw - resuming from it would quietly lose that stretch.
  saved=$(date -r "$checkpoint" +%s 2>/dev/null || echo 0)
  if [ "$compacted" -gt "$saved" ] 2>/dev/null; then
    echo "WARNING: a compaction happened after this checkpoint was written."
    echo "Newer work may only exist in $ARCHIVE/raw."
  fi
done <<< "$checkpoints"

echo "Read it in full before acting. Verify anything it cites against the live source."
exit 0
