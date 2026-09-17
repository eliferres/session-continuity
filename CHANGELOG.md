# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Added packaging, so `pipx install git+https://github.com/eliferres/session-continuity` installs a `checkpoint-lint` command with `--version`.

### Changed
- Changed the README so the case against compaction sits in one section and the file table is a short list.

### Fixed
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
