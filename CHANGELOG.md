# Changelog

## Unreleased

### Added
- Added `hooks/context-watch.py --measure TRANSCRIPT`, which prints how many tokens a session's context really holds, read from the last model call's usage in the transcript instead of estimated from the file's size.
- Added a context watch hook for `UserPromptSubmit` and `PostToolUse` that tells the agent once per session to plan a checkpoint (default 100,000 tokens) and once to write it now (default 150,000), both set with `SESSION_CONTEXT_HEADS_UP` and `SESSION_CONTEXT_WIND_DOWN`.
- Added a per-session limit on how often the context watch checks after tool calls (once a minute by default, `SESSION_CONTEXT_CHECK_SECONDS`), so a busy session does not re-read its transcript on every call and parallel sessions never mute each other.
- Added a one-time notice when you come back to a large session after an idle hour (`SESSION_IDLE_SECONDS`) and its checkpoint is older than its last work: the agent is told to write the checkpoint before anything else.
- Added a paste-ready pickup prompt: the SessionStart hook prints the exact resume cue (`continue from CHECKPOINT.md`), and the protocol says to end every checkpoint reply with the cue, the objective and the next open thread in one fenced block.
- Added named checkpoints for parallel sessions: start a session with `SESSION_CHECKPOINT_NAME=billing` and it keeps `CHECKPOINT-billing.md`, and the hooks announce, archive and mark stale only that file. A session with no name is shown every checkpoint, newest first, each with its own resume cue.
- Added packaging, so `pipx install git+https://github.com/eliferres/session-continuity` installs a `checkpoint-lint` command with `--version`.

### Changed
- Changed the usage message to go to stderr, and gave usage and unreadable-path errors their own exit code 2, so a script can tell them apart from a checkpoint that failed the lint (1). A path that is not a file is reported on stderr and the remaining files are still linted.
- Changed what a file with an unclosed code fence reports: everything after the unclosed fence now counts as code, so a section that only had content after it is reported as empty. The fix is to close the fence.
- Changed the linter section of the README to say which checks reject a file and which one only warns.
- Changed the README so the case against compaction sits in one section and the file table is a short list.

### Fixed
- Fixed `--version` so it only counts as the first argument; `checkpoint-lint FILE.md --version` used to print the version and exit clean without linting.
- Fixed the relative-date check to skip inline code spans, so a checkpoint quoting `git log --since=yesterday` in a sentence no longer fails.
- Fixed the code fence exemption to follow the Markdown rules: fences of four or more backticks or tildes are now recognised, and a failure inside a file with fences reports the real line number.
- Fixed the usage line to name the command you actually ran, so the installed `checkpoint-lint` no longer points at a source file.
- Fixed the Quick start, which told you to paste a "contract" the README never had; it names the protocols section instead.
- Fixed the README so the five rules and the required sections render as text instead of sitting inside the template's code block.

## [1.1.0](https://github.com/eliferres/session-continuity/releases/tag/v1.1.0) - 2026-09-03

### Added
- Added macos-latest to the CI matrix alongside ubuntu-latest.

### Fixed
- Fixed the install block to gitignore `.checkpoints/` and say why: the archive holds raw session transcripts.
- Fixed the hook to report on stderr when it cannot create the archive, instead of exiting silently.
- Fixed the docs to claim only what the hook does when the archive is writable.

## [1.0.0](https://github.com/eliferres/session-continuity/releases/tag/v1.0.0) - 2026-08-31

First public release.
