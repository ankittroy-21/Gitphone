# Troubleshooting GitPhone

Jump to the section that matches your problem:

- [Bot not responding to commands](#bot-not-responding-to-commands)
- [Telegram auth / "User not registered"](#telegram-auth--user-not-registered)
- [GitHub Device Flow failures](#github-device-flow-failures)
- [Supabase connection issues](#supabase-connection-issues)
- [Status bar shows "Disconnected"](#status-bar-shows-disconnected)
- [Files not appearing in /files](#files-not-appearing-in-files)
- [GitHub token / commit errors](#github-token--commit-errors)
- [Conflict detected on commit](#conflict-detected-on-commit)
- [Supabase paused (free tier)](#supabase-paused-free-tier)
- [Commit shows as "unverified"](#commit-shows-as-unverified-on-github)

---

## Bot not responding to commands

**Cause:** Backend on Render may be waking up from a cold start (free tier spins down after inactivity).

**Fix:**

1. Wait 30 seconds and try the command again
2. Visit `https://gitphone.onrender.com/health` in your browser
3. If it shows `{"status":"ok"}` the backend is healthy
4. If you see an error or timeout, check the Render dashboard logs for details

---

## Telegram auth / "User not registered"

**Cause:** The Telegram ID stored in the extension doesn't match your actual Telegram account.

**Fix:**

1. In Telegram, message **@userinfobot** and send `/start` — note the numeric ID it returns
2. In VS Code: `Ctrl+Shift+P` → **GitPhone: Open Setup**
3. Confirm the **Telegram User ID** field matches what @userinfobot showed
4. If they differ, update the field and click **🚀 Connect GitPhone** again

**Also check:** Make sure you sent `/start` to the bot at least once from your Telegram account before trying other commands. The bot won't recognize you until you've initiated contact.

---

## GitHub Device Flow failures

The `/auth` command uses GitHub's Device Flow — no passwords or tokens required. Here are the common failure modes:

**Code expired (`authorization_expired`)**

Device Flow codes are valid for 15 minutes. If you waited too long before entering the code on GitHub:

1. Send `/auth` again to get a fresh code
2. Complete the browser step promptly

**"Bad verification code" on GitHub**

- Double-check you typed the code exactly (format is `XXXX-XXXX`)
- Make sure you're on `https://github.com/login/device` — not a different URL
- If the page says the code is already used, send `/auth` again

**Browser link not opening / no response after authorizing**

The bot polls GitHub for up to 5 minutes after sending you the code. If it stops polling or you see no confirmation:

1. Check that you actually clicked **Authorize** on the GitHub page (not just entered the code)
2. Send `/status` to the bot — if it shows GitHub as disconnected, run `/auth` again
3. If the problem persists, check backend logs for `slow_down` or `access_denied` errors from GitHub

**`access_denied` error**

You clicked **Cancel** instead of **Authorize** on the GitHub permissions page. Send `/auth` and authorize this time.

---

## Supabase connection issues

**Symptoms:** Bot returns database errors, files disappear after staging, or nothing saves.

**Wrong Project URL or anon key**

1. Log into [supabase.com](https://supabase.com) → open your project
2. Go to **Settings → API**
3. Copy the **Project URL** and **anon (public) key** — make sure you're not using the `service_role` key
4. Update your backend `.env` (or Render environment variables) and redeploy

**Schema not applied**

If you see errors like `relation "users" does not exist`, the schema wasn't set up correctly:

1. Go to **SQL Editor** in your Supabase dashboard
2. Open `setup/schema.sql` from the repo root
3. Paste and run the entire file
4. Confirm you see `Success. No rows returned.`

**Row Level Security (RLS) blocking writes**

If inserts succeed but reads return empty results, RLS policies may be too restrictive. Check the **Authentication → Policies** section in Supabase and confirm the `anon` role has the permissions defined in `setup/schema.sql`.

**Supabase project paused** → see [Supabase paused](#supabase-paused-free-tier) below.

---

## Status bar shows "Disconnected"

**Cause:** The extension can't reach the backend.

**Fix:**

1. Check your Backend URL in the setup panel (should end with no trailing slash)
2. Visit the URL directly in a browser — it should return a JSON health response
3. If using Render's free tier, the backend may be cold — wait 30 seconds and reconnect
4. Open VS Code's **Output** panel → select **GitPhone** to see connection error details
5. Re-open the setup panel and click **🚀 Connect GitPhone**

---

## Files not appearing in `/files`

**Causes and fixes:**

1. **Extension not saving diffs** — Open VS Code **Output** panel → **GitPhone** channel and look for errors on save
2. **Wrong workspace** — The extension only watches files inside the currently open workspace folder; make sure the right folder is open
3. **File too large** — Files over 10 MB are skipped; you'll see a warning in VS Code
4. **File in an ignored folder** — `node_modules/`, `.git/`, and `dist/` are excluded automatically
5. **Backend not receiving data** — Check the status bar shows `✅ GitPhone` (not disconnected); if it's disconnected, fix that first

---

## GitHub token / commit errors

**Symptoms:** Bot says "GitHub token error", "permission denied", or commit fails immediately.

**Fix:**

1. Send `/auth` to re-authorize — your Device Flow token may have expired or been revoked
2. If you manually created a fine-grained PAT for the extension, check that it hasn't expired (GitHub → Settings → Developer Settings → Fine-grained tokens)
3. Verify the token has **Contents: Read and write** permission on the target repository
4. Check the repository name in the extension setup matches exactly (`username/repo-name`)
5. If the repo is inside an organization, make sure the token has organization access approved

---

## Conflict detected on commit

**What it means:** The file on GitHub was changed after you staged your version locally.

**Options the bot gives you:**

- **Force Commit (overwrite)** — Your staged version overwrites what's on GitHub. Use this if you're sure your version is correct.
- **Cancel** — Abandons the commit. Re-save the file in VS Code to generate a fresh diff that includes the latest GitHub version.

To avoid this: use `/preview` before committing to see if your diff is still current.

---

## Supabase paused (free tier)

**Cause:** Supabase pauses free projects after 1 week of inactivity.

**Fix:**

1. Log into [supabase.com](https://supabase.com)
2. Find your project — it will show a **Paused** banner
3. Click **Restore** and wait ~1 minute for it to wake up
4. Try the extension again

> **Prevention:** Sending any bot command or saving a file in VS Code counts as activity. Using GitPhone at least once a week keeps the project active automatically.

---

## Commit shows as "unverified" on GitHub

This is expected behavior for API-based commits that aren't GPG-signed.

Your commits are fully real and functional — the "unverified" badge only means the commit wasn't signed with a GPG key. It does **not** affect your GitHub streak or contribution graph.

**To fix (optional):** Set up GPG commit signing in GitHub and add your public key under **Settings → SSH and GPG keys**. Note that this requires configuring the backend to use your GPG key when committing, which is not currently automated.

---

Still stuck? Open an issue at [github.com/ankittroy-21/Gitphone/issues](https://github.com/ankittroy-21/Gitphone/issues) and include the error message plus the VS Code Output panel logs.
