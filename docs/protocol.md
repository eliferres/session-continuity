# The two protocols

Writing state and reading it back are separate disciplines with separate
failure modes. Both are below; the file format they share is in
[anatomy.md](anatomy.md).

## Checkpoint (the write half)

### When to write

- **At session end**, always. This is the cheap one and the one that gets
  skipped.
- **Approaching the context ceiling**, before the harness decides for you.
  A checkpoint written one turn early beats a summary written after the
  loss, because at that point the material to summarize is already gone.
- **Before a deliberate compaction or reset.** Compaction is lossy by
  design; the checkpoint is what makes the loss survivable.
- **After finishing a milestone**, even mid-session. A checkpoint several
  ships behind resumes onto state that no longer exists, which is worse
  than no checkpoint at all — it is confidently wrong.

### How to write it

**Rewrite in full, every time.** Never append to a checkpoint and never
patch a section. An appended checkpoint accumulates contradictions, and
the reader has no way to tell which line is current. Rewriting forces a
pass over the whole state, which is where you notice that the thing you
called done is actually blocked.

**Archive a dated copy.** The front door (`CHECKPOINT.md`) always holds
the freshest state; every write also drops
`.checkpoints/YYYY-MM-DD-HHMM-<topic>.md`, which is never overwritten. The
archive is what lets you answer "what did we believe on the 11th" and what
protects a parallel session's state from being clobbered by yours.

**Overwrite guard.** If the front door currently holds a different arc's
state, confirm that arc has an archived copy before overwriting. An
overwrite may never cost depth.

**Read it back after writing.** Trusting a tool's success message is how
sessions discover, one session later, that the file was empty.

## Rehydrate (the read half)

### The sequence

1. **Read the checkpoint in full, first, in one read of a known path.**
   Not a skim, not a grep, not the first two sections. Hunting for state
   burns the context the checkpoint exists to save, and a partial read
   reproduces exactly the thin-summary failure this whole pattern exists
   to prevent.
2. **Follow references on demand.** Open the files, tickets, and configs
   the checkpoint names, and only those. The checkpoint is a router into
   the real sources, not a replacement for them.
3. **Verify before acting.** Any number, path, config value, or state
   claim you are about to act on gets checked against the live source
   first. The checkpoint was true when it was written; the world moved.
   A checkpoint that cites a green test suite is a claim, not a fact —
   run it.
4. **Restate, then continue.** Give a short recap: the objective, each
   workstream's state, the prioritized open threads. This is not
   ceremony — it proves the context actually loaded, and it is the cheap
   moment for a human to catch a wrong inheritance before work compounds
   on it.
5. **Continue at full depth**, using the real specifics from the
   checkpoint rather than a paraphrase of them.

### When the checkpoint is missing or stale

Say so plainly rather than resuming on bad state. In order: the newest
dated copy in `.checkpoints/`, then the raw transcript backups in
`.checkpoints/raw/`. Report which one you used. If nothing is usable, ask
— a guessed resume costs more than a cold start, because it looks
confident.

Staleness is mechanical, not a feeling: if `.checkpoints/last-compaction.txt`
is newer than the checkpoint's own modification time, work exists that the
checkpoint never saw. The SessionStart hook in `hooks/` prints that
warning automatically.
