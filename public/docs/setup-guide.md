# GitPhone Setup Guide

> **Time to complete:** ~10 minutes

GitPhone lets you commit to GitHub from your phone via Telegram.
Your VS Code extension stages files locally — your phone commits them.

---

## Prerequisites

- A GitHub account with at least one repository
- A Telegram account
- VS Code installed
- Access to [Supabase](https://supabase.com) (free tier is fine)

> **Using the hosted backend?** If you're using `https://gitphone.onrender.com` (the public instance), you only need Steps 1–5. Self-hosters should also follow the [backend deployment guide](../../backend/README.md) before starting.

---

## Step 1 — Create Your Supabase Database (~3 minutes)

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Click **New Project**
3. Give it a name (e.g. `gitphone`) and set a database password — save this password somewhere safe
4. Wait for the project to initialize (~1 minute)
5. Go to **SQL Editor** in the left sidebar
6. Open `setup/schema.sql` from this repo (it's in the `setup/` folder at the root)
7. Paste the entire SQL and click **Run**
8. You should see: `Success. No rows returned.`
9. Copy your **Project URL** and **anon (public) key** from:

> **Settings → API → Project URL** and **anon key** (not the `service_role` key)

Keep these two values handy — you'll need them when configuring the backend.

---

## Step 2 — Configure Backend Environment Variables

> Skip this step if you're using the hosted backend at `https://gitphone.onrender.com`.

In the `backend/` folder, copy `.env.example` to `.env` and fill in:

```
SUPABASE_URL=<your Project URL from Step 1>
SUPABASE_KEY=<your anon key from Step 1>
TELEGRAM_BOT_TOKEN=<your bot token from BotFather>
GITHUB_CLIENT_ID=<your GitHub OAuth App client ID>
```

To get a Telegram bot token: search for **@BotFather** on Telegram → `/newbot` → follow the prompts.

---

## Step 3 — Get Your Telegram User ID (~1 minute)

1. Open Telegram and search for **@userinfobot**
2. Start a chat and send `/start`
3. It will reply with your numeric user ID (e.g. `123456789`)
4. Copy that number — you'll enter it in the VS Code extension setup

Then open **@GitPhoneBot** on Telegram (or your own bot if self-hosting) and send `/start` to register.

---

## Step 4 — Authorize GitHub via Device Flow (~2 minutes)

GitPhone uses GitHub's **Device Flow** (OAuth) to securely authorize the bot — it never asks for your password or a token directly.

1. In Telegram, send `/auth` to the bot
2. The bot replies with a short code (e.g. `ABCD-1234`) and a link: `https://github.com/login/device`
3. Open that link in your browser, enter the code, and click **Authorize**
4. The bot confirms: `✅ GitHub connected as @yourusername`

> **Code expired?** Device Flow codes expire after 15 minutes. If you see `authorization_expired`, just send `/auth` again to get a new code.

---

## Step 5 — Install the VS Code Extension (~2 minutes)

**Option A: From VS Code Marketplace**

Search "GitPhone" in the Extensions panel (`Ctrl+Shift+X`) and click **Install**.

**Option B: From VSIX**

1. Download `gitphone-1.0.0.vsix` from the [Releases page](https://github.com/ankittroy-21/Gitphone/releases)
2. In VS Code: `Ctrl+Shift+P` → **Extensions: Install from VSIX**
3. Select the `.vsix` file

---

## Step 6 — Connect GitPhone in VS Code (~2 minutes)

When the extension installs, the setup panel opens automatically. You can also open it anytime via `Ctrl+Shift+P` → **GitPhone: Open Setup**.

Fill in the fields:

| Field              | Value                                                       |
| ------------------ | ----------------------------------------------------------- |
| Telegram User ID   | Your numeric ID from Step 3                                 |
| Default Repository | `username/repo-name`                                        |
| Branch             | `main` (or your default branch)                             |
| Backend URL        | `https://gitphone.onrender.com` (or your self-hosted URL)   |

Click **🚀 Connect GitPhone**.

You should see the status bar change to: `✅ GitPhone — 0 staged`

---

## Verify It Works

1. Open any file in your VS Code workspace
2. Make a small change (add a comment)
3. Save the file (`Ctrl+S`)
4. Status bar updates to: `✅ GitPhone — 1 staged`
5. Open Telegram → send `/files` to the bot
6. You should see your file listed
7. Tap the file → Tap **✅ Done**
8. Type a commit message
9. Tap **🚀 Commit Now**
10. Check GitHub — your commit is live! 🎉

---

## Next Steps

- Read the **[Full User Guide](../../USER_GUIDE.md)** for all bot commands and workflows
- Hit a problem? See **[Troubleshooting](./troubleshooting.md)** for common issues
