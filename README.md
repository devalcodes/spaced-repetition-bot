# ReviseBot — 1-3-7-21 Spaced Repetition Telegram Bot

A tiny, self-hosted Telegram study companion that listens to what you learned, gives it a short title, and schedules four revisions on the **1st, 3rd, 7th, and 21st day** after you study it.

No web dashboard. No note-taking friction. Just send a voice note or text, confirm the title, and get one clean revision digest every morning at 9:00 AM.

---

## How it works

The Ebbinghaus forgetting curve shows that memory drops fastest right after learning. Reviewing at increasing intervals interrupts that forgetting.

| When | What happens |
|---|---|
| Day 0 | You study a topic and tell the bot about it. |
| Day 1 | First revision, while the memory is fresh. |
| Day 3 | Second revision, just as recall starts to weaken. |
| Day 7 | Third revision, rebuilding the memory with less effort. |
| Day 21 | Final revision, moving the topic toward long-term memory. |

If you study **Thermodynamics Second Law** on `29 Oct 2026`, the bot schedules:

- Day 1 — `30 Oct 2026`
- Day 3 — `01 Nov 2026`
- Day 7 — `05 Nov 2026`
- Day 21 — `19 Nov 2026`

Every morning at your configured reminder time, the bot sends **one consolidated message** listing only the topics due that day — no spam, no 21 separate reminders.

### What makes it feel natural

- **Voice notes are first-class.** Send a Telegram voice note; it is transcribed, summarized, and titled automatically.
- **You approve the title.** The bot proposes a short 3–4 word title first. Reply `yes`, or correct it (`call it Nernst Equation Basics`).
- **Ask questions later.** “What do I need to revise today?”, “What was my note on haloalkanes?”, or “Delete the thermodynamics topic” all work conversationally.
- **Provider-agnostic brain.** DeepSeek, OpenAI, Gemini, Groq, OpenRouter, or a local Ollama model — all through one OpenAI-compatible client.
- **Local-first option.** Offline voice transcription via `faster-whisper`; no system FFmpeg installation required.

---

## Let an AI agent install it for you

Not comfortable with terminals? Open this folder in Claude Code, Codex, Cursor, Windsurf, or DeepSeek Harness, then paste the ready-made prompt from [AI_SETUP_PROMPT.md](AI_SETUP_PROMPT.md).

The agent will find the project, guide you through creating a Telegram bot with @BotFather, collect your LLM key and timezone, write them into `.env`, install dependencies, test text and voice notes, and help you set up auto-restart for production.

---

## 2-Minute Quickstart

### Prerequisites

- Python **3.10 or newer**
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An API key for any OpenAI-compatible LLM provider (DeepSeek is the default)

### 1. Clone and install

```bash
git clone <YOUR_REPOSITORY_URL> spaced-repetition-bot
cd spaced-repetition-bot

python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 2. Create your `.env`

```bash
# macOS / Linux
cp .env.example .env

# Windows PowerShell
# Copy-Item .env.example .env
```

Open `.env` and set at least these three values:

```env
TELEGRAM_BOT_TOKEN=123456789:your_real_bot_token
LLM_API_KEY=your_deepseek_api_key
LLM_MODEL=deepseek-flash
```

### 3. Run

```bash
python main.py
```

Open your bot in Telegram, press **Start**, and send:

```text
I studied the second law of thermodynamics today — entropy always increases in an isolated system.
```

The bot proposes a short title. Confirm it. Your 1-3-7-21 cycle is now scheduled.

> **First voice note:** with `STT_MODE=local`, the bot downloads the selected Whisper model once on first use. `base` is a good balance of speed and accuracy on CPU.

---

## Choose your LLM

All presets use the same `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` variables. Change the block in `.env` and restart the bot.

### DeepSeek (default — latest Flash model)

```env
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your_deepseek_api_key
LLM_MODEL=deepseek-flash
```

### OpenAI

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

### Google Gemini (OpenAI-compatible endpoint)

```env
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=your_gemini_api_key
LLM_MODEL=gemini-2.5-flash
```

### Groq

```env
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...
LLM_MODEL=llama-3.3-70b-versatile
```

### OpenRouter (DeepSeek V4.1 Flash)

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-...
LLM_MODEL=deepseek/deepseek-v4.1-flash-1017
```

### Local Ollama

```bash
ollama pull llama3.1
ollama serve
```

```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.1
```

Any non-empty key works for Ollama. The bot never contacts a provider other than the one configured in `LLM_BASE_URL`.

---

## Voice transcription: local or cloud

### Local, free, offline (default)

```env
STT_MODE=local
LOCAL_WHISPER_MODEL=base
LOCAL_WHISPER_LOCAL_FILES_ONLY=false
```

Uses `faster-whisper` on CPU with `compute_type="int8"`. Its bundled PyAV handles Telegram's `.ogg` files, so **you do not need to install FFmpeg**. The model is lazy-loaded only when the first voice note arrives. Try `tiny`, `base`, `small`, or `medium` for different speed/accuracy tradeoffs.

If the model is already downloaded, point directly at its folder and forbid downloads:

```env
STT_MODE=local
LOCAL_WHISPER_MODEL=C:/Users/you/.cache/huggingface/hub/models--Systran--faster-whisper-base/snapshots/<snapshot-hash>
LOCAL_WHISPER_LOCAL_FILES_ONLY=true
```

The folder must contain `model.bin`, `config.json`, `tokenizer.json`, and `vocabulary.txt`. With `LOCAL_WHISPER_LOCAL_FILES_ONLY=true`, the bot never contacts Hugging Face.

### Cloud Whisper API

```env
STT_MODE=api
STT_BASE_URL=https://api.groq.com/openai/v1
STT_API_KEY=your_groq_api_key
STT_MODEL=whisper-large-v3-turbo
```

This works with Groq Whisper, OpenAI Whisper, or any compatible `/audio/transcriptions` endpoint. OpenAI example:

```env
STT_MODE=api
STT_BASE_URL=https://api.openai.com/v1
STT_API_KEY=sk-...
STT_MODEL=whisper-1
```

> In local mode, audio never leaves your machine. In API mode, the voice file is uploaded to your chosen STT provider. The LLM receives transcripts, summaries, and scheduling data — not raw audio.

---

## Daily digest configuration

```env
TIMEZONE=Asia/Kolkata
REMINDER_HOUR=9
REMINDER_MINUTE=0
```

`TIMEZONE` accepts any IANA timezone name, such as `Europe/London`, `America/New_York`, or `Asia/Tokyo`. The bundled `tzdata` package provides timezone data on systems (including Windows) that may lack it.

The job is registered with Telegram's `JobQueue` when the bot starts. Keep the bot process running for reminders to fire.

---

## Demo commands

Want to see the 9:00 AM experience immediately, without waiting?

1. Send `/seed_demo`
   Creates three realistic topics whose Day 1, Day 3, and Day 7 revisions are due **today**.
2. Send `/test_morning`
   Sends the exact consolidated morning digest to the current chat right now.

> `/seed_demo` clears that chat's existing saved topics and revisions first. It is intended for testing and video demos, not daily use.

### Example digest

```text
☀️ Good morning! Here is your revision lineup for today (29 Oct 2026):

• Thermodynamics Second Law (Day 1 Revision)
• Electrochemistry Nernst Equation (Day 3 Revision)
• Organic Haloalkanes (Day 7 Revision)

Reply anytime if you have doubts on these topics or want to log what you study today!
```

---

## Commands

| Command | Purpose |
|---|---|
| `/start` | Welcome, method overview, and instructions. |
| `/today` | Show revisions due today for this chat. |
| `/schedule` | Show every saved topic with all four revision dates. |
| `/seed_demo` | Replace this chat's topics with three demo topics due today. |
| `/test_morning` | Send today's 9:00 AM digest immediately. |

You can also talk to the bot without commands:

- “I studied SN1 and SN2 reactions in haloalkanes today.”
- “Yes, save it.”
- “Call it Haloalkane Substitution instead.”
- “What do I need to revise today?”
- “What was my note on the Nernst equation?”
- “Rename thermodynamics to Second Law Basics.”
- “Delete the electrochemistry topic.”

---

## Project structure

```text
spaced-repetition-bot/
├── .env.example      # Copy to .env and configure
├── .gitignore        # Keeps .env and local data out of Git
├── AI_SETUP_PROMPT.md # Copy-paste prompt for an AI coding agent
├── requirements.txt  # Runtime dependencies
├── README.md
├── database.py       # SQLite schema and all data access
├── transcriber.py    # Local faster-whisper / cloud Whisper adapter
├── agent.py          # LLM prompt, tools, and tool-calling loop
├── scheduler.py      # Morning digest formatter and JobQueue job
└── main.py           # Telegram handlers, commands, and startup
```

All study data lives in `study_memory.db`, created automatically next to the code on first run. Back it up by copying that single file.

---

## Troubleshooting

**The bot is running and polling, but never replies**
Check the startup log line:

```text
Connected to Telegram as @your_bot_username (bot id ...)
```

Message **that exact bot**. If the username is not the one in your `.env`, a stale `TELEGRAM_BOT_TOKEN` may be set in your Windows user environment. This project loads `.env` with `override=True`, so it wins on the next restart. You can also clear the old variable with:

```powershell
[Environment]::SetEnvironmentVariable("TELEGRAM_BOT_TOKEN", $null, "User")
```

**`JobQueue is unavailable`**
Install with the extras included in the requirements file:

```bash
pip install "python-telegram-bot[job-queue]>=21.5"
```

**`TELEGRAM_BOT_TOKEN is missing`**
Copy `.env.example` to `.env` (not `.env.example`), add your BotFather token, and restart from the project directory.

**The bot replies but no morning message arrives**
Confirm the process is still running, check `TIMEZONE`, and verify there is a revision scheduled for today with `/today`.

**`401 Authentication Fails` from DeepSeek**
Speech-to-text is not the problem in this case. The LLM rejected `LLM_API_KEY`. Create a fresh key at [platform.deepseek.com](https://platform.deepseek.com/api_keys), replace `LLM_API_KEY` in `.env`, and restart the bot.

**Voice note says it could not process the audio**
For local mode, the first run may still be downloading the Whisper model — check the logs and try again. For API mode, verify `STT_API_KEY`, `STT_BASE_URL`, and `STT_MODEL`.

**Gemini returns 404**
Keep the trailing slash in the Gemini base URL: `https://generativelanguage.googleapis.com/v1beta/openai/`.

**Ollama connection refused**
Run `ollama serve`, confirm the model is pulled, and use `http://localhost:11434/v1` as the base URL.

**Windows PowerShell does not run the virtual environment**
If script execution is blocked for the current session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

---

## Design notes

- The database uses `sqlite3` with `PRAGMA foreign_keys = ON`; deleting a topic cascades to its four revisions.
- Titles are kept to 3–4 words for a clean daily digest and easy recall.
- Chat history is trimmed to the latest 12 messages per chat so prompts remain small and cheap.
- Voice transcription runs in a worker thread, so CPU-bound Whisper work never blocks Telegram updates.
- The agent can stage, confirm, inspect, rename, and delete topics through five typed tools. It cannot invent revision dates: all dates come from SQLite.

Built to be forked, self-hosted, and modified. If it helps you remember more, share it with a study buddy.
