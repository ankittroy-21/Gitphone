# GitPhone Setup Guide

> **Time to complete:** ~10 minutes

GitPhone lets you commit to GitHub from your phone via Telegram.
Your VS Code extension stages files locally — your phone commits them.

---

## Prerequisites

- A GitHub account with a repository
- A Telegram account
- VS Code installed

---

## Step 1 — Create Your Supabase Database (~3 minutes)

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Click **New Project**
3. Give it a name (e.g. `gitphone`) and set a database password
4. Wait for the project to initialize (~1 minute)
5. Go to **SQL Editor** in the left sidebar
6. Open `setup/schema.sql` from this repo
7. Paste the entire SQL and click **Run**
8. You should see: `Success. No rows returned.`
9. Copy your **Project URL** and **anon (public) key** from:
   > Settings → API → Project URL + anon key

---

## Step 2 — Create a GitHub Fine-Grained Token (~2 minutes)

1. Go to GitHub → **Settings → Developer Settings → Fine-grained tokens**
2. Click **Generate new token**
3. Set a name (e.g. `gitphone`)
4. Set expiration (90 days recommended)
5. Under **Repository access**: select **Only select repositories** → pick your repo
6. Under **Permissions → Repository permissions**:
   - **Contents**: `Read and write`
   - Everything else: `No access`
7. Click **Generate token** and copy it immediately

> ⚠️ You won't see the token again after leaving the page.

---

## Step 3 — Get Your Telegram User ID (~1 minute)

1. Open Telegram and search for **@userinfobot**
2. Start a chat and send `/start`
3. It will reply with your numeric user ID (e.g. `123456789`)
4. Copy that number

Then start **@GitPhoneBot** on Telegram.

---

## Step 4 — Install the VS Code Extension (~2 minutes)

### Option A: From VSIX (Hackathon)
1. Download `gitphone-1.0.0.vsix`
2. In VS Code: `Ctrl+Shift+P` → **Extensions: Install from VSIX**
3. Select the `.vsix` file

### Option B: From Marketplace (Post-launch)
Search "GitPhone" in the VS Code Extensions panel.

---

## Step 5 — Connect GitPhone (~2 minutes)

When the extension installs, the setup panel opens automatically.

Fill in the 5 fields:

| Field | Value |
|---|---|
| GitHub PAT | Your fine-grained token from Step 2 |
| Telegram User ID | Your numeric ID from Step 3 |
| Default Repository | `username/repo-name` |
| Branch | `main` (or your default branch) |
| Backend URL | `https://gitphone.onrender.com` |

Click **🚀 Connect GitPhone**

You should see the status bar change to: `✅ GitPhone — 0 staged`

---

## Verify It Works

1. Open any file in your workspace
2. Make a small change (add a comment)
3. Save the file (`Ctrl+S`)
4. Status bar updates to: `✅ GitPhone — 1 staged`
5. Open Telegram → send `/files` to **@GitPhoneBot**
6. You should see your file listed!
7. Tap the file → Tap **✅ Done**
8. Type a commit message
9. Tap **🚀 Commit Now**
10. Check GitHub — your commit is live! 🎉

---

## Troubleshooting

See [troubleshooting.md](troubleshooting.md) for common issues.
