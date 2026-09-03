# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Fixed
- Fixed the install block to gitignore `.checkpoints/` and say why: the archive holds raw session transcripts.
- Fixed the hook to report on stderr when it cannot create the archive, instead of exiting silently.
- Fixed the docs to claim only what the hook does when the archive is writable.

## [1.0.0](https://github.com/eliferres/session-continuity/releases/tag/v1.0.0) - 2026-08-31

First public release.
