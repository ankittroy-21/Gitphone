# 📖 GitPhone User Guide

Welcome to **GitPhone**! This guide will help you set up and master the art of committing to GitHub directly from your Telegram app.

---

## 🚀 Quick Start {Only For Testing}

### 1. Install the VS Code Extension
*   **Search:** Open VS Code Extensions (`Ctrl+Shift+X`) and search for **"GitPhone"**.
*   **Marketplace Link:** [GitPhone on VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=ankittroy-21.gitphone)
*   **Install:** Click Install.

![GitPhone on Marketplace](public/images/Gitphone-1.png)
*Finding the extension on the marketplace.*

### 2. Connect the Telegram Bot
*   **Open Telegram:** Search for [@GitphoneBot](https://t.me/gitphonebot).
*   **Start:** Send `/start` to the bot.
*   **Authenticate:** Send `/auth` and follow the GitHub Device Flow instructions to link your account securely.

### 3. Link Extension to Bot
*   In the VS Code sidebar, click the **GitPhone icon**.
*   Click **"Connect GitPhone"**.
*   Enter your **Telegram ID** (the bot provides this when you send `/start`).

![Extension Setup Screen](public/images/Extension.png)
*Linking your VS Code extension to your Telegram account.*

---

## 🛠 How to Use

### Step 1: Making Changes
Simply write code in VS Code. Every time you **save a file**, GitPhone automatically detects the change and syncs it to the cloud. You'll see a badge on the GitPhone sidebar showing how many files are "Ready to Sync".

### Step 2: The Bot Workflow
1.  Open **@GitphoneBot** on your phone.
2.  Type `/files` to see your modified files.
3.  **Select** the files you want to commit.
4.  Type your **Commit Message**.
5.  **Choose a Branch:** 
    *   *Note:* Direct pushing to `main` is often blocked if you have branch protection.
    *   **Recommendation:** Always select "Create new branch" to create a feature branch.
6.  **Commit & Merge:** Once committed, the bot will send you a **Pull Request link**. Click it to merge your changes into `main` via the GitHub mobile interface.

![Bot Commit Success](public/images/Bot.png)
*A successful commit and PR link sent to Telegram.*

---

## ⚠️ Current Limitations (Cons)

*   **Branch Protection:** You generally cannot push directly to protected branches (like `main`). The bot will prompt you to create a new branch if it hits a protection error.
*   **Binary Files:** Currently optimized for text files (code). Very large binary files may experience sync delays.
*   **Sync Only:** This is a "Push" tool. It does not currently support "Git Pull" or "Merge" logic directly within the bot (use the PR link for merging).

---

## 🗺 Future Roadmap

We are constantly improving GitPhone. Here is what's coming:

### ⚡ Performance & Speed
*   **WebSocket Sync:** Moving from HTTP polling to WebSockets for near-instant file updates between VS Code and Telegram.
*   **Incremental Diffs:** Reducing data usage by only sending the specific lines changed rather than full file contents.

### 🛡 Security
*   **End-to-End Encryption:** Encrypting file contents with a local key before syncing to the database.
*   **Granular Scopes:** Moving to fine-grained GitHub App permissions.

### ✨ Features
*   **AI Commit Messages:** Integrated AI to suggest commit messages based on your changes.
*   **Voice-to-Commit:** Send a voice note to the bot to set your commit message.
*   **Conflict Editor:** A simple mobile UI to resolve minor merge conflicts within Telegram.
*   **PR Reviews:** View and approve Pull Requests directly from the bot.
*   **Adding Team Option:** Can add team feature

---

## 🆘 Troubleshooting
*   **Files not appearing?** Ensure the GitPhone sidebar in VS Code says "Connected".
*   **Auth failing?** Try running `/auth` again to refresh your GitHub token.
*   **Repo mismatch?** The extension auto-detects your repo. Ensure you have the correct project folder open in VS Code.

---
*Created with ❤️ for developers on the move.*
