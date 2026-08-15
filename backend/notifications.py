"""notifications.py - Send GitHub-event notifications to users via the Telegram bot."""

import re

from telegram.constants import ParseMode

_bot = None


def init_notifier(bot) -> None:
    global _bot
    _bot = bot


def _escape_markdown(text: str) -> str:
    """Escape Markdown metacharacters so titles don't break formatting."""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)


async def notify_issue_assigned(telegram_id: str, repo: str, issue_title: str,
                                issue_number: int, issue_url: str) -> bool:
    """DM a user that an issue was assigned to them. Returns True if sent."""
    if not _bot:
        return False
    safe_title = _escape_markdown(issue_title)
    text = (
        f"\U0001F514 *New Issue Assigned*\n\n"
        f"\U0001F4CC *{safe_title}* (#{issue_number})\n"
        f"\U0001F4C1 `{repo}`\n\n"
        f"\U0001F517 [Open on GitHub]({issue_url})"
    )
    try:
        await _bot.send_message(
            chat_id=int(telegram_id),
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return True
    except Exception as e:
        print(f"[notifications] send failed for {telegram_id}: {e}")
        return False
