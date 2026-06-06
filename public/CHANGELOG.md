# Changelog

## v1.0.0 — 2026-06-05

### MVP Release (Hackathon)

**Backend:**
- POST /register — GitHub token validation + user registration
- POST /sync-file — Diff storage in Supabase staged_files
- GET /version — Schema version check endpoint
- GET /health — Health check for Render + uptime monitors
- POST /webhook — Telegram bot webhook receiver
- /start command — New user onboarding via Telegram conversation
- /files command — File selection with inline keyboard toggles
- /log command — Recent commit history (last 10)
- /status command — Connection status and repo info
- /help command — All commands listed
- /cancel command — Cancel any in-progress operation
- Commit Now flow — SHA conflict check + PyGithub commit
- Force Commit option — Overwrite on conflict

**VS Code Extension:**
- Setup panel (Webview) with 5-field form and validation
- File watcher (onDidSaveTextDocument)
- CRLF normalization (Windows compatibility)
- Binary file detection (extension + null-byte scan)
- 10MB hard size limit with inline warning
- Diff computation using npm `diff` library
- Local cache (globalState) — last-committed SHA/content per file
- Status bar — staged count, syncing, error, disconnected states
- Schema version check on startup
- Health check on startup

**Database:**
- users table with telegram_id isolation
- staged_files table with unique-pending index
- commit_log audit table

**Infrastructure:**
- Render deployment (render.yaml)
- Single Supabase instance (MVP simplification)
- Webhook mode (no sleeping on Telegram messages)
