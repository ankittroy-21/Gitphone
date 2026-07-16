# Changelog

All notable changes to GitPhone are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [1.5.6]

### Added

- Rate limiting on `/sync-file` endpoint via `slowapi`
- API key authentication (`X-Api-Key` header) for extension requests

## [1.5.0]

### Added

- Dynamic branching: create new feature branches on the fly from Telegram
- Automatic PR creation when committing to non-default branches

## [1.0.0] - Initial Release

### Added

- Real-time file sync from VS Code on every save event
- Telegram bot for commit workflow (`/files`, `/auth`, `/log`)
- GitHub Device Flow authentication (no PAT needed)
- `diff-match-patch` based diff engine