#!/usr/bin/env bash
# SessionStart hook: announces that a resume is available.
#
# The point is that resuming costs the agent nothing to discover. Without
# this line a fresh session starts blank and only rehydrates if the human
# remembers to ask, which is exactly when they are least likely to.
#
# Wiring: see docs/hooks.md. Never blocks; always exits 0.
set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
CHECKPOINT="${SESSION_CHECKPOINT_FILE:-$PROJECT_DIR/CHECKPOINT.md}"
ARCHIVE="${SESSION_CHECKPOINT_ARCHIVE:-$PROJECT_DIR/.checkpoints}"

[ -f "$CHECKPOINT" ] || exit 0

updated=$(sed -n 's/^updated:[[:space:]]*//p' "$CHECKPOINT" | head -1)
echo "RESUME AVAILABLE - $CHECKPOINT (updated: ${updated:-unknown})"
echo "Read it in full before acting. Verify anything it cites against the live source."

breadcrumb="$ARCHIVE/last-compaction.txt"
if [ -f "$breadcrumb" ]; then
  compacted=$(cat "$breadcrumb" 2>/dev/null || echo 0)
  # A compaction after the last save means work exists that the checkpoint
  # never saw - resuming from it would quietly lose that stretch.
  saved=$(date -r "$CHECKPOINT" +%s 2>/dev/null || echo 0)
  if [ "$compacted" -gt "$saved" ] 2>/dev/null; then
    echo "WARNING: a compaction happened after this checkpoint was written."
    echo "Newer work may only exist in $ARCHIVE/raw."
  fi
fi
exit 0
