"""Telegram entrypoint for the 1-3-7-21 spaced-repetition bot."""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from datetime import date, datetime
from datetime import time as datetime_time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Message, Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import agent
import database
from scheduler import format_daily_digest, send_daily_reminders
from transcriber import transcribe_audio_file

# Load .env before the bot reads any configuration. override=True makes this
# project's .env authoritative even if an old TELEGRAM_BOT_TOKEN is still set
# in the Windows user environment.
load_dotenv(
    dotenv_path=Path(__file__).resolve().with_name(".env"),
    override=True,
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000

WELCOME_TEXT = """👋 Welcome to ReviseBot!

I help you remember what you study using the 1, 3, 7 and 21-day spaced repetition method:
• Day 1: revise tomorrow while the memory is still fresh.
• Day 3 and Day 7: strengthen the memory before it fades.
• Day 21: lock it into long-term memory.

Just send me a voice note or a text message whenever you finish studying a topic. I will suggest a short title, ask you to confirm it, and schedule all four revisions.

Commands:
/today - see what is due today
/schedule - view every topic and its revision dates
/seed_demo - load 3 demo topics for testing
/test_morning - preview today's 9:00 AM digest instantly

What did you study today?"""


def _today_str() -> str:
    tz = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))
    return datetime.now(tz).date().isoformat()


def _pretty_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {parsed.strftime('%b %Y')}"


def _chunks(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long reply on a line/word boundary for Telegram's size limit."""
    remaining = text.strip()
    chunks: list[str] = []

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit

        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].lstrip("\n ")

    return chunks or [""]


async def _reply(message: Message, text: str) -> None:
    # Replies are sent without a parse mode so malformed Markdown can never
    # break delivery. Remove emphasis markers instead of showing them raw.
    plain_text = text.replace("**", "")
    for chunk in _chunks(plain_text):
        await message.reply_text(chunk)


def _is_llm_auth_error(exc: Exception) -> bool:
    """Recognise provider 401s without tying handlers to one SDK class."""
    return (
        getattr(exc, "status_code", None) == 401
        or type(exc).__name__ == "AuthenticationError"
    )


async def _reply_llm_auth_error(message: Message, was_voice: bool) -> None:
    lead = (
        "Your voice note was transcribed locally, but the LLM API key was "
        "rejected (401)."
        if was_voice
        else "The LLM API key was rejected (401)."
    )
    await message.reply_text(
        f"{lead}\n\n"
        "Update LLM_API_KEY in .env with a valid key for your configured "
        "provider, then restart the bot. Speech-to-text is already working."
    )


async def _typing(update: Update) -> None:
    chat = update.effective_chat
    if chat is not None:
        await chat.send_action(ChatAction.TYPING)


async def start_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_message is not None:
        await _reply(update.effective_message, WELCOME_TEXT)


async def today_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    today = _today_str()
    revisions = database.get_revisions_for_date(chat.id, today)

    if not revisions:
        await _reply(
            message,
            f"Nothing is scheduled for revision today ({_pretty_date(today)}).\n\n"
            "Send me a voice note or message when you finish studying "
            "something, and I will start its 1-3-7-21 cycle.",
        )
        return

    lines = [
        f"📚 Today's revisions ({_pretty_date(today)}):",
        "",
    ]
    for revision in revisions:
        lines.append(
            f"• {revision['title']} "
            f"(Day {revision['interval_day']} Revision)"
        )
    lines.extend(
        ["", "Reply if you want to revisit any of these topics."]
    )
    await _reply(message, "\n".join(lines))


async def schedule_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    topics = database.get_all_topics_with_schedule(chat.id)
    if not topics:
        await _reply(
            message,
            "You have no saved topics yet.\n\n"
            "Send me a voice note or message about what you studied, and I "
            "will set up its 1, 3, 7 and 21-day revisions.",
        )
        return

    lines = ["🗓 Your topics and revision cycle:", ""]
    for index, topic in enumerate(topics, start=1):
        lines.append(f"{index}. {topic['title']}")
        lines.append(f"   Studied: {_pretty_date(topic['studied_date'])}")
        for revision in topic["schedule"]:
            lines.append(
                f"   Day {revision['interval_day']}: "
                f"{_pretty_date(revision['scheduled_date'])}"
            )
        lines.append("")

    await _reply(message, "\n".join(lines).strip())


async def seed_demo_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    created = database.seed_demo_data(chat.id, _today_str())
    await _reply(
        message,
        f"✅ Loaded {len(created)} demo topics. Their Day 1, Day 3 and Day 7 "
        "revisions are all due today.\n\n"
        "Run /test_morning to preview the exact 9:00 AM digest right now.",
    )


async def test_morning_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    today = _today_str()
    revisions = database.get_revisions_for_date(chat.id, today)
    if not revisions:
        await _reply(
            message,
            "There are no revisions due today, so the digest would be empty.\n\n"
            "Use /seed_demo to load sample topics, then run /test_morning again.",
        )
        return

    await _reply(message, format_daily_digest(today, revisions))


async def voice_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None or message.voice is None:
        return

    temp_path: str | None = None
    try:
        await _typing(update)
        voice_file = await context.bot.get_file(message.voice.file_id)

        # NamedTemporaryFile is closed before Telegram writes to it, which is
        # required on Windows.
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
            temp_path = temp_file.name

        await voice_file.download_to_drive(custom_path=temp_path)
        await _typing(update)

        try:
            transcript = (await transcribe_audio_file(temp_path)).strip()
        except Exception:
            logger.exception("Local transcription failed for chat %s", chat.id)
            with contextlib.suppress(TelegramError):
                await message.reply_text(
                    "I downloaded your voice note, but local Whisper could not "
                    "transcribe it. Check LOCAL_WHISPER_MODEL in .env and the "
                    "bot logs, then try again."
                )
            return

        if not transcript:
            await _reply(
                message,
                "I could not make out any speech in that voice note. Could you "
                "try again a little closer to the microphone?",
            )
            return

        await _typing(update)
        try:
            reply = await agent.process_user_message(
                chat.id, transcript, is_voice=True
            )
        except Exception as exc:
            logger.exception("LLM processing failed for chat %s", chat.id)
            with contextlib.suppress(TelegramError):
                if _is_llm_auth_error(exc):
                    await _reply_llm_auth_error(message, was_voice=True)
                else:
                    await message.reply_text(
                        "Your voice note was transcribed, but the LLM could not "
                        "produce a reply. Check the bot logs and try again."
                    )
            return

        await _reply(message, reply)

    except Exception:
        logger.exception("Failed to download voice note for chat %s", chat.id)
        with contextlib.suppress(TelegramError):
            await message.reply_text(
                "Sorry, I could not download that voice note. Please try again."
            )
    finally:
        if temp_path:
            with contextlib.suppress(OSError):
                Path(temp_path).unlink()


async def text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None or not (message.text or "").strip():
        return

    try:
        await _typing(update)
        reply = await agent.process_user_message(
            chat.id, message.text.strip(), is_voice=False
        )
        await _reply(message, reply)
    except Exception as exc:
        logger.exception("Failed to process text message for chat %s", chat.id)
        with contextlib.suppress(TelegramError):
            if _is_llm_auth_error(exc):
                await _reply_llm_auth_error(message, was_voice=False)
            else:
                await message.reply_text(
                    "Sorry, I hit a snag while thinking about that. Please "
                    "check the bot logs and try again."
                )


async def error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.error("Unhandled Telegram update error", exc_info=context.error)


def _reminder_time() -> datetime_time:
    tz_name = os.getenv("TIMEZONE", "Asia/Kolkata")
    try:
        tz = ZoneInfo(tz_name)
    except Exception as exc:
        raise RuntimeError(f"Invalid TIMEZONE '{tz_name}': {exc}") from exc

    try:
        hour = int(os.getenv("REMINDER_HOUR", "9"))
        minute = int(os.getenv("REMINDER_MINUTE", "0"))
    except ValueError as exc:
        raise RuntimeError(
            "REMINDER_HOUR and REMINDER_MINUTE must be whole numbers."
        ) from exc

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise RuntimeError(
            "REMINDER_HOUR must be 0-23 and REMINDER_MINUTE must be 0-59."
        )

    return datetime_time(hour=hour, minute=minute, tzinfo=tz)


async def post_init(application: Application) -> None:
    """Log which bot actually connected, making token mix-ups obvious."""
    me = await application.bot.get_me()
    logger.info(
        "Connected to Telegram as @%s (bot id %s).",
        me.username,
        me.id,
    )
    logger.info(
        "LLM model: %s at %s",
        os.getenv("LLM_MODEL", agent.LLM_MODEL),
        os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
    )
    stt_mode = os.getenv("STT_MODE", "local").strip().lower()
    if stt_mode == "local":
        logger.info(
            "STT: local faster-whisper model=%s local_files_only=%s",
            os.getenv("LOCAL_WHISPER_MODEL", "base"),
            os.getenv("LOCAL_WHISPER_LOCAL_FILES_ONLY", "false"),
        )
    else:
        logger.info("STT: API mode model=%s", os.getenv("STT_MODEL", "whisper-1"))


def build_application() -> Application:
    """Create the bot application and register every handler and job."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token.startswith("your_"):
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and add "
            "the token from @BotFather."
        )

    logger.info("Starting Telegram bot id %s from .env.", token.split(":", 1)[0])
    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("seed_demo", seed_demo_command))
    application.add_handler(CommandHandler("test_morning", test_morning_command))
    application.add_handler(MessageHandler(filters.VOICE, voice_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
    )
    application.add_error_handler(error_handler)

    job_queue = application.job_queue
    if job_queue is None:
        raise RuntimeError(
            "JobQueue is unavailable. Install the project with "
            "`pip install -r requirements.txt` (it includes the job-queue extra)."
        )

    reminder_time = _reminder_time()
    job_queue.run_daily(
        send_daily_reminders,
        time=reminder_time,
        name="daily_revision_digest",
    )
    logger.info(
        "Daily digest scheduled for %02d:%02d (%s).",
        reminder_time.hour,
        reminder_time.minute,
        reminder_time.tzinfo,
    )

    return application


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    database.init_db()

    try:
        application = build_application()
    except RuntimeError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    logger.info("ReviseBot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
