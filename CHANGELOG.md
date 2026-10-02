# Changelog

## Unreleased

### Added
- Added `hooks/context-watch.py --measure TRANSCRIPT`, which prints how many tokens a session's context really holds, read from the last model call's usage in the transcript instead of estimated from the file's size.
- Added a context watch hook for `UserPromptSubmit` and `PostToolUse` that tells the agent once per session to plan a checkpoint (default 100,000 tokens) and once to write it now (default 150,000), both set with `SESSION_CONTEXT_HEADS_UP` and `SESSION_CONTEXT_WIND_DOWN`.
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
