"""
admin.py - Admin-only Telegram bot commands for GitPhone.
Only works for ADMIN_TELEGRAM_ID set in environment variables.

Commands:
  /admin_stats     - Global platform stats
  /admin_users     - List all registered users
  /admin_user <id> - Inspect a specific user by telegram_id
  /admin_ban <id>  - Ban a user (marks status = banned)
  /admin_unban <id>- Unban a user (marks status = active)
  /admin_broadcast - Broadcast message to all active users
  /admin_ping      - Backend health check
"""

import os
from datetime import datetime, timezone
from functools import wraps

import channel_logger
from supabase_service import (
    get_client,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# --- Admin Guard ----------------------------------------------------------------------------------------------

def get_admin_ids() -> set[str]:
    """Returns set of admin telegram IDs from env var (comma-separated)."""
    raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
    return {tid.strip() for tid in raw.split(",") if tid.strip()}


def is_admin(telegram_id: str) -> bool:
    return telegram_id in get_admin_ids()


def admin_only(func):
    """Decorator - silently ignores non-admin callers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        caller = str(update.effective_user.id)
        if not is_admin(caller):
            await update.message.reply_text("[X] Unauthorized.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


# --- Admin Supabase Queries ------------------------------------------------------------------------------

def admin_get_global_stats() -> dict:
    """Pull aggregate stats across all users."""
    try:
        db = get_client()
        total_users   = db.table("users").select("id", count="exact").execute()
        active_users  = db.table("users").select("id", count="exact").eq("status", "active").execute()
        dormant_users = db.table("users").select("id", count="exact").eq("status", "dormant").execute()
        banned_users  = db.table("users").select("id", count="exact").eq("status", "banned").execute()
        staged_total  = db.table("staged_files").select("id", count="exact").eq("status", "pending").execute()
        commits_total = db.table("commit_log").select("id", count="exact").execute()

        # Most active user (most commits)
        top_committer_res = (
            db.table("commit_log")
            .select("telegram_id")
            .execute()
        )
        top_map: dict[str, int] = {}
        for row in (top_committer_res.data or []):
            tid = row["telegram_id"]
            top_map[tid] = top_map.get(tid, 0) + 1
        top_user = max(top_map, key=top_map.get) if top_map else "-"
        top_count = top_map.get(top_user, 0)

        return {
            "total_users":   total_users.count   or 0,
            "active_users":  active_users.count  or 0,
            "dormant_users": dormant_users.count  or 0,
            "banned_users":  banned_users.count   or 0,
            "staged_total":  staged_total.count  or 0,
            "commits_total": commits_total.count or 0,
            "top_user":      top_user,
            "top_count":     top_count,
        }
    except Exception as e:
        print(f"[admin] get_global_stats error: {e}")
        return {}


def admin_get_all_users(limit: int = 20, offset: int = 0) -> list[dict]:
    """Returns paginated list of all users."""
    try:
        result = get_client().table("users") \
            .select("telegram_id, default_repo, branch, status, last_active, created_at, ping_count") \
            .order("created_at", desc=True) \
            .range(offset, offset + limit - 1) \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[admin] get_all_users error: {e}")
        return []


def admin_get_user_detail(telegram_id: str) -> dict | None:
    """Full detail for one user including commit + staged counts."""
    try:
        db = get_client()
        user_res = db.table("users").select("*").eq("telegram_id", telegram_id).execute()
        if not user_res.data:
            return None
        user = user_res.data[0]

        staged_res = db.table("staged_files").select("id", count="exact") \
            .eq("telegram_id", telegram_id).eq("status", "pending").execute()
        commits_res = db.table("commit_log").select("id", count="exact") \
            .eq("telegram_id", telegram_id).execute()

        user["staged_count"]  = staged_res.count or 0
        user["commits_count"] = commits_res.count or 0
        return user
    except Exception as e:
        print(f"[admin] get_user_detail error: {e}")
        return None


def admin_set_user_status(telegram_id: str, status: str) -> bool:
    """Set status field on a user. Returns True on success."""
    try:
        get_client().table("users") \
            .update({"status": status}) \
            .eq("telegram_id", telegram_id) \
            .execute()
        return True
    except Exception as e:
        print(f"[admin] set_user_status error: {e}")
        return False


def admin_get_recent_activity(limit: int = 10) -> list[dict]:
    """Returns the most recent commits across ALL users."""
    try:
        result = get_client().table("commit_log") \
            .select("telegram_id, commit_sha, message, repo, committed_at") \
            .order("committed_at", desc=True) \
            .limit(limit) \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[admin] get_recent_activity error: {e}")
        return []


def admin_get_all_active_telegram_ids() -> list[str]:
    """Get telegram_ids of all active (non-banned, non-dormant) users for broadcast."""
    try:
        result = get_client().table("users") \
            .select("telegram_id") \
            .eq("status", "active") \
            .execute()
        return [row["telegram_id"] for row in (result.data or [])]
    except Exception as e:
        print(f"[admin] get_all_active_telegram_ids error: {e}")
        return []


# --- Helper ------------------------------------------------------------------------------------------------------

def _time_ago(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        s = int(diff.total_seconds())
        if s < 60:
            return "just now"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return "unknown"


STATUS_EMOJI = {
    "active":      "[OK]",
    "inactive_7d": "[Wait]",
    "dormant":     "[Error]",
    "banned":      "[Banned]",
}


# --- /admin_stats ---------------------------------------------------------------------------------------------

@admin_only
async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("[Stats] Fetching global stats...")
    stats = admin_get_global_stats()
    if not stats:
        await update.message.reply_text("[X] Failed to fetch stats.")
        return

    await update.message.reply_text(
        f"[Stats] *GitPhone - Global Stats*\n\n"
        f"[Users] *Users*\n"
        f"  Total:   `{stats['total_users']}`\n"
        f"  [OK] Active:  `{stats['active_users']}`\n"
        f"  [Error] Dormant: `{stats['dormant_users']}`\n"
        f"  [Banned] Banned:  `{stats['banned_users']}`\n\n"
        f"[Files] *Activity*\n"
        f"  Staged (pending):  `{stats['staged_total']}`\n"
        f"  Total commits:     `{stats['commits_total']}`\n\n"
        f"[Top] *Top Committer*\n"
        f"  `{stats['top_user']}` - `{stats['top_count']}` commits",
        parse_mode=ParseMode.MARKDOWN
    )


# --- /admin_users ---------------------------------------------------------------------------------------------

@admin_only
async def admin_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Parse optional page number: /admin_users 2
    args = context.args or []
    page = int(args[0]) if args and args[0].isdigit() else 1
    limit = 10
    offset = (page - 1) * limit

    users = admin_get_all_users(limit=limit, offset=offset)
    if not users:
        await update.message.reply_text("[Empty] No users found.")
        return

    lines = [f"[Users] *All Users* (page {page})\n"]
    for u in users:
        emoji = STATUS_EMOJI.get(u.get("status", "active"), "[?]")
        last  = _time_ago(u.get("last_active", ""))
        lines.append(
            f"{emoji} `{u['telegram_id']}`\n"
            f"   [Repo] {u.get('default_repo','-')} \u2022 {u.get('branch','-')}\n"
            f"   [Time] {last}"
        )

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(f"< Page {page-1}", callback_data=f"ADMIN_USERS:{page-1}"))
    if len(users) == limit:
        nav.append(InlineKeyboardButton(f"Page {page+1} >", callback_data=f"ADMIN_USERS:{page+1}"))

    markup = InlineKeyboardMarkup([nav]) if nav else None
    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=markup
    )


@admin_only
async def admin_users_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[1])
    limit = 10
    offset = (page - 1) * limit

    users = admin_get_all_users(limit=limit, offset=offset)
    if not users:
        await query.edit_message_text("[Empty] No more users.")
        return

    lines = [f"[Users] *All Users* (page {page})\n"]
    for u in users:
        emoji = STATUS_EMOJI.get(u.get("status", "active"), "[?]")
        last  = _time_ago(u.get("last_active", ""))
        lines.append(
            f"{emoji} `{u['telegram_id']}`\n"
            f"   [Repo] {u.get('default_repo','-')} \u2022 {u.get('branch','-')}\n"
            f"   [Time] {last}"
        )

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(f"< Page {page-1}", callback_data=f"ADMIN_USERS:{page-1}"))
    if len(users) == limit:
        nav.append(InlineKeyboardButton(f"Page {page+1} >", callback_data=f"ADMIN_USERS:{page+1}"))

    markup = InlineKeyboardMarkup([nav]) if nav else None
    await query.edit_message_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=markup
    )


# --- /admin_user <telegram_id> -------------------------------------------------------------------------

@admin_only
async def admin_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: `/admin_user <telegram_id>`", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = context.args[0].strip()
    user = admin_get_user_detail(target_id)
    if not user:
        await update.message.reply_text(f"[X] No user found with ID `{target_id}`", parse_mode=ParseMode.MARKDOWN)
        return

    emoji   = STATUS_EMOJI.get(user.get("status", "active"), "[?]")
    last    = _time_ago(user.get("last_active", ""))
    created = _time_ago(user.get("created_at", ""))

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("[Banned] Ban",   callback_data=f"ADMIN_BAN:{target_id}"),
            InlineKeyboardButton("[OK] Unban", callback_data=f"ADMIN_UNBAN:{target_id}"),
        ]
    ])

    await update.message.reply_text(
        f"[User] *User Detail*\n\n"
        f"Telegram ID: `{target_id}`\n"
        f"Status: {emoji} `{user.get('status','-')}`\n"
        f"Repo: `{user.get('default_repo','-')}` \u2022 `{user.get('branch','-')}`\n"
        f"Last active: `{last}`\n"
        f"Joined: `{created}`\n"
        f"Ping count: `{user.get('ping_count', 0)}`\n\n"
        f"[Files] Staged (pending): `{user['staged_count']}`\n"
        f"[Logs] Total commits: `{user['commits_count']}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


# --- /admin_ban & /admin_unban -------------------------------------------------------------------------

@admin_only
async def admin_ban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: `/admin_ban <telegram_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    target_id = context.args[0].strip()
    ok = admin_set_user_status(target_id, "banned")
    if ok:
        await channel_logger.log_user_banned(str(update.effective_user.id), target_id, "banned")
        await update.message.reply_text(f"[Banned] User `{target_id}` has been *banned*.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("[X] Failed to ban user.")


@admin_only
async def admin_unban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: `/admin_unban <telegram_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    target_id = context.args[0].strip()
    ok = admin_set_user_status(target_id, "active")
    if ok:
        await channel_logger.log_user_banned(str(update.effective_user.id), target_id, "unbanned")
        await update.message.reply_text(f"[OK] User `{target_id}` has been *unbanned*.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("[X] Failed to unban user.")


async def admin_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not is_admin(str(query.from_user.id)):
        await query.answer("[X] Unauthorized.", show_alert=True)
        return
    await query.answer()
    target_id = query.data.split(":")[1]
    ok = admin_set_user_status(target_id, "banned")
    if ok:
        await channel_logger.log_user_banned(str(query.from_user.id), target_id, "banned")
    status_text = f"[Banned] Banned `{target_id}`" if ok else "[X] Ban failed"
    await query.edit_message_text(status_text, parse_mode=ParseMode.MARKDOWN)


async def admin_unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not is_admin(str(query.from_user.id)):
        await query.answer("[X] Unauthorized.", show_alert=True)
        return
    await query.answer()
    target_id = query.data.split(":")[1]
    ok = admin_set_user_status(target_id, "active")
    if ok:
        await channel_logger.log_user_banned(str(query.from_user.id), target_id, "unbanned")
    status_text = f"[OK] Unbanned `{target_id}`" if ok else "[X] Unban failed"
    await query.edit_message_text(status_text, parse_mode=ParseMode.MARKDOWN)


# --- /admin_activity ----------------------------------------------------------------------------------------

@admin_only
async def admin_activity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the most recent commits across ALL users."""
    commits = admin_get_recent_activity(limit=10)
    if not commits:
        await update.message.reply_text("[Empty] No commits yet.")
        return

    lines = ["[Time] *Recent Activity (All Users)*\n"]
    for c in commits:
        short_sha = c["commit_sha"][:7]
        time_str  = _time_ago(c.get("committed_at", ""))
        lines.append(
            f"`{short_sha}` - {time_str}\n"
            f"   [User] `{c['telegram_id']}`\n"
            f"   \U0001f4ac {c['message']}\n"
            f"   [Repo] {c.get('repo','-')}"
        )

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.MARKDOWN
    )


# --- /admin_broadcast ---------------------------------------------------------------------------------------

ADMIN_BROADCAST_WAITING = 99

@admin_only
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    active_ids = admin_get_all_active_telegram_ids()
    await update.message.reply_text(
        f"[Broadcast] *Broadcast to {len(active_ids)} active users*\n\n"
        f"Type your message below. It will be sent to all active users.\n"
        f"Send /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data["broadcast_count"] = len(active_ids)
    return ADMIN_BROADCAST_WAITING


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_text = update.message.text.strip()
    active_ids = admin_get_all_active_telegram_ids()

    sent = 0
    failed = 0
    for tid in active_ids:
        try:
            await context.bot.send_message(
                chat_id=int(tid),
                text=f"[Broadcast] *Message from GitPhone Team*\n\n{message_text}",
                parse_mode=ParseMode.MARKDOWN
            )
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"[OK] Broadcast complete!\n\n"
        f"Sent:   `{sent}`\n"
        f"Failed: `{failed}`",
        parse_mode=ParseMode.MARKDOWN
    )
    # Log broadcast to channel
    await channel_logger.log_broadcast(
        admin_id=str(update.effective_user.id),
        sent=sent,
        failed=failed,
        preview=message_text,
    )
    return ConversationHandler.END


# --- /admin_ping ----------------------------------------------------------------------------------------------

@admin_only
async def admin_ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import time
    start = time.time()
    # Quick DB ping
    try:
        get_client().table("users").select("id").limit(1).execute()
        db_ok = True
    except Exception:
        db_ok = False
    elapsed = int((time.time() - start) * 1000)

    await update.message.reply_text(
        f"[Ping] *Admin Ping*\n\n"
        f"Bot: [OK] Online\n"
        f"DB:  {'[OK] OK' if db_ok else '[X] DOWN'}\n"
        f"Latency: `{elapsed}ms`",
        parse_mode=ParseMode.MARKDOWN
    )


# --- /admin_help ----------------------------------------------------------------------------------------------

@admin_only
async def admin_help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "[Admin] *Admin Commands*\n\n"
        "/admin\\_stats       - Global platform stats\n"
        "/admin\\_users       - List all users (paginated)\n"
        "/admin\\_user \\<id\\>  - Inspect a specific user\n"
        "/admin\\_ban \\<id\\>   - Ban a user\n"
        "/admin\\_unban \\<id\\> - Unban a user\n"
        "/admin\\_activity    - Recent commits across all users\n"
        "/admin\\_broadcast   - Send message to all active users\n"
        "/admin\\_ping        - Backend + DB health check\n"
        "/admin\\_help        - This message\n\n"
        f"[Key] Your admin ID: `{update.effective_user.id}`",
        parse_mode=ParseMode.MARKDOWN
    )


# --- Register all admin handlers ----------------------------------------------------------------------

def register_admin_handlers(telegram_app) -> None:
    """Call this from main.py to wire up all admin handlers."""
    from telegram.ext import CallbackQueryHandler

    telegram_app.add_handler(CommandHandler("admin_stats",     admin_stats_handler))
    telegram_app.add_handler(CommandHandler("admin_users",     admin_users_handler))
    telegram_app.add_handler(CommandHandler("admin_user",      admin_user_handler))
    telegram_app.add_handler(CommandHandler("admin_ban",       admin_ban_handler))
    telegram_app.add_handler(CommandHandler("admin_unban",     admin_unban_handler))
    telegram_app.add_handler(CommandHandler("admin_activity",  admin_activity_handler))
    telegram_app.add_handler(CommandHandler("admin_ping",      admin_ping_handler))
    telegram_app.add_handler(CommandHandler("admin_help",      admin_help_handler))

    # Broadcast conversation
    telegram_app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("admin_broadcast", admin_broadcast_start)],
        states={
            ADMIN_BROADCAST_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)
            ]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    ))

    # Inline button callbacks
    telegram_app.add_handler(CallbackQueryHandler(admin_users_page_callback, pattern=r"^ADMIN_USERS:\d+$"))
    telegram_app.add_handler(CallbackQueryHandler(admin_ban_callback,        pattern=r"^ADMIN_BAN:"))
    telegram_app.add_handler(CallbackQueryHandler(admin_unban_callback,      pattern=r"^ADMIN_UNBAN:"))
