# Contributing

Welcome things:

- New linter checks, each with a test and a one-line why.
- Ports of the protocols to other agent harnesses (a `ports/` doc, not a
  framework).
- Real checkpoints, redacted, that the format handled badly.
- Fixes to anything the README claims that turns out not to be true.

Ground rules: the linter stays stdlib-only, the format stays plain
Markdown a human can write by hand, and every change keeps
`python3 -m unittest discover -s tests` green. A change to the format
also updates `docs/anatomy.md` (the source of truth), the block quoted in
the README, and `CHECKPOINT-TEMPLATE.md`, in the same pull request.

Format changes belong in an issue before a pull request. The section list
is deliberately short. Every added section is one more thing an agent
skips under context pressure, which is precisely when the checkpoint
matters most.
