# GitPhone

> **Commit to GitHub from your phone — via Telegram bot**

GitPhone is a developer tool that lets you stage code changes in VS Code and commit them to GitHub from anywhere using a Telegram bot — no laptop needed.

---

## How It Works

```
1. Save a file in VS Code
       ↓
2. GitPhone extension computes a diff locally
       ↓
3. Diff is synced to the cloud (Supabase)
       ↓
4. Open Telegram → /files
       ↓
5. Select files, type commit message, tap 🚀
       ↓
6. Real GitHub commit — streak maintained ✅
```

---

## Demo

```
User: /files

Bot: 📁 john/my-project • main
     Select files to commit:
     ☐  src/index.js    1.2KB
     ☐  README.md       0.8KB
     [☑️ Select All]  [✅ Done]

User: [taps src/index.js] → [taps Done]

Bot: ✏️ Type your commit message:
     • src/index.js

User: fix: updated auth logic

Bot: 📦 Review Commit
     • src/index.js
     💬 fix: updated auth logic
     🌿 main • john/my-project
     [🚀 Commit Now] [❌ Cancel]

User: [taps Commit Now]

Bot: ✅ Committed!
     🔗 abc123f
     💬 fix: updated auth logic
     🔥 Streak maintained!
```

---

## Setup (8 minutes)

1. **Supabase** — Create free project, run `setup/schema.sql`
2. **GitHub** — Create fine-grained PAT with Contents read/write
3. **Telegram** — Get your ID from @userinfobot, start @GitPhoneBot
4. **VS Code** — Install extension, fill 5 fields, connect

→ Full guide: [docs/setup-guide.md](public/docs/setup-guide.md)

---

## Architecture

```
VS Code Extension (TypeScript)
  → Watches file saves
  → Computes diffs locally
  → POSTs to Render backend

Backend (Python/FastAPI + Telegram Bot)
  → Runs on Render (free, webhook mode)
  → Stores diffs in Supabase
  → Commits to GitHub via PyGithub

Supabase (PostgreSQL)
  → Users, staged_files, commit_log
```

---

## Repository Structure

```
gitphone/
├── backend/        ← FastAPI + Telegram bot (Python)
├── extension/      ← VS Code extension (TypeScript)
├── public/         ← Schema + docs (you are here)
│   ├── setup/
│   │   └── schema.sql     ← Run this in Supabase
│   └── docs/
│       ├── setup-guide.md
│       └── troubleshooting.md
└── .context/       ← AI agent context files
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot | python-telegram-bot v21 (webhook) |
| Backend | FastAPI + uvicorn |
| GitHub API | PyGithub |
| Diff (backend) | diff-match-patch (Google) |
| Database | Supabase (PostgreSQL) |
| Hosting | Render (free, no credit card) |
| Extension | TypeScript + VS Code API |
| Diff (extension) | diff (npm) |
| HTTP client | axios |

---

## Security Notes

- GitHub tokens stored as **plain text** in MVP (AES-256 encryption post-launch)
- Bot only responds to **whitelisted Telegram IDs** (your registered users)
- Tokens are **never logged or exposed** in API responses
- BYOD (Bring Your Own Database) model planned post-launch for full privacy

---

## Roadmap

See [.context/13_OPEN_SOURCE_ROADMAP.md](.context/13_OPEN_SOURCE_ROADMAP.md) for post-hackathon plans including:
- AES-256 token encryption
- Scheduled commits
- Multi-repo support
- Branch switching
- BYOD model

---

## License

Custom Proprietary

Test