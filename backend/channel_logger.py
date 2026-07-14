"""
channel_logger.py - Sends structured log messages to a private Telegram channel.

HOW TO SET UP:
  1. Create a private Telegram channel
  2. Add your bot as an Administrator (with "Post Messages" permission)
  3. Get the channel ID (forward any message to @userinfobot or use @getidsbot)
     Channel IDs look like: -1001234567890
  4. Set LOG_CHANNEL_ID env var to that value

EVENTS LOGGED:
  - \U0001f195 New user registered
  - [OK] Commit successful
  - \U0001f504 Force commit
  - [Warning]  Conflict detected
  - [X] Commit failed
  - [Files] File staged (sync)
  - [Banned] User banned / unbanned
  - [Broadcast] Broadcast sent
  - [Error] Backend errors
"""

import os
import traceback
from datetime import datetime, timezone

# Global bot reference - set during startup in main.py
_bot = None


def init_logger(bot) -> None:
    """Call once from main.py with the telegram Bot instance."""
    global _bot
    _bot = bot


def _get_channel_id() -> str | None:
    return os.environ.get("LOG_CHANNEL_ID", "").strip() or None


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


async def _send(text: str) -> None:
    """Fire-and-forget send to log channel. Never raises."""
    channel_id = _get_channel_id()
    if not channel_id or not _bot:
        return
    try:
        await _bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="Markdown",
            disable_notification=True,   # silent - no phone buzz for each log
        )
    except Exception as e:
        # Log to console but never crash the main flow
        print(f"[channel_logger] Failed to send log: {e}")


# --- Event Loggers -------------------------------------------------------------------------------------------

async def log_new_user(telegram_id: str, repo: str, branch: str) -> None:
    await _send(
        f"\U0001f195 *New User Registered*\n"
        f"[User] `{telegram_id}`\n"
        f"[Repo] `{repo}` \u2022 `{branch}`\n"
        f"[Time] {_now_utc()}"
    )


async def log_commit(
    telegram_id: str,
    repo: str,
    branch: str,
    commit_sha: str,
    message: str,
    files: list[str],
    was_forced: bool = False,
) -> None:
    icon = "\U0001f504" if was_forced else "[OK]"
    label = "Force Commit" if was_forced else "Commit"
    short_sha = commit_sha[:7] if commit_sha else "unknown"
    files_str = "\n".join(f"  \u2022 `{f}`" for f in files) or "  -"
    await _send(
        f"{icon} *{label} Successful*\n"
        f"[User] `{telegram_id}`\n"
        f"[Repo] `{repo}` \u2022 `{branch}`\n"
        f"[Link] `{short_sha}`\n"
        f"\U0001f4ac {message}\n"
        f"[Files] Files:\n{files_str}\n"
        f"[Time] {_now_utc()}"
    )


async def log_commit_failed(
    telegram_id: str,
    repo: str,
    error: str,
) -> None:
    await _send(
        f"[X] *Commit Failed*\n"
        f"[User] `{telegram_id}`\n"
        f"[Repo] `{repo}`\n"
        f"[Warning] `{error}`\n"
        f"[Time] {_now_utc()}"
    )


async def log_conflict(
    telegram_id: str,
    repo: str,
    conflict_files: list[str],
) -> None:
    files_str = "\n".join(f"  \u2022 `{f}`" for f in conflict_files) or "  -"
    await _send(
        f"[Warning] *Conflict Detected*\n"
        f"[User] `{telegram_id}`\n"
        f"[Repo] `{repo}`\n"
        f"\U0001f500 Conflicting files:\n{files_str}\n"
        f"[Time] {_now_utc()}"
    )


async def log_file_staged(
    telegram_id: str,
    filepath: str,
    repo: str,
    file_size: int,
    is_binary: bool,
) -> None:
    size_kb = round(file_size / 1024, 1)
    binary_tag = " _(binary)_" if is_binary else ""
    await _send(
        f"[Files] *File Staged*\n"
        f"[User] `{telegram_id}`\n"
        f"[Repo] `{repo}`\n"
        f"\U0001f4c4 `{filepath}`{binary_tag} - `{size_kb}KB`\n"
        f"[Time] {_now_utc()}"
    )


async def log_user_banned(
    admin_id: str,
    target_id: str,
    action: str,          # "banned" or "unbanned"
) -> None:
    icon = "[Banned]" if action == "banned" else "[OK]"
    await _send(
        f"{icon} *User {action.title()}*\n"
        f"[Key] Admin: `{admin_id}`\n"
        f"[User] Target: `{target_id}`\n"
        f"[Time] {_now_utc()}"
    )


async def log_broadcast(
    admin_id: str,
    sent: int,
    failed: int,
    preview: str,
) -> None:
    preview_truncated = (preview[:80] + "\u2026") if len(preview) > 80 else preview
    await _send(
        f"[Broadcast] *Broadcast Sent*\n"
        f"[Key] Admin: `{admin_id}`\n"
        f"[OK] Sent: `{sent}` | [X] Failed: `{failed}`\n"
        f"\U0001f4ac _{preview_truncated}_\n"
        f"[Time] {_now_utc()}"
    )


async def log_error(
    context: str,
    error: Exception,
    telegram_id: str | None = None,
) -> None:
    tb = traceback.format_exc()
    tb_short = tb[-500:] if len(tb) > 500 else tb  # last 500 chars
    user_line = f"[User] `{telegram_id}`\n" if telegram_id else ""
    await _send(
        f"[Error] *Backend Error*\n"
        f"{user_line}"
        f"\U0001f4cd `{context}`\n"
        f"[Warning] `{type(error).__name__}: {str(error)[:100]}`\n"
        f"```\n{tb_short}\n```\n"
        f"[Time] {_now_utc()}"
    )


async def log_startup(webhook_url: str) -> None:
    await _send(
        f"\U0001f680 *GitPhone Backend Started*\n"
        f"[Link] Webhook: `{webhook_url}/webhook`\n"
        f"[Time] {_now_utc()}"
    )


async def log_shutdown() -> None:
    await _send(
        f"\U0001f6d1 *GitPhone Backend Shutting Down*\n"
        f"[Time] {_now_utc()}"
    )
