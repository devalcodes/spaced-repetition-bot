"""Daily revision digest and its scheduled Telegram job."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from telegram.error import TelegramError
from telegram.ext import ContextTypes

import database

logger = logging.getLogger(__name__)


def _timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))


def _display_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {parsed.strftime('%b %Y')}"


def format_daily_digest(target_date_str: str, revisions: list[dict[str, Any]]) -> str:
    """Format one clean morning message for every revision due on a date."""
    display_date = _display_date(target_date_str)

    if not revisions:
        return (
            f"☀️ Good morning! Nothing is scheduled for revision today "
            f"({display_date}).\n\n"
            "Reply anytime if you want to log what you study today!"
        )

    lines = [
        (
            f"☀️ Good morning! Here is your revision lineup for today "
            f"({display_date}):"
        ),
        "",
    ]
    for revision in revisions:
        lines.append(
            f"• {revision['title']} "
            f"(Day {revision['interval_day']} Revision)"
        )

    lines.extend(
        [
            "",
            (
                "Reply anytime if you have doubts on these topics or want to "
                "log what you study today!"
            ),
        ]
    )
    return "\n".join(lines)


async def send_daily_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the consolidated 9:00 AM digest to every chat with due revisions."""
    today_str = datetime.now(_timezone()).date().isoformat()
    chat_ids = database.get_all_active_chats_with_revisions_today(today_str)

    if not chat_ids:
        logger.info("No revisions scheduled for %s; no digests sent.", today_str)
        return

    for chat_id in chat_ids:
        revisions = database.get_revisions_for_date(chat_id, today_str)
        if not revisions:
            continue
        message = format_daily_digest(today_str, revisions)
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
        except TelegramError as exc:
            logger.warning("Could not send digest to chat %s: %s", chat_id, exc)
        except Exception:
            logger.exception("Unexpected error sending digest to chat %s", chat_id)
        else:
            logger.info(
                "Sent digest for %s to chat %s (%d revisions).",
                today_str,
                chat_id,
                len(revisions),
            )
