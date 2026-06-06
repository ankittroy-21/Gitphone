# Troubleshooting GitPhone

## Bot not responding to commands

**Cause:** Backend on Render may be waking up (cold start).

**Fix:**
1. Wait 30 seconds and try again
2. Visit `https://your-app.onrender.com/health` in your browser
3. If it shows `{"status":"ok"}` the backend is healthy
4. If you see an error, check Render dashboard logs

---

## "User not registered" error in bot

**Cause:** Telegram ID in Telegram doesn't match what the extension sent.

**Fix:**
1. In VS Code: `Ctrl+Shift+P` → **GitPhone: Open Setup**
2. Verify Telegram ID matches what @userinfobot shows you
3. Re-connect

---

## Status bar shows "Disconnected"

**Cause:** Backend unreachable.

**Fix:**
1. Check your Backend URL in setup (should be `https://your-app.onrender.com`)
2. Visit the URL in browser — should return JSON
3. Re-open setup panel and re-connect

---

## Files not appearing in `/files`

**Causes and fixes:**

1. **Extension not saving diffs** — Check VS Code Output panel for GitPhone errors
2. **Wrong workspace** — Extension only watches files in the open workspace folder
3. **File too large** — Files over 10MB are skipped (check the warning in VS Code)
4. **File in ignored folder** — `node_modules/`, `.git/`, `dist/` are skipped automatically

---

## GitHub token error

**Symptoms:** Bot says "GitHub token error" or commit fails immediately.

**Fix:**
1. Check your fine-grained PAT hasn't expired
2. Verify the token has `Contents: read & write` permission
3. Verify the token has access to the specific repo
4. Create a new token and update it via **GitPhone: Open Setup**

---

## "Conflict detected" on commit

**What it means:** The file was modified on GitHub after you staged it.

**Options in the bot:**
- **Force Commit (overwrite)** — Your staged version overwrites GitHub
- **Cancel** — Abandon the commit, re-save the file in VS Code to get a fresh diff

---

## Supabase paused (free tier)

**Cause:** Supabase pauses free projects after 1 week of inactivity.

**Fix:**
1. Log into [supabase.com](https://supabase.com)
2. Find your project and click **Restore**
3. Wait ~1 minute for it to wake up
4. Try the extension again

> **Prevention:** Using GitPhone regularly (even once a week) keeps your Supabase active automatically.

---

## Commit shows as "unverified" on GitHub

This is expected behavior for API-based commits that aren't GPG-signed.

Your commits are real and fully functional — the "unverified" badge only means
the commit wasn't signed with a GPG key. This does not affect your GitHub streak.

To fix (optional): Configure GPG signing in GitHub and add the public key to your account.
