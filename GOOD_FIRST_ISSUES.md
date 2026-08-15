# 🐣 Good First Issues — GitPhone

Welcome, contributor! This document lists beginner-friendly issues you can pick up, implement, and open a Pull Request for. Each issue includes a **title**, **explanation of the problem**, and a **step-by-step guide on how to implement the fix**.

> **Before you start:**
> - Comment on the issue (or DM the maintainer) so no one else is working on the same thing.
> - Fork the repo → create a feature branch → open a PR against `main`.
> - Every PR needs the `ECSoC26` label to be scored.
> - Backend changes: run `ruff check backend/` before pushing.
> - Extension changes: run `npx tsc --noEmit` before pushing.

---

## Issue #1 — Update `/help` command to list all available bot commands

**Labels:** `good-first-issue` · `ECSoC26-L1` · `bot` · `documentation`

### Problem
The `/help` handler in `backend/bot.py` exists and is registered, but the actual help text shown to the user does not include newer commands like `/unstage`, `/clear`, and `/preview`. New users may not know these exist at all.

### Where to look
- File: `backend/bot.py` — search for `help_handler`

### How to implement
1. Open `backend/bot.py` and search for the function `help_handler`.
2. Find the message text it sends and update it so **every** bot command is listed with a one-line description. Include:
   - `/start` — Register or welcome back
   - `/auth` — Link your GitHub account (Device Flow)
   - `/files` — View and select staged files to commit
   - `/repo` — Show your active repository
   - `/branch` — Switch or create branches
   - `/preview` — Preview diffs before committing
   - `/log` — View your recent GitPhone commit history
   - `/status` — Check connection & system health
   - `/unstage` — Remove a specific file from the staged list
   - `/clear` — Wipe your entire remote staging area
   - `/cancel` — Cancel the current operation
   - `/help` — Show this help message
3. Format the reply using Markdown so command names appear in `code` style for readability.
4. Test it by reading through the code to confirm every command name appears correctly.

### Acceptance criteria
- All 12 commands are listed.
- The message is easy to read on a mobile screen (short lines).
- No existing behavior is broken.

---

## Issue #2 — Add input validation for the `filepath` field in the sync endpoint

**Labels:** `good-first-issue` · `ECSoC26-L1` · `backend` · `security`

### Problem
In `backend/routes/sync.py`, the `POST /sync-file` endpoint receives a `filepath` field. Currently there is **no validation** to prevent suspicious patterns like `../../etc/passwd` or absolute paths. While data goes to Supabase (not disk), it is good hygiene to reject bad inputs early.

### Where to look
- File: `backend/routes/sync.py` — the `sync_file()` function
- File: `backend/models/staged.py` — the `SyncFilePayload` Pydantic model

### How to implement
1. Open `backend/models/staged.py` and find the `SyncFilePayload` class.
2. Add a Pydantic `field_validator` on the `filepath` field.
3. Inside the validator, raise a `ValueError` if any of the following are true:
   - The path starts with `/` or `\` (absolute path)
   - The path contains `..` (directory traversal)
   - The path is longer than 500 characters
4. Return the stripped filepath string on success.

### Example skeleton
```python
from pydantic import field_validator

class SyncFilePayload(BaseModel):
    filepath: str

    @field_validator("filepath")
    @classmethod
    def validate_filepath(cls, v: str) -> str:
        v = v.strip()
        if v.startswith(("/", "\\")):
            raise ValueError("Absolute paths are not allowed")
        if ".." in v:
            raise ValueError("Path traversal is not allowed")
        if len(v) > 500:
            raise ValueError("Filepath is too long")
        return v
```

### Acceptance criteria
- A request with `filepath: "../../etc/passwd"` returns HTTP 422.
- A request with a normal path like `src/main.py` still works.
- `ruff check backend/` passes cleanly.

---

## Issue #3 — Status bar tooltip should show the backend URL

**Labels:** `good-first-issue` · `ECSoC26-L1` · `extension` · `ux`

### Problem
In `extension/src/statusBar.ts`, the `setConnected()` tooltip says `"GitPhone: N file(s) staged. Click to open panel."` but does **not** show which backend server the extension is connected to. If a user has a misconfigured URL, there is no quick way to see it without opening the setup panel.

### Where to look
- File: `extension/src/statusBar.ts` — the `setConnected()` function
- File: `extension/src/config.ts` — `getBackendUrl()` returns the current backend URL

### How to implement
1. Open `extension/src/statusBar.ts`.
2. Import `getBackendUrl` from `./config` at the top of the file.
3. In `setConnected()`, update the `.tooltip` string to include the URL:
   ```
   GitPhone: 3 file(s) staged | Backend: https://gitphone.onrender.com — Click to open panel.
   ```
4. Also update `setDisconnected()` to include the URL so the user knows what URL is failing.

### Example change
```typescript
import { getBackendUrl } from './config';

// In setConnected():
_statusBar.tooltip = `GitPhone: ${stagedCount} file(s) staged | Backend: ${getBackendUrl()} — Click to open panel.`;
```

### Acceptance criteria
- Connected state tooltip shows the backend URL.
- Disconnected state tooltip shows the backend URL.
- `npx tsc --noEmit` passes without errors.

---

## Issue #4 — Add local development setup docs for the VS Code extension

**Labels:** `good-first-issue` · `ECSoC26-L1` · `documentation` · `dx`

### Problem
The backend has a well-documented `backend/.env.example` file. However, the VS Code extension has **no equivalent documentation** for its configuration. New contributors who want to develop the extension locally must read through source code to figure out what to configure.

### Where to look
- File: `backend/.env.example` — the existing backend example (for reference style)
- File: `extension/src/config.ts` — lists all config fields
- File: `extension/README.md` — the extension's existing README

### How to implement
1. Open `extension/README.md` (or create `extension/DEVELOPMENT.md`).
2. Add a "Local Development" section that covers:
   - How to install dependencies: `cd extension && npm install`
   - How to launch the extension: Open the `extension/` folder in VS Code, then press `F5`
   - What configuration values are needed and where to get them:
     - **Backend URL** — default `https://gitphone.onrender.com`, or `http://localhost:8000` if running locally
     - **Telegram ID** — obtained by sending `/start` to the bot
   - How to run the TypeScript type check: `npx tsc --noEmit`
3. Make sure the information is accurate.

### Acceptance criteria
- A new developer can read the document and run the extension locally without asking questions.
- All commands in the doc actually work.

---

## Issue #5 — Add `CHANGELOG.md` to track version history

**Labels:** `good-first-issue` · `ECSoC26-L1` · `documentation`

### Problem
GitPhone's VS Code extension is at version `1.5.6` (see `extension/package.json`), but there is **no `CHANGELOG.md`** in the repository. Contributors and users cannot tell what changed between versions.

### Where to look
- File: `extension/package.json` — current version is `1.5.6`
- Reference: https://keepachangelog.com/en/1.0.0/

### How to implement
1. Create a new file `CHANGELOG.md` in the **repository root**.
2. Use the Keep a Changelog format. At minimum include three entries:

```markdown
# Changelog

All notable changes to GitPhone are documented here.

## [Unreleased]

## [1.5.6] - Latest
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
```

### Acceptance criteria
- `CHANGELOG.md` exists in the repo root.
- It follows the Keep a Changelog format.
- It covers at least the current version and 2 prior milestones.

---

## Issue #6 — Extract hardcoded version string `"1.0.0"` into a constant in `main.py`

**Labels:** `good-first-issue` · `ECSoC26-L1` · `backend` · `dx`

### Problem
In `backend/main.py`, the version string `"1.0.0"` appears in **three** separate places:

```python
# In FastAPI() constructor
app = FastAPI(version="1.0.0", ...)

# In /health endpoint
return {"status": "ok", "service": "gitphone", "version": "1.0.0"}

# In / root endpoint
return {"service": "GitPhone", ..., "version": "1.0.0"}
```

When the backend version is updated, a developer must remember to update all three places. A single constant is safer.

### Where to look
- File: `backend/main.py` — lines ~118, ~184, ~193

### How to implement
1. At the top of `backend/main.py`, after the imports, add:
   ```python
   APP_VERSION = "1.0.0"
   ```
2. Replace all three `"1.0.0"` string literals with `APP_VERSION`.
3. Run `ruff check backend/` to verify no linting issues.

### Acceptance criteria
- `APP_VERSION` is defined exactly once near the top of `main.py`.
- All three usages reference `APP_VERSION`.
- `ruff check backend/` passes cleanly.

---

## Issue #7 — Add a proper type annotation to `_bot` in `channel_logger.py`

**Labels:** `good-first-issue` · `ECSoC26-L1` · `backend` · `code-quality`

### Problem
In `backend/channel_logger.py` line 28, the global `_bot` variable is initialized without a type annotation:

```python
_bot = None
```

This causes static analysis tools and IDEs to show "possibly None" warnings throughout the file. A proper annotation makes the code cleaner and more IDE-friendly.

### Where to look
- File: `backend/channel_logger.py` — lines 28 and 31

### How to implement
1. Add the `Bot` import at the top:
   ```python
   from telegram import Bot
   ```
2. Change the global declaration:
   ```python
   from typing import Optional
   _bot: Optional[Bot] = None
   ```
3. Update `init_logger` with typed parameters:
   ```python
   def init_logger(bot: Bot) -> None:
       global _bot
       _bot = bot
   ```
4. Run `ruff check backend/` to confirm no errors.

### Acceptance criteria
- `_bot` has an `Optional[Bot]` type annotation.
- `init_logger` has a typed `bot: Bot` parameter and `-> None` return type.
- `ruff check backend/` passes cleanly.

---

## Issue #8 — Expand `detectMinified()` in `diffEngine.ts` to cover more patterns

**Labels:** `good-first-issue` · `ECSoC26-L1` · `extension` · `code-quality`

### Problem
In `extension/src/diffEngine.ts`, the `detectMinified()` function only checks for `.min.` in the path:

```typescript
export function detectMinified(relativePath: string): boolean {
  return relativePath.includes('.min.');
}
```

This misses common patterns like files in `dist/`, `build/`, or `out/` folders, and files ending in `.bundle.js` or `.prod.js`. These large generated files should also be skipped since diffing them is not useful.

### Where to look
- File: `extension/src/diffEngine.ts` — the `detectMinified()` function (~line 56)

### How to implement
Update `detectMinified()` to also return `true` for:
- Paths containing `/dist/` or `\dist\`
- Paths containing `/build/` or `\build\`
- Paths containing `/out/` or `\out\`
- Paths ending in `.bundle.js`
- Paths ending in `.prod.js`

```typescript
export function detectMinified(relativePath: string): boolean {
  if (relativePath.includes('.min.')) return true;
  if (/[\\/]dist[\\/]/.test(relativePath)) return true;
  if (/[\\/]build[\\/]/.test(relativePath)) return true;
  if (/[\\/]out[\\/]/.test(relativePath)) return true;
  if (relativePath.endsWith('.bundle.js')) return true;
  if (relativePath.endsWith('.prod.js')) return true;
  return false;
}
```

Run `npx tsc --noEmit` after the change.

### Acceptance criteria
- `detectMinified('dist/app.js')` returns `true`.
- `detectMinified('src/app.ts')` returns `false`.
- `detectMinified('lib/jquery.min.js')` still returns `true`.
- `npx tsc --noEmit` passes.

---

## Issue #9 — Expand `SECURITY.md` with a token handling and vulnerability reporting section

**Labels:** `good-first-issue` · `ECSoC26-L1` · `documentation` · `security`

### Problem
The existing `SECURITY.md` file is very minimal. New users may be concerned about whether their GitHub tokens are safe. Adding a clear, accurate statement about how data is handled will increase user trust.

### Where to look
- File: `SECURITY.md` — the existing minimal file
- File: `backend/auth.py` — shows only the SHA-256 hash of the API key is stored
- File: `backend/supabase_service.py` — `upsert_user()` stores `github_token`
- File: `backend/channel_logger.py` — verify no token values are passed to the logger

### How to implement
1. Open `SECURITY.md`.
2. Add a **"Data Handling"** section covering:
   - **GitHub Token:** Stored in Supabase (encrypted at rest by Supabase). Never printed to logs.
   - **API Key:** Only the SHA-256 hash is stored. The raw key is given to the extension once at registration and never stored server-side.
   - **Telegram ID:** Used as a user identifier. It is a public number, not a secret.
   - **File Content:** Temporarily stored in Supabase as a staged diff until committed, then deleted.
3. Add a **"Reporting a Vulnerability"** section telling contributors to open a GitHub private security advisory or contact the maintainer directly.

### Acceptance criteria
- `SECURITY.md` has a "Data Handling" section covering the four data types above.
- `SECURITY.md` has a "Reporting a Vulnerability" section.
- All statements accurately reflect the codebase.

---

## Issue #10 — Show a friendly, actionable message when `/files` has nothing staged

**Labels:** `good-first-issue` · `ECSoC26-L1` · `bot` · `ux`

### Problem
When a user types `/files` and has zero files staged, the bot shows a message like `"No files pending."` — but this is vague. A new user may not understand what "pending" means or what action they should take next.

### Where to look
- File: `backend/bot.py` — find the `/files` handler and the branch that handles an empty staged file list (`if not staged_files:`)

### How to implement
1. Open `backend/bot.py` and find the `if not staged_files:` (or equivalent) check in the files handler.
2. Replace the current message with a more user-friendly, actionable one:

```
📭 No files staged yet!

To stage files:
1. Open your project in VS Code
2. Make and save some changes
3. The GitPhone extension will sync them automatically

Come back here and use /files once changes appear.
```

3. Keep `parse_mode=ParseMode.MARKDOWN` to render the emoji and formatting.

### Acceptance criteria
- When `/files` is called with no staged files, the user sees the new friendly message.
- The message tells the user exactly what to do next.
- The existing behavior when files **are** staged is unchanged.

---

## Issue #11 — Add `.editorconfig` to enforce consistent formatting across editors

**Labels:** `good-first-issue` · `ECSoC26-L1` · `dx` · `tooling`

### Problem
The project has both Python (4-space indent) and TypeScript (2-space indent) code. Different contributors using different editors can introduce inconsistent indentation, line endings, and trailing whitespace. An `.editorconfig` file automatically enforces these basics for all editors that support it (VS Code, JetBrains, Vim, etc.).

### Where to look
- There is currently no `.editorconfig` in the repo root.
- Reference: https://editorconfig.org/

### How to implement
Create `.editorconfig` in the **repository root** with this content:

```ini
# EditorConfig — https://editorconfig.org
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.py]
indent_style = space
indent_size = 4

[*.ts]
indent_style = space
indent_size = 2

[*.json]
indent_style = space
indent_size = 2

[*.md]
trim_trailing_whitespace = false
```

Verify the indent sizes match actual usage in `backend/bot.py` (4 spaces) and `extension/src/extension.ts` (2 spaces).

### Acceptance criteria
- `.editorconfig` exists in the repository root.
- Indent sizes match the existing code style.
- `trim_trailing_whitespace = false` is set for `.md` files.

---

## Issue #12 — `list_branches()` silently caps at 50 with no indication to the caller

**Labels:** `good-first-issue` · `ECSoC26-L1` · `backend` · `code-quality`

### Problem
In `backend/github_service.py`, `list_branches()` silently truncates to 50:

```python
return [b.name for b in repo.get_branches()][:50]
```

If a repo has more than 50 branches, the Telegram `/branch` command shows an incomplete list with no warning. Users may be confused why their branch isn't appearing.

### Where to look
- File: `backend/github_service.py` — the `list_branches()` method (~line 44)
- File: `backend/bot.py` — wherever `list_branches()` is called

### How to implement
1. Modify `list_branches()` to return a `dict` with `branches` and `truncated` keys:

```python
def list_branches(self, token: str, repo_name: str) -> dict:
    """Return branch names for a repo (max 50). Returns { branches, truncated }."""
    try:
        repo = Github(token).get_repo(repo_name)
        all_branches = [b.name for b in repo.get_branches()]
        truncated = len(all_branches) > 50
        return {"branches": all_branches[:50], "truncated": truncated}
    except Exception as e:
        print(f"[github_service] list_branches error: {e}")
        return {"branches": [], "truncated": False}
```

2. Update the caller in `bot.py` to use `result["branches"]` and — if `result["truncated"]` is `True` — append `"\n_(showing first 50 branches only)_"` to the message.
3. Run `ruff check backend/` to check for linting issues.

### Acceptance criteria
- `list_branches()` returns a `dict` with `branches` (list) and `truncated` (bool) keys.
- The bot mentions if the branch list was truncated.
- All callers in `bot.py` are updated.
- `ruff check backend/` passes.

---

## 🏷️ How to claim an issue

1. Leave a comment on the GitHub issue saying: **"I'd like to work on this."**
2. The maintainer will assign it to you.
3. Fork the repo → create a feature branch → implement → open a PR.
4. Add the `ECSoC26` label to your PR to get it scored automatically.

Good luck and happy coding! 🚀
