# GitPhone — Commit from Your Phone 📱

**Stage changes in VS Code. Commit from Telegram. Keep your GitHub streak alive.**

GitPhone is a VS Code extension that bridges your local code with your phone. Save a file → it's instantly staged in the cloud → open Telegram and commit with a tap. No laptop needed.

---

## How It Works

```
Save file in VS Code  →  Diff synced to cloud  →  Telegram /files  →  🚀 Committed!
```

1. **Save any file** in your open workspace
2. Status bar shows: `✅ GitPhone — 1 staged`
3. Open **Telegram** → send `/files` to [@GitPhoneBot](https://t.me/GitPhoneBot)
4. Tap the file → type commit message → tap **🚀 Commit Now**
5. Real GitHub commit. Streak maintained. Done.

---

## Features

- 🔄 **Auto-sync on save** — diffs sent to cloud automatically
- 📱 **Telegram bot interface** — commit from anywhere, any device
- 🔀 **Diff-based sync** — stores only changes, not full files (97% storage savings)
- ⚡ **Conflict detection** — warns if file changed on GitHub after staging
- 🔒 **Your token, your data** — GitHub PAT stored in your account only
- 📊 **Status bar** — always shows staged file count
- 🪟 **Windows friendly** — CRLF normalization built in

---

## Quick Setup (~8 minutes)

### 1. Supabase (3 min)
- Create free account at [supabase.com](https://supabase.com)
- New project → SQL Editor → run the schema from [setup/schema.sql](https://github.com/ankittroy-21/gitphone/blob/main/public/setup/schema.sql)
- Copy your **Project URL** and **anon key**

### 2. GitHub PAT (2 min)
- Settings → Developer Settings → Fine-grained tokens
- Select your repo → **Contents: read & write** only
- Copy the token

### 3. Telegram (1 min)
- Message [@userinfobot](https://t.me/userinfobot) → copy your numeric ID
- Start [@GitPhoneBot](https://t.me/GitPhoneBot)

### 4. Connect (2 min)
- `Ctrl+Shift+P` → **GitPhone: Open Setup**
- Fill the 5 fields → **🚀 Connect**

---

## 💻 Local Development

### Install dependencies

From the repository root, install the extension dependencies:

```bash
cd extension
npm install
```

### Launch the extension

1. Open the `extension/` folder in Visual Studio Code.
2. Press `F5` to launch the Extension Development Host.

### Configuration

After launching the extension, run **GitPhone: Open Setup** from the Command Palette (`Ctrl+Shift+P`) and provide the following values:

#### Backend URL

- Default production backend: `https://gitphone.onrender.com`
- Local backend (if running the backend yourself): `http://localhost:8000`

#### Telegram ID

Open the GitPhone Telegram bot and send:
```text
/start
```
The bot will reply with your Telegram ID. Use that value in the extension configuration.

### Type checking

To check for TypeScript type errors, run:

```bash
cd extension
npx tsc --noEmit
```

---

## Telegram Bot Commands

| Command | Description |
|---|---|
| `/files` | Select staged files and commit |
| `/log` | Recent commit history |
| `/status` | Connection status and repo info |
| `/start` | Setup or reconfigure |
| `/help` | All commands |

---

## Requirements

- VS Code 1.85+
- A GitHub account with a repository
- A Telegram account
- A free [Supabase](https://supabase.com) account

---

## Privacy & Security

- Your **GitHub token is never logged** or exposed in API responses
- Diffs (not full files) are stored — your code stays as small fragments
- Only your **Telegram ID** can trigger commits — no one else can use your bot session
- Full security details: [security.md](https://github.com/ankittroy-21/gitphone/blob/main/public/docs/security.md)

---

## Troubleshooting

See [troubleshooting.md](https://github.com/ankittroy-21/gitphone/blob/main/public/docs/troubleshooting.md) for help with:
- Bot not responding
- Files not appearing in `/files`
- GitHub token errors
- Supabase paused (free tier)

---

## Feedback & Issues

[github.com/ankittroy-21/gitphone/issues](https://github.com/ankittroy-21/gitphone/issues)

---

*Built for developers who live on GitHub streaks and Telegram. Made with ❤️*
