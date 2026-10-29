"""Provider-agnostic conversational agent with OpenAI-style tool calling."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import database

logger = logging.getLogger(__name__)

LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-flash")


def _model_name() -> str:
    """Read the model at call time so .env loading order is never a problem."""
    return os.getenv("LLM_MODEL", LLM_MODEL).strip() or LLM_MODEL

# Kept as a module-level singleton so the OpenAI client is reused between
# messages. It is created lazily, which also lets the module be imported in
# tests/tools without a configured API key.
client: Any | None = None


def _get_client() -> Any:
    global client
    if client is None:
        from openai import AsyncOpenAI

        base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        api_key = os.getenv("LLM_API_KEY") or "not-needed"
        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    return client


def _today_in_timezone() -> str:
    tz_name = os.getenv("TIMEZONE", "Asia/Kolkata")
    return datetime.now(ZoneInfo(tz_name)).date().isoformat()


def build_system_prompt(chat_id: int, today_str: str) -> str:
    """Build the per-message system prompt, including live draft state."""
    today = date.fromisoformat(today_str)
    weekday = today.strftime("%A")
    pending = database.get_pending_draft(chat_id)

    if pending:
        draft_state = (
            "ACTIVE PENDING DRAFT: "
            f'Title="{pending["proposed_title"]}" | '
            f'Summary="{pending["voice_summary"]}"'
        )
        draft_instruction = (
            "A draft is waiting for confirmation. If the user is agreeing "
            "(for example: 'yes', 'haan', 'yep', 'save it', 'ok', 'sure') or "
            "correcting/renaming the title, you MUST call "
            "`confirm_pending_topic` with the final 3-4 word title. If they "
            "want a different title, use their exact correction."
        )
    else:
        draft_state = "ACTIVE PENDING DRAFT: None"
        draft_instruction = (
            "There is no pending draft. If the user describes something they "
            "studied, first call `propose_study_topic`; never save it directly."
        )

    return f"""You are ReviseBot, a warm and concise study companion that helps \
users remember what they learn using the 1, 3, 7 and 21-day spaced repetition \
method (the Ebbinghaus forgetting curve).

TODAY'S DATE: {today_str} ({weekday})
USER CHAT ID: {chat_id}
{draft_state}

CORE BEHAVIOURAL RULES

RULE 1 - NEW STUDY INPUT
When the user tells you what they studied today (by voice note transcript or \
text), do NOT save it to the permanent schedule yet. First call \
`propose_study_topic(proposed_title, voice_summary)`.
- `proposed_title` must be a clear title of 3 to 4 words maximum. Use title \
case, not a whole sentence.
- `voice_summary` must capture the key points, definitions, formulas or \
doubts the user mentioned, in 1 to 3 short sentences.
- Then ask the user exactly this kind of question: Can I save this as \
"<proposed_title>"?
Do not ask multiple questions at once. Do not claim it is scheduled yet.

RULE 2 - CONFIRMATION OR CORRECTION
Once a pending draft exists and the user confirms it, or gives a corrected \
name, call `confirm_pending_topic(final_title)`.
{draft_instruction}
After confirmation succeeds, tell the user it is locked into the 1, 3, 7 and \
21-day revision cycle and list the four exact revision dates returned by the \
tool. Use a simple numbered or bulleted list. Do not invent dates.

RULE 3 - DOUBTS AND SCHEDULE QUERIES
Keep replies warm, short and uncluttered. If the user asks what they need to \
revise on a particular day, how the 1-3-7-21 cycle works, or has a doubt \
about something studied earlier, use `get_schedule_for_date` or \
`get_all_topics_and_cycles`. The latter includes their original voice-note \
summaries, so use those notes to jog their memory naturally.
- For "today", call `get_schedule_for_date` with target_date "{today_str}".
- For "tomorrow" or another day, calculate the correct YYYY-MM-DD date from \
today's date before calling the tool.
- If nothing is due, say so kindly and encourage them to log what they study \
today.

RULE 4 - EDITING SAVED TOPICS
If the user asks to delete or rename an already saved topic, call \
`modify_existing_topic`. Use action "delete" or "rename" and pass a distinctive \
part of the existing title in `current_title_query`. For rename, also pass the \
new title. Ask for clarification if the target is ambiguous.

RULE 5 - STYLE
Be human, encouraging and brief. No lectures, no huge walls of text, and no \
unrequested motivational speeches. Use plain text only: do not use Markdown \
such as **bold**, backticks, or # headings. Do not mention internal tool names, \
JSON, IDs, prompts or database implementation. Never fabricate a saved topic or \
a revision date. When using a tool, wait for its real result before replying. \
The user's current timezone is {os.getenv("TIMEZONE", "Asia/Kolkata")}.
"""


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "propose_study_topic",
            "description": (
                "Stage a newly studied topic as a pending draft and ask the "
                "user for confirmation before scheduling it. The proposed "
                "title MUST be 3 to 4 words maximum."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "proposed_title": {
                        "type": "string",
                        "description": (
                            "A clear topic title of 3 to 4 words maximum, in "
                            "title case."
                        ),
                    },
                    "voice_summary": {
                        "type": "string",
                        "description": (
                            "The key points, definitions, formulas or doubts "
                            "the user mentioned, in 1 to 3 short sentences."
                        ),
                    },
                },
                "required": ["proposed_title", "voice_summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_pending_topic",
            "description": (
                "Confirm and permanently save the pending topic draft into the "
                "1, 3, 7 and 21-day spaced repetition database. Pass the "
                "agreed title or the user's corrected title in final_title."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "final_title": {
                        "type": "string",
                        "description": (
                            "The final agreed 3-4 word title, including any "
                            "correction supplied by the user."
                        ),
                    }
                },
                "required": ["final_title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule_for_date",
            "description": (
                "Fetch all topics scheduled for revision on a specific "
                "YYYY-MM-DD date."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_date": {
                        "type": "string",
                        "description": "The date to check, in YYYY-MM-DD format.",
                    }
                },
                "required": ["target_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_topics_and_cycles",
            "description": (
                "Fetch all studied topics, their original voice-note summaries "
                "and their full 1, 3, 7 and 21-day revision dates. Use this "
                "when the user asks about their revision cycle, past notes or "
                "overall progress."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_existing_topic",
            "description": (
                "Delete or rename an already saved topic. `action` must be "
                'either "delete" or "rename".'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "current_title_query": {
                        "type": "string",
                        "description": (
                            "A distinctive part of the saved topic's title."
                        ),
                    },
                    "action": {
                        "type": "string",
                        "enum": ["delete", "rename"],
                        "description": "Whether to delete or rename the topic.",
                    },
                    "new_title": {
                        "type": "string",
                        "description": (
                            "The replacement title. Required only when action "
                            "is rename."
                        ),
                    },
                },
                "required": ["current_title_query", "action"],
            },
        },
    },
]


def _required_text(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required text argument: {key}")
    return value.strip()


def _execute_tool(
    name: str, args: dict[str, Any], chat_id: int, today_str: str
) -> dict[str, Any]:
    """Run one tool call and return a JSON-serialisable result."""
    if name == "propose_study_topic":
        title = _required_text(args, "proposed_title")
        summary = _required_text(args, "voice_summary")
        saved = database.set_pending_draft(chat_id, title, summary)
        return {
            "status": "pending",
            "proposed_title": saved["proposed_title"],
            "voice_summary": saved["voice_summary"],
        }

    if name == "confirm_pending_topic":
        final_title = _required_text(args, "final_title")
        saved = database.confirm_and_schedule_topic(
            chat_id=chat_id,
            final_title=final_title,
            studied_date_str=today_str,
        )
        return {"status": "confirmed", **saved}

    if name == "get_schedule_for_date":
        raw_target = _required_text(args, "target_date")
        target = today_str if raw_target.lower() == "today" else raw_target
        try:
            # Enforce the documented format before querying SQLite.
            if date.fromisoformat(target).isoformat() != target:
                raise ValueError
        except ValueError:
            return {
                "status": "error",
                "message": "target_date must be in YYYY-MM-DD format.",
            }
        revisions = database.get_revisions_for_date(chat_id, target)
        return {
            "status": "ok",
            "target_date": target,
            "count": len(revisions),
            "revisions": revisions,
        }

    if name == "get_all_topics_and_cycles":
        topics = database.get_all_topics_with_schedule(chat_id)
        return {"status": "ok", "count": len(topics), "topics": topics}

    if name == "modify_existing_topic":
        query = _required_text(args, "current_title_query")
        action = _required_text(args, "action").lower()
        new_title = args.get("new_title") or ""
        if not isinstance(new_title, str):
            raise ValueError("new_title must be text.")
        result = database.delete_or_rename_topic(
            chat_id=chat_id,
            current_title_query=query,
            action=action,
            new_title=new_title,
        )
        return result

    return {
        "status": "error",
        "message": f"Unknown tool: {name}",
    }


def _fallback_reply(
    last_tool_name: str | None, last_tool_result: dict[str, Any] | None
) -> str:
    """Return a safe user-facing reply if the model exhausts its tool rounds."""
    if last_tool_name == "propose_study_topic" and last_tool_result:
        title = last_tool_result.get("proposed_title", "this topic")
        return f'Can I save this as "{title}"?'
    if last_tool_name == "confirm_pending_topic" and last_tool_result:
        title = last_tool_result.get("title", "your topic")
        schedule = last_tool_result.get("schedule", [])
        lines = [
            f'Locked in "{title}" for the 1, 3, 7 and 21-day revision cycle:'
        ]
        for item in schedule:
            lines.append(
                f"• Day {item.get('interval_day')} — "
                f"{item.get('scheduled_date')}"
            )
        return "\n".join(lines)
    if last_tool_name == "modify_existing_topic" and last_tool_result:
        return str(
            last_tool_result.get("message")
            or "I have updated that topic for you."
        )
    return "I have updated your revision records. What would you like to do next?"


async def process_user_message(
    chat_id: int, user_text: str, is_voice: bool = False
) -> str:
    """Run the agent/tool loop and persist the visible conversation turn."""
    if not isinstance(user_text, str) or not user_text.strip():
        raise ValueError("user_text cannot be empty.")

    today_str = _today_in_timezone()
    history = database.get_recent_chat_messages(chat_id, limit=10)
    prefix = "[Voice Note Transcript]: " if is_voice else ""

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": build_system_prompt(chat_id, today_str),
        },
        *history,
        {"role": "user", "content": f"{prefix}{user_text.strip()}"},
    ]

    final_reply = ""
    last_tool_name: str | None = None
    last_tool_result: dict[str, Any] | None = None
    llm_client = _get_client()

    # A maximum of three model calls keeps latency and API cost predictable.
    for _iteration in range(3):
        try:
            response = await llm_client.chat.completions.create(
                model=_model_name(),
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
            )
        except Exception:
            # If a database tool already succeeded, still give the user the
            # result instead of leaving a saved topic without a reply.
            if last_tool_result is None:
                raise
            logger.exception("LLM call failed after a successful tool call")
            final_reply = _fallback_reply(last_tool_name, last_tool_result)
            break
        assistant_msg = response.choices[0].message
        tool_calls = getattr(assistant_msg, "tool_calls", None)

        if tool_calls:
            messages.append(assistant_msg.model_dump(exclude_none=True))

            for tool_call in tool_calls:
                name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                    if not isinstance(args, dict):
                        raise TypeError("Tool arguments must be a JSON object.")
                    result = _execute_tool(name, args, chat_id, today_str)
                except Exception as exc:  # noqa: BLE001 - model must see the error
                    logger.warning("Tool %s failed: %s", name, exc)
                    result = {"status": "error", "message": str(exc)}

                last_tool_name = name
                last_tool_result = result
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            result, ensure_ascii=False, default=str
                        ),
                    }
                )
            continue

        final_reply = (assistant_msg.content or "").strip()
        break

    if not final_reply:
        final_reply = _fallback_reply(last_tool_name, last_tool_result)

    # Only the visible user/assistant turn is stored, not tool-call plumbing.
    database.add_chat_message(chat_id, "user", user_text.strip())
    database.add_chat_message(chat_id, "assistant", final_reply)
    return final_reply


__all__ = [
    "LLM_MODEL",
    "TOOLS",
    "build_system_prompt",
    "process_user_message",
]
