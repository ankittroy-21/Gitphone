"""
bot.py - All Telegram bot handlers for GitPhone.
Uses python-telegram-bot v21 (async, webhook mode).

User Commands:
  /start   - Register or welcome back (uses Device Flow via /auth)
  /auth    - GitHub Device Flow login (browser-based, no PAT needed)
  /files   - Select staged files grouped by repo & commit
  /log     - Recent commit history
  /status  - Connection status & repo info
  /repo    - Show active repo (auto-detected)
  /branch  - Switch active branch
  /preview - Preview diffs before committing
  /unstage - Remove a specific file from staged
  /clear   - Clear all staged files
  /cancel  - Cancel current operation
  /help    - Show all commands

Admin Commands (ADMIN_TELEGRAM_IDS env var):
  /ban <id> [reason]  - Ban a user
  /unban <id>         - Unban a user
  /users [page]       - List all users
  /broadcast <msg>    - Message all users
  /stats              - Global platform stats
  /revoke <id>        - Force user to re-authenticate
"""

import os
import asyncio
import httpx
from datetime import datetime, timezone
from typing import Optional
import channel_logger
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode

from supabase_service import (
    get_user_by_telegram_id,
    upsert_user,
    update_last_active,
    get_pending_files,
    get_pending_files_by_repo,
    get_staged_files_by_ids,
    mark_files_committed,
    insert_commit_log,
    get_recent_commits,
    unstage_file_by_path,
    clear_all_staged,
    update_branch,
    save_device_flow_state,
    get_device_flow_state,
    delete_device_flow_state,
    update_github_token,
    update_github_username,
    ban_user,
    unban_user,
    revoke_api_key,
    get_all_users,
    count_stats,
)
from github_service import github_service

# GitHub Device Flow endpoints
GITHUB_CLIENT_ID     = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
DEVICE_CODE_URL      = "https://github.com/login/device/code"
TOKEN_URL            = "https://github.com/login/oauth/access_token"

# --- Conversation States ---------------------------------------------------------------------------------
WAITING_REPO         = 1
WAITING_BRANCH_SETUP = 2
SELECTING_FILES      = 10
WAITING_MESSAGE      = 11
CONFIRM_COMMIT       = 12
SELECTING_BRANCH     = 13   # NEW: branch picker before commit
WAITING_NEW_BR_NAME  = 14   # NEW: typing new branch name
WAITING_PROTECTED_BRANCH_NAME = 15  # NEW: typing branch name after protection error
WAITING_NEW_BRANCH   = 20
WAITING_AUTH_POLL    = 30   # Device Flow polling state

# --- Admin check ---------------------------------------------------------------------------------------------
def _is_admin(telegram_id: str) -> bool:
    admin_ids = os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",")
    return telegram_id.strip() in [a.strip() for a in admin_ids if a.strip()]


# --- Helpers ---------------------------------------------------------------------------------------------------

def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


def _time_ago(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        else:
            return f"{seconds // 86400}d ago"
    except Exception:
        return "recently"


def _build_files_keyboard(staged_files: list[dict], selected: set[str]) -> InlineKeyboardMarkup:
    """Build inline keyboard for file selection with change type icons."""
    buttons = []
    for f in staged_files:
        file_id = f["id"]
        filepath = f["filepath"]
        size = _format_file_size(f.get("file_size", 0))
        checked = "\u2705" if file_id in selected else "\u2610"
        # Show change type
        change = f.get("change_type", "modify")
        if change == "create":
            type_icon = "\u2795"   # \u2795 new file
        elif change == "delete":
            type_icon = "\U0001f5d1"  # [Clear] deletion
        else:
            type_icon = "\u270f"   # \u270f\ufe0f modification
        label = f"{checked} {type_icon} {filepath}" + (f"  {size}" if size != "0B" else "")
        buttons.append([InlineKeyboardButton(label, callback_data=f"FILE_TOGGLE:{file_id}")])

    done_count = f" ({len(selected)})" if selected else ""
    buttons.append([
        InlineKeyboardButton("\u2611\ufe0f Select All", callback_data="FILE_SELECT_ALL"),
        InlineKeyboardButton(f"\u2705 Done{done_count}", callback_data="FILE_DONE"),
    ])
    return InlineKeyboardMarkup(buttons)


async def _check_registered(update: Update) -> Optional[dict]:
    """Return user row if registered and not banned, else None."""
    telegram_id = str(update.effective_user.id)
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        await update.effective_message.reply_text(
            "\U0001f44b You're not registered yet!\n\n"
            "Use /start to set up your GitPhone account."
        )
        return None
    if user.get("status") == "banned":
        await update.effective_message.reply_text(
            "[Banned] Your account has been suspended.\n"
            "Contact support if you think this is a mistake."
        )
        return None
    update_last_active(telegram_id)
    return user


# --- /start Handler ------------------------------------------------------------------------------------------

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = str(update.effective_user.id)
    user = get_user_by_telegram_id(telegram_id)

    if user and user.get("status") != "banned" and user.get("github_token"):
        pending = get_pending_files(telegram_id)
        last_active = _time_ago(user.get("last_active", ""))
        active_repo = user.get("active_repo") or user.get("default_repo", "-")
        active_branch = user.get("active_branch") or user.get("branch", "main")
        await update.message.reply_text(
            f"\U0001f44b Welcome back!\n\n"
            f"[Repo] `{active_repo}` \u2022 `{active_branch}`\n"
            f"[Time] Last active: {last_active}\n"
            f"[Files] {len(pending)} file(s) staged\n\n"
            f"Use /files to commit, or /help for all commands.",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    # New user - direct to /auth
    await update.message.reply_text(
        "\U0001f44b Welcome to *GitPhone!*\n\n"
        "Commit to GitHub from anywhere \u2014 right from your phone.\n\n"
        "First, let's connect your GitHub account.\n\n"
        "\U0001f4f1 *Your Telegram ID:* `" + telegram_id + "`\n"
        "_(You'll need this for the VS Code extension)_\n\n"
        "Use /auth to sign in with GitHub \u2192",
        parse_mode=ParseMode.MARKDOWN,
    )
    return ConversationHandler.END


# --- /auth Handler - GitHub Device Flow ------------------------------------------------------------

async def auth_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start GitHub Device Flow. User enters a code on github.com/login/device."""
    telegram_id = str(update.effective_user.id)

    # Cancel any existing auth task for this user
    old_task = context.user_data.get("auth_task")
    if old_task and not old_task.done():
        old_task.cancel()
        print(f"[auth] Cancelled previous auth task for {telegram_id}")

    if not GITHUB_CLIENT_ID:
        await update.message.reply_text(
            "[X] GitHub OAuth not configured.\n\n"
            "The bot admin needs to set GITHUB\_CLIENT\_ID env var.",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    await update.message.reply_text("\U0001f504 Contacting GitHub...")

    # Step 1: Request device code
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                DEVICE_CODE_URL,
                data={"client_id": GITHUB_CLIENT_ID, "scope": "repo,read:user"},
                headers={"Accept": "application/json"},
                timeout=10,
            )
        data = resp.json()
    except Exception as e:
        await update.message.reply_text(f"[X] Failed to reach GitHub: {e}")
        return ConversationHandler.END

    if "error" in data:
        await update.message.reply_text(
            f"[X] GitHub error: {data.get('error_description', data['error'])}"
        )
        return ConversationHandler.END

    device_code      = data["device_code"]
    user_code        = data["user_code"]
    verification_uri = data.get("verification_uri", "https://github.com/login/device")
    expires_in       = data.get("expires_in", 900)
    interval         = data.get("interval", 5)

    # Store state
    context.user_data["device_code"] = device_code

    await update.message.reply_text(
        f"[Admin] *Sign in with GitHub*\n\n"
        f"1\u20e3 Open this link:\n"
        f"\U0001f449 [{verification_uri}]({verification_uri})\n\n"
        f"2\u20e3 Enter this code:\n"
        f"```\n{user_code}\n```\n\n"
        f"3\u20e3 Click *Authorize* in the browser\n\n"
        f"_Waiting for authorization (expires in {expires_in // 60} min)..._\n\n"
        f"Send /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

    # Start background polling and store task
    task = asyncio.create_task(_poll_device_auth(
        telegram_id=telegram_id,
        device_code=device_code,
        interval=interval,
        expires_in=expires_in,
        context=context,
        chat_id=update.effective_chat.id,
    ))
    context.user_data["auth_task"] = task
    
    return ConversationHandler.END


async def _poll_device_auth(
    telegram_id: str,
    device_code: str,
    interval: int,
    expires_in: int,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    """Background task: polls GitHub token endpoint until authorized."""
    import time
    deadline = time.time() + expires_in
    poll_interval = interval

    print(f"[_poll_device_auth] Started polling for {telegram_id} (expires in {expires_in}s)")

    try:
        while time.time() < deadline:
            await asyncio.sleep(poll_interval)

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        TOKEN_URL,
                        data={
                            "client_id": GITHUB_CLIENT_ID,
                            "client_secret": GITHUB_CLIENT_SECRET,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        },
                        headers={"Accept": "application/json"},
                        timeout=10,
                    )
                data = resp.json()
            except Exception as e:
                print(f"[_poll_device_auth] Network error: {e}")
                continue

            if "access_token" in data:
                token = data["access_token"]
                username = github_service.get_username(token)
                print(f"[_poll_device_auth] Success for {telegram_id} ({username})")
                
                # Store token - handle new users by providing required default_repo
                user = get_user_by_telegram_id(telegram_id)
                if user:
                    update_github_token(telegram_id, token)
                    if username:
                        update_github_username(telegram_id, username)
                else:
                    upsert_user({
                        "telegram_id": telegram_id, 
                        "github_token": token,
                        "github_username": (username or "").lower() or None,
                        "default_repo": "not-set", # Required column
                        "branch": "main"
                    })

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"\u2705 *GitHub connected!*\n\n"
                        f"Signed in as *{username or 'your account'}*\n\n"
                        f"Now set your repository with:\n"
                        f"`/repo owner/repo-name`"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

            error = data.get("error", "")
            if error == "slow_down":
                poll_interval = data.get("interval", poll_interval + 5)
            elif error == "expired_token":
                print(f"[_poll_device_auth] Token expired for {telegram_id}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="[X] Authorization expired. Use /auth to try again.",
                )
                return
            elif error not in ("authorization_pending", "slow_down", ""):
                print(f"[_poll_device_auth] GitHub error for {telegram_id}: {error}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"[X] GitHub Auth error: `{error}`\nUse /auth to try again.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        print(f"[_poll_device_auth] Deadline reached for {telegram_id}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="\u23f0 Authorization timed out. Use /auth to try again.",
        )
    except asyncio.CancelledError:
        print(f"[_poll_device_auth] Task cancelled for {telegram_id}")
    except Exception as e:
        print(f"[_poll_device_auth] Unexpected crash for {telegram_id}: {e}")
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"[X] Unexpected auth error. Try /auth again.")
        except:
            pass



# --- /repo set handler - /repo owner/name ---------------------------------------------------------

async def set_repo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allow user to set default repo: /repo owner/name"""
    user = await _check_registered(update)
    if not user:
        return

    args = context.args
    if not args or "/" not in args[0]:
        active_repo   = user.get("active_repo")   or user.get("default_repo", "-")
        active_branch = user.get("active_branch") or user.get("branch", "main")
        await update.message.reply_text(
            f"[Repo] *Active Repository*\n\n"
            f"`{active_repo}` \u2022 `{active_branch}`\n\n"
            f"To change: `/repo owner/repo-name`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    telegram_id = str(update.effective_user.id)
    new_repo = args[0].strip()
    await update.message.reply_text("\U0001f50d Checking repo access...")
    token = user.get("github_token")
    result = github_service.validate_token_and_repo(token, new_repo)
    if not result["ok"]:
        await update.message.reply_text(
            f"[X] Cannot access `{new_repo}`: {result.get('message')}\n\n"
            "Make sure the repo exists and your token has access.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    upsert_user({"telegram_id": telegram_id, "default_repo": new_repo, "active_repo": new_repo})
    default_branch = result.get("default_branch", "main")
    await update.message.reply_text(
        f"[OK] Default repo set to `{new_repo}`\n"
        f"Default branch: `{default_branch}`\n\n"
        f"Use /branch to switch branch.",
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END


# --- /repo Handler -------------------------------------------------------------------------------------------

async def repo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _check_registered(update)
    if not user:
        return

    active_repo = user.get("active_repo") or user.get("default_repo", "-")
    active_branch = user.get("active_branch") or user.get("branch", "main")
    default_repo = user.get("default_repo", "-")
    is_auto = bool(user.get("active_repo") and user.get("active_repo") != default_repo)

    source_note = "\U0001f504 Auto-detected from VS Code" if is_auto else "\U0001f4cc Set in configuration"

    await update.message.reply_text(
        f"[Repo] *Active Repository*\n\n"
        f"`{active_repo}` \u2022 `{active_branch}`\n"
        f"{source_note}\n\n"
        f"\U0001f4cc Default repo: `{default_repo}`\n\n"
        f"_Open a different project in VS Code and save a file - "
        f"GitPhone will auto-switch to that repo._\n\n"
        f"Use /branch to switch branch.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"View on GitHub \u2197",
                url=f"https://github.com/{active_repo}"
            )
        ]])
    )


# --- /branch Handler ----------------------------------------------------------------------------------------

async def branch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await _check_registered(update)
    if not user:
        return ConversationHandler.END

    current = user.get("active_branch") or user.get("branch", "main")
    args = context.args

    if args:
        # /branch main - inline switch
        new_branch = args[0].strip()
        update_branch(str(update.effective_user.id), new_branch)
        await update.message.reply_text(
            f"[OK] Branch switched to `{new_branch}`\n\n"
            f"Future commits will go to `{new_branch}`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"[Branch] *Current Branch:* `{current}`\n\n"
        f"Type the branch name to switch, or /cancel:",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_NEW_BRANCH


async def branch_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_branch = update.message.text.strip()
    telegram_id = str(update.effective_user.id)

    if not new_branch or " " in new_branch:
        await update.message.reply_text("[X] Invalid branch name. Try again or /cancel")
        return WAITING_NEW_BRANCH

    update_branch(telegram_id, new_branch)
    await update.message.reply_text(
        f"[OK] Branch switched to `{new_branch}`\n\n"
        f"Future commits will go to `{new_branch}`.",
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END


# --- /unstage Handler ---------------------------------------------------------------------------------------

async def unstage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _check_registered(update)
    if not user:
        return

    telegram_id = str(update.effective_user.id)
    args = context.args

    if not args:
        staged = get_pending_files(telegram_id)
        if not staged:
            await update.message.reply_text("[Empty] No staged files to unstage.")
            return

        file_list = "\n".join(f"\u2022 `{f['filepath']}`" for f in staged[:20])
        await update.message.reply_text(
            f"[Files] *Staged Files:*\n\n{file_list}\n\n"
            f"Usage: `/unstage src/filename.py`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    filepath = " ".join(args).strip()
    found = unstage_file_by_path(telegram_id, filepath)

    if found:
        await update.message.reply_text(
            f"[OK] Unstaged: `{filepath}`\n\n"
            f"The file was removed from your staged list.\n"
            f"It will be re-staged next time you save it in VS Code.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            f"[X] File not found in staged list: `{filepath}`\n\n"
            f"Use /unstage without arguments to see staged files.",
            parse_mode=ParseMode.MARKDOWN
        )


# --- /clear Handler ------------------------------------------------------------------------------------------

async def clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _check_registered(update)
    if not user:
        return

    telegram_id = str(update.effective_user.id)
    staged = get_pending_files(telegram_id)

    if not staged:
        await update.message.reply_text("[Empty] No staged files to clear.")
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"[Clear] Clear All ({len(staged)} files)", callback_data="CLEAR_CONFIRM"),
            InlineKeyboardButton("[X] Cancel", callback_data="COMMIT_CANCEL"),
        ]
    ])
    await update.message.reply_text(
        f"[Warning] *Clear All Staged Files?*\n\n"
        f"This will remove all {len(staged)} staged file(s).\n"
        f"This cannot be undone.\n\n"
        f"Your actual files are safe - only the staged diffs are cleared.",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


async def clear_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    telegram_id = str(update.effective_user.id)
    count = clear_all_staged(telegram_id)
    await query.edit_message_text(
        f"[OK] Cleared {count} staged file(s).\n\n"
        f"Save files in VS Code to re-stage them."
    )


# --- /preview Handler ---------------------------------------------------------------------------------------

async def preview_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _check_registered(update)
    if not user:
        return

    telegram_id = str(update.effective_user.id)
    staged = get_pending_files(telegram_id)

    if not staged:
        await update.message.reply_text(
            "[Empty] No staged files to preview.\n\n"
            "Save files in VS Code to stage them."
        )
        return

    # Show diff snippets for first 5 files
    lines = [f"\U0001f441 *Diff Preview* - {len(staged)} file(s) staged\n"]
    for f in staged[:5]:
        filepath = f["filepath"]
        size = _format_file_size(f.get("file_size", 0))
        diff = f.get("diff", "")

        # Show first 8 diff lines
        if diff:
            diff_lines = diff.split("\n")[:8]
            snippet = "\n".join(diff_lines)
            # Truncate if too long
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
        else:
            snippet = "(binary file)"

        lines.append(f"`{filepath}` ({size})\n```\n{snippet}\n```")

    if len(staged) > 5:
        lines.append(f"_...and {len(staged) - 5} more file(s)_")

    lines.append("\nUse /files to select and commit.")

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.MARKDOWN
    )


# --- /files Handler (grouped by repo) -------------------------------------------------------------

async def files_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await _check_registered(update)
    if not user:
        return ConversationHandler.END

    telegram_id = str(update.effective_user.id)
    grouped = get_pending_files_by_repo(telegram_id)

    if not grouped:
        active_repo = user.get("active_repo") or user.get("default_repo", "-")
        active_branch = user.get("active_branch") or user.get("branch", "main")
        await update.message.reply_text(
            "[Empty] *No files staged yet.*\n\n"
            "Save a file in VS Code and it will appear here automatically.\n\n"
            f"Active: `{active_repo}` \u2022 `{active_branch}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    # Build flat list with repo context
    all_files = []
    for repo, files in grouped.items():
        for f in files:
            f["_repo"] = repo  # tag each file with its repo
            all_files.append(f)

    context.user_data["staged_data"] = {f["id"]: f for f in all_files}
    context.user_data["selected_files"] = set()

    # Build header showing repos
    if len(grouped) == 1:
        repo_name = list(grouped.keys())[0]
        branch = user.get("active_branch") or user.get("branch", "main")
        header = f"[Files] *{repo_name}* \u2022 `{branch}`\n\nSelect files to commit:"
    else:
        repo_summary = "\n".join(
            f"  [Repo] `{r}` - {len(files)} file(s)"
            for r, files in grouped.items()
        )
        header = f"[Files] *{len(grouped)} Repos* staged:\n{repo_summary}\n\nSelect files to commit:"

    keyboard = _build_files_keyboard(all_files, set())
    await update.message.reply_text(
        header,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    return SELECTING_FILES


async def file_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    file_id = query.data.split(":", 1)[1]
    selected: set = context.user_data.get("selected_files", set())
    staged_data: dict = context.user_data.get("staged_data", {})

    if file_id in selected:
        selected.discard(file_id)
    else:
        selected.add(file_id)
    context.user_data["selected_files"] = selected

    staged_files = list(staged_data.values())
    keyboard = _build_files_keyboard(staged_files, selected)

    user = get_user_by_telegram_id(str(update.effective_user.id))
    active_repo = user.get("active_repo") or user.get("default_repo", "-")
    branch = user.get("active_branch") or user.get("branch", "main")
    try:
        await query.edit_message_text(
            f"[Files] *{active_repo}* \u2022 `{branch}`\n\nSelect files to commit:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass
    return SELECTING_FILES


async def file_select_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    staged_data: dict = context.user_data.get("staged_data", {})
    selected = set(staged_data.keys())
    context.user_data["selected_files"] = selected

    staged_files = list(staged_data.values())
    keyboard = _build_files_keyboard(staged_files, selected)

    user = get_user_by_telegram_id(str(update.effective_user.id))
    active_repo = user.get("active_repo") or user.get("default_repo", "-")
    branch = user.get("active_branch") or user.get("branch", "main")
    try:
        await query.edit_message_text(
            f"[Files] *{active_repo}* \u2022 `{branch}`\n\nSelect files to commit:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass
    return SELECTING_FILES


async def done_selecting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    selected: set = context.user_data.get("selected_files", set())
    staged_data: dict = context.user_data.get("staged_data", {})

    if not selected:
        await query.answer("[Warning] No files selected. Tap files to toggle.", show_alert=True)
        return SELECTING_FILES

    selected_names = [staged_data[fid]["filepath"] for fid in selected if fid in staged_data]
    files_display = "\n".join(f"\u2022 `{f}`" for f in selected_names)

    await query.edit_message_text(
        f"\u270f\ufe0f *Type your commit message:*\n\n"
        f"Selected:\n{files_display}\n\n"
        f'_(e.g. "fix: updated auth logic")_',
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_MESSAGE


async def commit_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message.text.strip()
    if not message:
        await update.message.reply_text("[Warning] Commit message cannot be empty. Try again:")
        return WAITING_MESSAGE

    context.user_data["commit_message"] = message

    # After commit message - show branch picker
    telegram_id = str(update.effective_user.id)
    user = get_user_by_telegram_id(telegram_id)
    active_repo   = user.get("active_repo") or user.get("default_repo", "")
    current_branch = user.get("active_branch") or user.get("branch", "main")
    token = user.get("github_token", "")

    # Fetch existing branches from GitHub
    branches = github_service.list_branches(token, active_repo) if token and active_repo else []
    default_branch = github_service.get_default_branch(token, active_repo) if token and active_repo else "main"

    # Build branch picker keyboard
    buttons = []
    # First: current branch (most likely choice)
    current_label = f"[OK] {current_branch} (current)"
    buttons.append([InlineKeyboardButton(current_label, callback_data=f"BRANCH_PICK:{current_branch}")])
    # Other branches (skip current to avoid duplicate)
    for b in branches[:8]:
        if b != current_branch:
            is_default = " (default)" if b == default_branch else ""
            buttons.append([InlineKeyboardButton(f"[Branch] {b}{is_default}", callback_data=f"BRANCH_PICK:{b}")])
    # Always offer create new
    buttons.append([InlineKeyboardButton("\u2795 Create new branch...", callback_data="BRANCH_NEW")])
    buttons.append([InlineKeyboardButton("[X] Cancel", callback_data="COMMIT_CANCEL")])

    selected_names = [
        context.user_data["staged_data"][fid]["filepath"]
        for fid in context.user_data.get("selected_files", set())
        if fid in context.user_data.get("staged_data", {})
    ]
    files_display = "\n".join(f"\u2022 `{f}`" for f in selected_names[:5])
    if len(selected_names) > 5:
        files_display += f"\n_...and {len(selected_names) - 5} more_"

    await update.message.reply_text(
        f"[Branch] *Choose branch to commit to:*\n\n"
        f"[Repo] `{active_repo}`\n"
        f"\U0001f4ac `{message}`\n\n"
        f"Files:\n{files_display}",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN
    )
    return SELECTING_BRANCH


async def branch_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User selected an existing branch from the picker."""
    query = update.callback_query
    await query.answer()

    chosen_branch = query.data.split(":", 1)[1]
    context.user_data["commit_branch"] = chosen_branch

    selected = context.user_data.get("selected_files", set())
    staged_data = context.user_data.get("staged_data", {})
    selected_names = [staged_data[fid]["filepath"] for fid in selected if fid in staged_data]
    files_display = "\n".join(f"\u2022 `{f}`" for f in selected_names)
    message = context.user_data.get("commit_message", "")
    telegram_id = str(update.effective_user.id)
    user = get_user_by_telegram_id(telegram_id)
    active_repo = user.get("active_repo") or user.get("default_repo", "")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f680 Commit Now", callback_data="COMMIT_NOW"),
            InlineKeyboardButton("[X] Cancel", callback_data="COMMIT_CANCEL"),
        ]
    ])
    await query.edit_message_text(
        f"[Repo] *Review Commit*\n\n"
        f"Files:\n{files_display}\n\n"
        f"\U0001f4ac `{message}`\n"
        f"[Branch] `{chosen_branch}` \u2022 `{active_repo}`\n\n"
        f"Ready to commit?",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    return CONFIRM_COMMIT


async def branch_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User wants to create a new branch."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "[Branch] *New Branch Name*\n\n"
        "Type the branch name (e.g. `feature/my-fix`):\n\n"
        "_No spaces. Use - or / as separators._",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_NEW_BR_NAME


async def new_branch_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed a new branch name."""
    branch_name = update.message.text.strip()
    if not branch_name or " " in branch_name:
        await update.message.reply_text(
            "[X] Invalid branch name (no spaces allowed).\n\nTry again:"
        )
        return WAITING_NEW_BR_NAME

    telegram_id = str(update.effective_user.id)
    user = get_user_by_telegram_id(telegram_id)
    token = user.get("github_token", "")
    active_repo   = user.get("active_repo") or user.get("default_repo", "")
    default_branch = github_service.get_default_branch(token, active_repo)

    await update.message.reply_text(f"\U0001f528 Creating branch `{branch_name}`...",
                                     parse_mode=ParseMode.MARKDOWN)

    result = github_service.create_branch(token, active_repo, branch_name, from_branch=default_branch)
    if not result["ok"]:
        if result.get("error") == "branch_exists":
            await update.message.reply_text(
                f"\u2139\ufe0f Branch `{branch_name}` already exists \u2014 will commit to it.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"[X] Failed to create branch: {result.get('message')}\n\n"
                "Try a different name or /cancel"
            )
            return WAITING_NEW_BR_NAME

    context.user_data["commit_branch"] = branch_name

    selected = context.user_data.get("selected_files", set())
    staged_data = context.user_data.get("staged_data", {})
    selected_names = [staged_data[fid]["filepath"] for fid in selected if fid in staged_data]
    files_display = "\n".join(f"\u2022 `{f}`" for f in selected_names)
    message = context.user_data.get("commit_message", "")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f680 Commit Now", callback_data="COMMIT_NOW"),
            InlineKeyboardButton("[X] Cancel", callback_data="COMMIT_CANCEL"),
        ]
    ])
    await update.message.reply_text(
        f"[OK] Branch `{branch_name}` ready!\n\n"
        f"[Repo] *Review Commit*\n\n"
        f"Files:\n{files_display}\n\n"
        f"\U0001f4ac `{message}`\n"
        f"[Branch] `{branch_name}` \u2022 `{active_repo}`\n\n"
        f"Ready to commit?",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    return CONFIRM_COMMIT


async def protected_branch_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed a new branch name after hit a protected branch error."""
    new_branch = update.message.text.strip()
    if not new_branch or " " in new_branch:
        await update.message.reply_text("[X] Invalid branch name. Try again or /cancel")
        return WAITING_PROTECTED_BRANCH_NAME

    telegram_id = str(update.effective_user.id)
    user = get_user_by_telegram_id(telegram_id)
    token = user.get("github_token", "")
    active_repo = user.get("active_repo") or user.get("default_repo", "")
    default_branch = github_service.get_default_branch(token, active_repo)

    await update.message.reply_text(f"\U0001f528 Creating branch `{new_branch}` and committing...",
                                     parse_mode=ParseMode.MARKDOWN)

    # Create the branch
    br_res = github_service.create_branch(token, active_repo, new_branch, from_branch=default_branch)
    if not br_res["ok"] and br_res.get("error") != "branch_exists":
        await update.message.reply_text(f"[X] Failed to create branch: {br_res.get('message')}")
        return WAITING_PROTECTED_BRANCH_NAME

    # Direct commit to this new branch
    context.user_data["commit_branch"] = new_branch
    # Reuse commit_now logic by calling it manually (with a fake update/query) or just redirecting
    # Actually, it's better to just finish this state and tell user to click commit again,
    # OR we can just trigger the commit here.
    # To keep it simple and safe, let's show the review screen again with the new branch.
    
    selected = context.user_data.get("selected_files", set())
    staged_data = context.user_data.get("staged_data", {})
    selected_names = [staged_data[fid]["filepath"] for fid in selected if fid in staged_data]
    files_display = "\n".join(f"\u2022 `{f}`" for f in selected_names)
    message = context.user_data.get("commit_message", "")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f680 Commit Now", callback_data="COMMIT_NOW"),
            InlineKeyboardButton("[X] Cancel", callback_data="COMMIT_CANCEL"),
        ]
    ])
    await update.message.reply_text(
        f"[OK] Branch `{new_branch}` created!\n\n"
        f"[Repo] *Review Commit*\n\n"
        f"Files:\n{files_display}\n\n"
        f"\U0001f4ac `{message}`\n"
        f"[Branch] `{new_branch}` \u2022 `{active_repo}`\n\n"
        f"Ready to commit?",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    return CONFIRM_COMMIT


async def commit_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("\u23f3 Committing...")

    telegram_id = str(update.effective_user.id)
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        await query.edit_message_text("[X] User not found. Please /start again.")
        return ConversationHandler.END

    active_repo   = user.get("active_repo") or user.get("default_repo")
    # Use the branch selected in the branch picker (if any), else user's active branch
    active_branch = context.user_data.get("commit_branch") or user.get("active_branch") or user.get("branch", "main")
    
    # Fetch default branch to know if we need a PR
    default_branch = github_service.get_default_branch(user["github_token"], active_repo)

    selected: set = context.user_data.get("selected_files", set())
    staged_data: dict = context.user_data.get("staged_data", {})
    commit_message: str = context.user_data.get("commit_message", "GitPhone commit")

    file_ids = [fid for fid in selected if fid in staged_data]
    staged_rows = get_staged_files_by_ids(file_ids)

    if not staged_rows:
        await query.edit_message_text("[X] Could not load staged files. Try /files again.")
        return ConversationHandler.END

    result = github_service.commit_files(
        token=user["github_token"],
        repo_name=active_repo,
        branch=active_branch,
        staged_files=staged_rows,
        commit_message=commit_message,
    )

    if result["ok"]:
        commit_sha = result["commit_sha"]
        short_sha = commit_sha[:7] if commit_sha else "unknown"
        committed_ids = result.get("committed_ids", [])
        
        # Only mark files that were ACTUALLY committed as 'committed'
        mark_files_committed(committed_ids)
        
        # Log only committed files
        committed_rows = [r for r in staged_rows if r["id"] in committed_ids]
        committed_paths = [r["filepath"] for r in committed_rows]

        insert_commit_log({
            "telegram_id": telegram_id,
            "user_id": user["id"],
            "commit_sha": commit_sha or "unknown",
            "message": commit_message,
            "files": committed_paths,
            "repo": active_repo,
            "branch": active_branch,
            "was_scheduled": False,
        })

        await channel_logger.log_commit(
            telegram_id=telegram_id,
            repo=active_repo,
            branch=active_branch,
            commit_sha=commit_sha or "unknown",
            message=commit_message,
            files=committed_paths,
            was_forced=False,
        )

        # Clear selection on success
        context.user_data["selected_files"] = set()

        conflict_note = ""
        if result.get("conflict_files"):
            conflict_note = (
                f"\n\n[Warning] Skipped (conflict): "
                + ", ".join(f"`{f}`" for f in result["conflict_files"])
            )

        # If committed to a non-default branch, offer PR creation
        pr_note = ""
        pr_button = None
        if active_branch != default_branch:
            pr_result = github_service.create_pull_request(
                token=user["github_token"],
                repo_name=active_repo,
                head=active_branch,
                base=default_branch,
                title=commit_message,
            )
            if pr_result["ok"]:
                pr_url = pr_result["pr_url"]
                pr_num = pr_result["number"]
                pr_note = f"\n\n\U0001f500 PR #{pr_num} created \u2192 ready to merge"
                pr_button = InlineKeyboardButton("Open PR on GitHub \u2197", url=pr_url)

        commit_url = f"https://github.com/{active_repo}/commit/{commit_sha}"
        buttons = []
        if pr_button:
            # If it's a PR, only show the PR merge link
            buttons.append([pr_button])
        else:
            buttons.append([InlineKeyboardButton("View Commit [Link]", url=commit_url)])

        await query.edit_message_text(
            f"\u2705 *Committed!*\n\n"
            f"[Link] [`{short_sha}`]({commit_url})\n"
            f"\U0001f4ac {commit_message}\n"
            f"[Branch] `{active_branch}` \u2022 `{active_repo}`\n"
            f"[Time] Just now{conflict_note}{pr_note}",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )

    elif result.get("error") == "conflict":
        conflict_files = result.get("conflict_files", [])
        conflict_display = "\n".join(f"\u2022 `{f}`" for f in conflict_files)
        context.user_data["staged_rows_for_force"] = staged_rows
        context.user_data["file_ids_for_force"] = file_ids

        await channel_logger.log_conflict(
            telegram_id=telegram_id,
            repo=active_repo,
            conflict_files=conflict_files,
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001f504 Force Commit (overwrite)", callback_data="COMMIT_FORCE")],
            [InlineKeyboardButton("[X] Cancel", callback_data="COMMIT_CANCEL")],
        ])
        await query.edit_message_text(
            f"[Warning] *Conflict Detected*\n\n"
            f"{conflict_display}\n\n"
            f"These files were modified on GitHub after staging.\n\n"
            f"What would you like to do?",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return CONFIRM_COMMIT

    elif result.get("error") == "branch_protected":
        # Protected branch - offer to name a NEW branch immediately
        await channel_logger.log_commit_failed(telegram_id, active_repo, "branch_protected")
        await query.edit_message_text(
            f"Locked: *Branch `{active_branch}` is protected.*\n\n"
            f"Direct pushes are not allowed. Please type a name for a *new branch* to commit to instead:\n\n"
            f"_(e.g. `patch-1` or `fix/auth`)_",
            parse_mode=ParseMode.MARKDOWN
        )
        return WAITING_PROTECTED_BRANCH_NAME

    else:
        error_msg = result.get('message', 'Unknown error')
        await channel_logger.log_commit_failed(telegram_id, active_repo, error_msg)
        await query.edit_message_text(
            f"[X] *Commit failed.*\n\n"
            f"Error: {error_msg}\n\n"
            f"Your staged files are safe. Try /files again."
        )

    context.user_data.clear()
    return ConversationHandler.END


async def commit_force_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("[Wait] Force committing...")

    telegram_id = str(update.effective_user.id)
    user = get_user_by_telegram_id(telegram_id)
    staged_rows = context.user_data.get("staged_rows_for_force", [])
    file_ids = context.user_data.get("file_ids_for_force", [])
    commit_message = context.user_data.get("commit_message", "GitPhone force commit")

    if not staged_rows or not user:
        await query.edit_message_text("[X] Session expired. Please try /files again.")
        return ConversationHandler.END

    active_repo = user.get("active_repo") or user.get("default_repo")
    active_branch = user.get("active_branch") or user.get("branch", "main")

    result = github_service.force_commit_files(
        token=user["github_token"],
        repo_name=active_repo,
        branch=active_branch,
        staged_files=staged_rows,
        commit_message=commit_message,
    )

    if result["ok"]:
        commit_sha = result["commit_sha"]
        short_sha = commit_sha[:7] if commit_sha else "unknown"
        committed_ids = result.get("committed_ids", [])
        
        # Mark files as committed
        mark_files_committed(committed_ids)
        
        # Log only committed files
        committed_rows = [r for r in staged_rows if r["id"] in committed_ids]
        committed_paths = [r["filepath"] for r in committed_rows]

        insert_commit_log({
            "telegram_id": telegram_id,
            "user_id": user["id"],
            "commit_sha": commit_sha or "unknown",
            "message": commit_message,
            "files": committed_paths,
            "repo": active_repo,
            "branch": active_branch,
            "was_scheduled": False,
        })
        await channel_logger.log_commit(
            telegram_id=telegram_id,
            repo=active_repo,
            branch=active_branch,
            commit_sha=commit_sha or "unknown",
            message=commit_message,
            files=committed_paths,
            was_forced=True,
        )
        
        # Clear selection
        context.user_data["selected_files"] = set()

        await query.edit_message_text(
            f"[OK] *Force committed!*\n\n"
            f"[Link] [`{short_sha}`](https://github.com/{active_repo}/commit/{commit_sha})\n"
            f"\U0001f4ac {commit_message}\n"
            f"[Branch] `{active_branch}` \u2022 `{active_repo}`",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        error_msg = result.get('message', 'Unknown error')
        await channel_logger.log_commit_failed(telegram_id, active_repo, error_msg)
        await query.edit_message_text(f"[X] Force commit failed: {error_msg}")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_commit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        "[OK] Cancelled.\nNo changes were made.\n\nUse /files to start a new commit."
    )
    return ConversationHandler.END


# --- /cancel Command ------------------------------------------------------------------------------------------

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "[OK] Cancelled.\nNo changes were made.\n\nUse /files to start a new commit."
    )
    return ConversationHandler.END


# --- /log Command ---------------------------------------------------------------------------------------------

async def log_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _check_registered(update)
    if not user:
        return

    commits = get_recent_commits(str(update.effective_user.id), limit=10)
    if not commits:
        await update.message.reply_text(
            "[Empty] No commits yet via GitPhone.\n\n"
            "Stage files in VS Code, then use /files to commit."
        )
        return

    active_repo = user.get("active_repo") or user.get("default_repo", "-")
    lines = [f"\U0001f4dc *Recent Commits* (`{active_repo}`)\n"]
    for i, c in enumerate(commits, 1):
        short_sha = c["commit_sha"][:7]
        files_str = ", ".join(c.get("files", []))[:60]
        time_str = _time_ago(c.get("committed_at", ""))
        repo = c.get("repo", active_repo)
        lines.append(
            f"{i}. `{short_sha}` - {time_str}\n"
            f"   {c['message']}\n"
            f"   _`{repo}` \u2022 {files_str}_"
        )

    active_branch = user.get("active_branch") or user.get("branch", "main")
    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"View on GitHub \u2197",
                url=f"https://github.com/{active_repo}/commits/{active_branch}"
            )
        ]])
    )


# --- /status Command ------------------------------------------------------------------------------------------

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _check_registered(update)
    if not user:
        return

    telegram_id = str(update.effective_user.id)
    staged = get_pending_files(telegram_id)
    commits = get_recent_commits(telegram_id, limit=100)
    last_sync = _time_ago(user.get("last_active", ""))

    active_repo = user.get("active_repo") or user.get("default_repo", "-")
    active_branch = user.get("active_branch") or user.get("branch", "main")
    default_repo = user.get("default_repo", "-")

    auto_note = ""
    if user.get("active_repo") and user.get("active_repo") != default_repo:
        auto_note = f"\n\U0001f4e1 Auto-detected from VS Code"

    await update.message.reply_text(
        f"[Stats] *GitPhone Status*\n\n"
        f"[User] Registered: [OK]\n"
        f"[Repo] Repo: `{active_repo}`{auto_note}\n"
        f"[Branch] Branch: `{active_branch}`\n"
        f"[Link] GitHub: Connected [OK]\n\n"
        f"[Files] Staged files: {len(staged)} pending\n"
        f"[Time] Last sync: {last_sync}\n"
        f"[Logs] Total commits via GitPhone: {len(commits)}\n\n"
        f"Use /repo to see repo details, /files to commit.",
        parse_mode=ParseMode.MARKDOWN
    )


# --- /help Command ---------------------------------------------------------------------------------------------

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = str(update.effective_user.id)
    is_admin = _is_admin(telegram_id)

    user_commands = (
        "\U0001f6e0 *GitPhone Commands*\n\n"
        "[Files] *Staging & Commits*\n"
        "/files   - Select staged files & commit\n"
        "/preview - Preview diffs before committing\n"
        "/unstage - Remove a file from staged list\n"
        "/clear   - Clear all staged files\n\n"
        "[Repo] *Repo & Branch*\n"
        "/repo    - Show active repo (auto-detected)\n"
        "/branch  - Switch branch\n"
        "/log     - Recent commit history\n"
        "/status  - Connection & repo status\n\n"
        "\u2699\ufe0f *Account*\n"
        "/auth    - Update GitHub token\n"
        "/start   - Setup or reconfigure\n"
        "/cancel  - Cancel current operation\n"
        "/help    - This message\n\n"
        "\U0001f4a1 *Tip:* Save any file in VS Code - it auto-stages and "
        "the repo is auto-detected from your git remote."
    )

    admin_commands = (
        "\n\n[Admin] *Admin Commands*\n"
        "/ban `<id>` `[reason]` - Ban a user\n"
        "/unban `<id>` - Restore a user\n"
        "/users `[page]` - List all users\n"
        "/broadcast `<msg>` - Message all users\n"
        "/stats - Platform statistics\n"
        "/revoke `<id>` - Force user to re-auth"
    )

    await update.message.reply_text(
        user_commands + (admin_commands if is_admin else ""),
        parse_mode=ParseMode.MARKDOWN
    )


# --- Admin Commands ------------------------------------------------------------------------------------------

async def admin_ban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = str(update.effective_user.id)
    if not _is_admin(telegram_id):
        await update.message.reply_text("[Banned] Admin only.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/ban <telegram_id> [reason]`", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = args[0]
    reason = " ".join(args[1:]) if len(args) > 1 else "Banned by admin"

    target = get_user_by_telegram_id(target_id)
    if not target:
        await update.message.reply_text(f"[X] User `{target_id}` not found.", parse_mode=ParseMode.MARKDOWN)
        return

    ok = ban_user(target_id, reason)
    if ok:
        await update.message.reply_text(
            f"[OK] User `{target_id}` banned.\nReason: {reason}",
            parse_mode=ParseMode.MARKDOWN
        )
        try:
            await context.bot.send_message(
                chat_id=int(target_id),
                text="[Banned] Your GitPhone account has been suspended.\nContact support to appeal."
            )
        except Exception:
            pass
    else:
        await update.message.reply_text(f"[X] Failed to ban `{target_id}`.", parse_mode=ParseMode.MARKDOWN)


async def admin_unban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = str(update.effective_user.id)
    if not _is_admin(telegram_id):
        await update.message.reply_text("[Banned] Admin only.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/unban <telegram_id>`", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = args[0]
    ok = unban_user(target_id)
    if ok:
        await update.message.reply_text(f"[OK] User `{target_id}` unbanned.", parse_mode=ParseMode.MARKDOWN)
        try:
            await context.bot.send_message(
                chat_id=int(target_id),
                text="[OK] Your GitPhone account has been reinstated. You can use /files again."
            )
        except Exception:
            pass
    else:
        await update.message.reply_text(f"[X] User `{target_id}` not found.", parse_mode=ParseMode.MARKDOWN)


async def admin_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = str(update.effective_user.id)
    if not _is_admin(telegram_id):
        await update.message.reply_text("[Banned] Admin only.")
        return

    args = context.args
    page = int(args[0]) - 1 if args and args[0].isdigit() else 0
    page_size = 10

    users = get_all_users(limit=page_size, offset=page * page_size)
    if not users:
        await update.message.reply_text("[Empty] No users found.")
        return

    lines = [f"[Users] *Users* (page {page + 1})\n"]
    for u in users:
        repo = u.get("active_repo") or u.get("default_repo", "-")
        status = "[Banned]" if u.get("status") == "banned" else "[OK]"
        last = _time_ago(u.get("last_active", ""))
        lines.append(f"{status} `{u['telegram_id']}` - `{repo}` - {last}")

    lines.append(f"\n_Use /users {page + 2} for next page_")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = str(update.effective_user.id)
    if not _is_admin(telegram_id):
        await update.message.reply_text("[Banned] Admin only.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/broadcast <message>`", parse_mode=ParseMode.MARKDOWN)
        return

    message = " ".join(args)
    users = get_all_users(limit=1000)

    sent = 0
    failed = 0
    for u in users:
        if u.get("status") == "banned":
            continue
        try:
            await context.bot.send_message(
                chat_id=int(u["telegram_id"]),
                text=f"[Broadcast] *GitPhone Announcement*\n\n{message}",
                parse_mode=ParseMode.MARKDOWN
            )
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"[OK] Broadcast sent!\n"
        f"\u2709\ufe0f Delivered: {sent}\n"
        f"[X] Failed: {failed}"
    )


async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = str(update.effective_user.id)
    if not _is_admin(telegram_id):
        await update.message.reply_text("[Banned] Admin only.")
        return

    stats = count_stats()
    await update.message.reply_text(
        f"[Stats] *GitPhone Stats*\n\n"
        f"[Users] Users: {stats.get('total_users', 0)} registered\n"
        f"[Banned] Banned: {stats.get('banned_users', 0)}\n"
        f"[Files] Staged: {stats.get('pending_files', 0)} pending files\n"
        f"[Logs] Commits: {stats.get('total_commits', 0)} total",
        parse_mode=ParseMode.MARKDOWN
    )


async def admin_revoke_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = str(update.effective_user.id)
    if not _is_admin(telegram_id):
        await update.message.reply_text("[Banned] Admin only.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/revoke <telegram_id>`", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = args[0]
    ok = revoke_api_key(target_id)
    if ok:
        await update.message.reply_text(
            f"[OK] API key revoked for `{target_id}`.\n"
            f"User must re-connect the VS Code extension.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(f"[X] User `{target_id}` not found.", parse_mode=ParseMode.MARKDOWN)


# --- Conversation Handler Builders (exported to main.py) ----------------------------------

def build_start_conversation() -> ConversationHandler:
    """
    /start no longer has a multi-step flow.
    New users are directed to /auth (Device Flow) instead of entering a PAT.
    No states needed - start_handler always returns ConversationHandler.END.
    """
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_handler)],
        states={},
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True,
    )


def build_files_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("files", files_handler)],
        states={
            SELECTING_FILES: [
                CallbackQueryHandler(file_toggle_callback, pattern=r"^FILE_TOGGLE:"),
                CallbackQueryHandler(file_select_all_callback, pattern=r"^FILE_SELECT_ALL$"),
                CallbackQueryHandler(done_selecting_callback, pattern=r"^FILE_DONE$"),
            ],
            WAITING_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, commit_message_handler),
            ],
            # Branch picker after commit message
            SELECTING_BRANCH: [
                CallbackQueryHandler(branch_pick_callback, pattern=r"^BRANCH_PICK:"),
                CallbackQueryHandler(branch_new_callback, pattern=r"^BRANCH_NEW$"),
                CallbackQueryHandler(cancel_commit_callback, pattern=r"^COMMIT_CANCEL$"),
            ],
            WAITING_NEW_BR_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_branch_name_handler),
            ],
            WAITING_PROTECTED_BRANCH_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, protected_branch_name_handler),
            ],
            CONFIRM_COMMIT: [
                CallbackQueryHandler(commit_now_callback, pattern=r"^COMMIT_NOW$"),
                CallbackQueryHandler(commit_force_callback, pattern=r"^COMMIT_FORCE$"),
                CallbackQueryHandler(cancel_commit_callback, pattern=r"^COMMIT_CANCEL$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True,
    )


def build_auth_conversation() -> ConversationHandler:
    """Device Flow /auth - no states needed, polling runs as background task."""
    return ConversationHandler(
        entry_points=[CommandHandler("auth", auth_handler)],
        states={},
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True,
    )


def build_branch_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("branch", branch_handler)],
        states={
            WAITING_NEW_BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, branch_name_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True,
    )
