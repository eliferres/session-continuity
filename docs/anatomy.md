# Checkpoint file anatomy

The wire format. This file is the source of truth; `CHECKPOINT-TEMPLATE.md`
is the blank you copy, and `tools/checkpoint_lint.py` enforces the parts a
machine can check.

```markdown
---
type: session-checkpoint
updated: YYYY-MM-DD          # absolute, always; the linter rejects anything else
---

# Checkpoint — <one-line arc name>

<Two or three lines telling the reader to read the whole file before
acting, and that everything below is exact rather than remembered.>

## Objective
The outcome the work serves, in one or two lines. Not the current task —
the reason the task is worth doing.

## State
Per workstream: done and verified / in flight / blocked. Exact files,
commands, and observed output. A workstream with no evidence behind it is
"in flight", never "done".

## Decisions and why
Every ruling made, each with the reasoning that produced it, including the
alternatives rejected. The conclusion alone invites relitigation; the
argument is what closes the question.

## Open threads
Next actions in priority order, each concrete enough to act on cold.
Blocked items name the blocker and what clears it.

## Gotchas and dead ends
Approaches tried and rejected with a one-line why each, traps hit and
their fix, and anything that looks wrong but is correct.
```

## The five rules that make it work

1. **Absolute dates, never relative ones.** "Fixed yesterday" is
   unreadable a week later. `2026-03-11` is readable forever.
2. **Verbatim specifics.** Paths, commands, identifiers, numbers, and
   error strings are copied, not paraphrased. Paraphrase is the exact
   thing compaction already does, and it is what loses the state.
3. **Written for zero context.** Assume the reader has never seen the
   project. If a sentence only makes sense to someone who was there, it
   does not belong in a checkpoint.
4. **Every section survives, even when empty-ish.** A missing section
   reads as forgotten; a section saying "none" reads as answered.
5. **Depth, not bulk.** Write what a fresh session cannot re-derive from
   the repository and its history. Never paste transcripts.

## Required sections

`Objective`, `State`, `Decisions`, `Open threads`, `Gotchas`. The linter
matches on prefix, so `## Decisions and why` and `## Gotchas and dead ends`
satisfy the requirement while reading like prose.
