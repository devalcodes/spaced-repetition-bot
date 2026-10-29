"""SQLite persistence layer for the 1-3-7-21 spaced-repetition bot.

All functions are intentionally synchronous.  The Telegram handlers call them
from the event loop only for very short operations; the expensive work in this
project (LLM calls and speech-to-text) is asynchronous.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INTERVALS = [1, 3, 7, 21]
DB_PATH = Path(__file__).resolve().parent / "study_memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id       INTEGER NOT NULL,
    title         TEXT NOT NULL,
    voice_summary TEXT,
    studied_date  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revisions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id       INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    chat_id        INTEGER NOT NULL,
    interval_day   INTEGER NOT NULL,
    scheduled_date TEXT NOT NULL,
    notified       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pending_drafts (
    chat_id        INTEGER PRIMARY KEY,
    proposed_title TEXT NOT NULL,
    voice_summary  TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now_iso() -> str:
    """Return an ISO-8601 UTC timestamp suitable for audit columns."""
    return datetime.now(timezone.utc).isoformat(  # noqa: UP017 - Python 3.10
        timespec="seconds"
    )


def _parse_iso_date(value: str, field_name: str = "date") -> date:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a YYYY-MM-DD string.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid YYYY-MM-DD date.") from exc
    # date.fromisoformat also accepts some compact forms on newer Pythons.
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must use the YYYY-MM-DD format.")
    return parsed


def _title(value: str, field_name: str = "title") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} cannot be empty.")
    return value.strip()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open a short-lived connection with foreign keys enforced."""
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create every table used by the bot if it does not already exist."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def set_pending_draft(
    chat_id: int, proposed_title: str, voice_summary: str
) -> dict[str, Any]:
    """Stage a topic until the user confirms or corrects its title."""
    title = _title(proposed_title, "proposed_title")
    summary = (voice_summary or "").strip()
    if not summary:
        raise ValueError("voice_summary cannot be empty.")
    updated_at = _now_iso()

    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pending_drafts
                (chat_id, proposed_title, voice_summary, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, title, summary, updated_at),
        )

    return {
        "chat_id": chat_id,
        "proposed_title": title,
        "voice_summary": summary,
        "updated_at": updated_at,
    }


def get_pending_draft(chat_id: int) -> dict[str, str] | None:
    """Return the current pending draft for a chat, if one exists."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT proposed_title, voice_summary
            FROM pending_drafts
            WHERE chat_id = ?
            """,
            (chat_id,),
        ).fetchone()

    if row is None:
        return None
    return {
        "proposed_title": row["proposed_title"],
        "voice_summary": row["voice_summary"],
    }


def clear_pending_draft(chat_id: int) -> None:
    """Delete any staged draft for a chat."""
    with _connect() as conn:
        conn.execute("DELETE FROM pending_drafts WHERE chat_id = ?", (chat_id,))


def _insert_topic_with_schedule(
    conn: sqlite3.Connection,
    chat_id: int,
    title: str,
    studied_date: str,
    voice_summary: str,
) -> dict[str, Any]:
    """Insert one topic and its four revisions inside the caller's transaction."""
    created_at = _now_iso()
    cursor = conn.execute(
        """
        INSERT INTO topics
            (chat_id, title, voice_summary, studied_date, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (chat_id, title, voice_summary, studied_date, created_at),
    )
    topic_id = int(cursor.lastrowid)
    studied = _parse_iso_date(studied_date, "studied_date")
    schedule: list[dict[str, Any]] = []

    for interval_day in INTERVALS:
        scheduled_date = (studied + timedelta(days=interval_day)).isoformat()
        conn.execute(
            """
            INSERT INTO revisions
                (topic_id, chat_id, interval_day, scheduled_date, notified)
            VALUES (?, ?, ?, ?, 0)
            """,
            (topic_id, chat_id, interval_day, scheduled_date),
        )
        schedule.append(
            {"interval_day": interval_day, "scheduled_date": scheduled_date}
        )

    return {
        "topic_id": topic_id,
        "title": title,
        "studied_date": studied_date,
        "schedule": schedule,
    }


def confirm_and_schedule_topic(
    chat_id: int,
    final_title: str,
    studied_date_str: str,
    voice_summary: str = "",
) -> dict[str, Any]:
    """Save a confirmed topic atomically with its 1, 3, 7 and 21-day revisions."""
    title = _title(final_title, "final_title")
    _parse_iso_date(studied_date_str, "studied_date")
    summary = (voice_summary or "").strip()

    with _connect() as conn:
        if not summary:
            draft_row = conn.execute(
                """
                SELECT voice_summary
                FROM pending_drafts
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            if draft_row is not None:
                summary = draft_row["voice_summary"]

        result = _insert_topic_with_schedule(
            conn, chat_id, title, studied_date_str, summary
        )
        conn.execute("DELETE FROM pending_drafts WHERE chat_id = ?", (chat_id,))

    return result


def get_revisions_for_date(chat_id: int, target_date_str: str) -> list[dict[str, Any]]:
    """Return every revision due for a chat on a specific calendar date."""
    _parse_iso_date(target_date_str, "target_date")
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                r.id            AS revision_id,
                r.topic_id      AS topic_id,
                t.title         AS title,
                t.voice_summary AS voice_summary,
                t.studied_date  AS studied_date,
                r.interval_day  AS interval_day,
                r.scheduled_date AS scheduled_date
            FROM revisions AS r
            JOIN topics AS t ON t.id = r.topic_id
            WHERE r.chat_id = ? AND r.scheduled_date = ?
            ORDER BY r.interval_day ASC, r.id ASC
            """,
            (chat_id, target_date_str),
        ).fetchall()

    return [
        {
            "revision_id": row["revision_id"],
            "topic_id": row["topic_id"],
            "title": row["title"],
            "voice_summary": row["voice_summary"] or "",
            "studied_date": row["studied_date"],
            "interval_day": row["interval_day"],
            "scheduled_date": row["scheduled_date"],
        }
        for row in rows
    ]


def get_all_active_chats_with_revisions_today(target_date_str: str) -> list[int]:
    """Return distinct chat IDs that have at least one revision on a date."""
    _parse_iso_date(target_date_str, "target_date")
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT chat_id
            FROM revisions
            WHERE scheduled_date = ?
            ORDER BY chat_id ASC
            """,
            (target_date_str,),
        ).fetchall()
    return [int(row["chat_id"]) for row in rows]


def get_all_topics_with_schedule(chat_id: int) -> list[dict[str, Any]]:
    """Return all studied topics, notes and their four revision dates."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                t.id             AS topic_id,
                t.title          AS title,
                t.voice_summary  AS voice_summary,
                t.studied_date   AS studied_date,
                r.id             AS revision_id,
                r.interval_day   AS interval_day,
                r.scheduled_date AS scheduled_date,
                r.notified       AS notified
            FROM topics AS t
            LEFT JOIN revisions AS r ON r.topic_id = t.id
            WHERE t.chat_id = ?
            ORDER BY t.studied_date DESC, t.id DESC, r.interval_day ASC
            """,
            (chat_id,),
        ).fetchall()

    topics: list[dict[str, Any]] = []
    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        topic_id = int(row["topic_id"])
        topic = by_id.get(topic_id)
        if topic is None:
            topic = {
                "topic_id": topic_id,
                "title": row["title"],
                "voice_summary": row["voice_summary"] or "",
                "studied_date": row["studied_date"],
                "schedule": [],
            }
            by_id[topic_id] = topic
            topics.append(topic)

        if row["revision_id"] is not None:
            topic["schedule"].append(
                {
                    "revision_id": row["revision_id"],
                    "interval_day": row["interval_day"],
                    "scheduled_date": row["scheduled_date"],
                    "notified": bool(row["notified"]),
                }
            )

    return topics


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def delete_or_rename_topic(
    chat_id: int,
    current_title_query: str,
    action: str,
    new_title: str = "",
) -> dict[str, Any]:
    """Find the closest matching saved topic and delete or rename it."""
    query = (current_title_query or "").strip()
    normalized_action = (action or "").strip().lower()
    if normalized_action not in {"delete", "rename"}:
        raise ValueError('action must be either "delete" or "rename".')
    if not query:
        return {
            "status": "not_found",
            "message": "No topic was specified.",
            "query": current_title_query,
        }

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, title
            FROM topics
            WHERE chat_id = ? AND title LIKE ? ESCAPE '\\'
            ORDER BY studied_date DESC, id DESC
            LIMIT 1
            """,
            (chat_id, f"%{_escape_like(query)}%"),
        ).fetchone()

        if row is None:
            return {
                "status": "not_found",
                "message": f'No saved topic matched "{query}".',
                "query": query,
            }

        topic_id = int(row["id"])
        old_title = row["title"]

        if normalized_action == "delete":
            # Explicit deletion makes the operation safe even if an older
            # SQLite build has foreign-key enforcement disabled.
            conn.execute("DELETE FROM revisions WHERE topic_id = ?", (topic_id,))
            conn.execute(
                "DELETE FROM topics WHERE id = ? AND chat_id = ?",
                (topic_id, chat_id),
            )
            return {
                "status": "deleted",
                "topic_id": topic_id,
                "title": old_title,
                "message": f'Deleted "{old_title}" and its revision schedule.',
            }

        final_title = _title(new_title, "new_title")
        conn.execute(
            "UPDATE topics SET title = ? WHERE id = ? AND chat_id = ?",
            (final_title, topic_id, chat_id),
        )
        return {
            "status": "renamed",
            "topic_id": topic_id,
            "old_title": old_title,
            "title": final_title,
            "message": f'Renamed "{old_title}" to "{final_title}".',
        }


def add_chat_message(chat_id: int, role: str, content: str) -> None:
    """Save a chat turn and retain only the latest 12 turns for that chat."""
    normalized_role = (role or "").strip().lower()
    if normalized_role not in {"user", "assistant"}:
        raise ValueError('role must be either "user" or "assistant".')
    if content is None:
        raise ValueError("content cannot be None.")

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (chat_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, normalized_role, str(content), _now_iso()),
        )
        conn.execute(
            """
            DELETE FROM chat_messages
            WHERE chat_id = ?
              AND id NOT IN (
                  SELECT id
                  FROM chat_messages
                  WHERE chat_id = ?
                  ORDER BY id DESC
                  LIMIT 12
              )
            """,
            (chat_id, chat_id),
        )


def get_recent_chat_messages(chat_id: int, limit: int = 10) -> list[dict[str, str]]:
    """Return the latest messages for a chat in chronological order."""
    if limit <= 0:
        return []

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM (
                SELECT id, role, content
                FROM chat_messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (chat_id, limit),
        ).fetchall()

    return [{"role": row["role"], "content": row["content"]} for row in rows]


def seed_demo_data(chat_id: int, today_date_str: str) -> list[dict[str, Any]]:
    """Replace a chat's data with three topics due for revision today.

    The three topics were "studied" one, three and seven days ago so their
    Day 1, Day 3 and Day 7 revisions all fall on ``today_date_str``.
    """
    today = _parse_iso_date(today_date_str, "today_date")
    samples = [
        (
            "Thermodynamics Second Law",
            (
                "Entropy of an isolated system never decreases. Heat flows "
                "spontaneously from hot to cold, and irreversible processes "
                "increase total entropy."
            ),
            1,
        ),
        (
            "Electrochemistry Nernst Equation",
            (
                "The Nernst equation relates cell potential to standard "
                "potential, temperature and reaction quotient. It explains "
                "concentration effects on electrode potential."
            ),
            3,
        ),
        (
            "Organic Haloalkanes",
            (
                "Haloalkanes undergo SN1 and SN2 substitution. SN1 is favoured "
                "by tertiary substrates and polar protic solvents; SN2 by "
                "primary substrates and strong nucleophiles."
            ),
            7,
        ),
    ]

    created: list[dict[str, Any]] = []
    with _connect() as conn:
        conn.execute("DELETE FROM revisions WHERE chat_id = ?", (chat_id,))
        conn.execute("DELETE FROM topics WHERE chat_id = ?", (chat_id,))

        for title, summary, days_ago in samples:
            studied_date = (today - timedelta(days=days_ago)).isoformat()
            result = _insert_topic_with_schedule(
                conn, chat_id, title, studied_date, summary
            )
            result["voice_summary"] = summary
            created.append(result)

    return created
