# ReviseBot AI Setup Prompt

This file is for someone who wants an AI coding agent to install and launch ReviseBot for them.

## How to use it

1. Download or clone this repository and open the **project folder** in an AI coding tool that has terminal and file access: Claude Code, Codex, Cursor, Windsurf, DeepSeek Harness, etc.
2. Open `AI_SETUP_PROMPT.md` and copy everything inside the box below.
3. Paste it into the agent and send it.
4. The agent will ask for your Telegram token and LLM key once, put them in `.env`, install the bot, test it, and guide you through going live.

> The agent needs shell access. A plain chat window that cannot read files or run commands cannot complete this setup.

## Copy this prompt

````markdown
You are a senior Python engineer and deployment agent. Install, launch, test, and production-harden the ReviseBot 1-3-7-21 Telegram spaced-repetition bot for me. Do the work yourself using file and terminal tools. Do not hand me a checklist and call it done. Keep working until the acceptance checklist passes, or stop only when you are blocked on a secret, permission, or decision that only I can provide.

## 0. Find and understand the project

Search the current directory and one level above it for a folder containing all of these:

- `main.py`
- `database.py`
- `.env.example`
- `requirements.txt`

If you cannot find it, ask me for the exact folder path or repository URL. Do not create a new project from scratch and do not invent files. Treat the existing code as the source of truth.

Read these files before changing anything:

1. `README.md`
2. `.env.example`
3. `main.py`
4. `agent.py`
5. `transcriber.py`
6. `database.py`
7. `scheduler.py`

Do not change the database schema, replace the framework, or introduce Docker/Kubernetes unless I explicitly ask.

Work only inside the project folder. At the end, report the absolute path.

## 1. Interaction rules

- Ask for every missing secret/decision in one concise message, not one question at a time.
- Never print API keys, bot tokens, or the contents of `.env` back to me.
- Never commit `.env`. Confirm that `.gitignore` protects `.env`, `study_memory.db`, `.venv/`, and `__pycache__/`.
- If `.env` already exists, back it up before editing and merge changes instead of silently deleting existing values.
- Never hard-code secrets into `.py` files, README, shell history, or source control.
- Do not invent a Telegram token or API key. If a key is invalid, ask me for a new one.
- If a command fails, diagnose it and fix it. Do not report success without evidence.

## 2. Tell me how to create the Telegram bot

If I do not already have a bot token, guide me through this and wait for the token:

1. Open Telegram and message **@BotFather**.
2. Send `/newbot`.
3. Choose a display name, for example `ReviseBot`.
4. Choose a username that ends in `bot`, for example `my_revise_bot`.
5. BotFather returns a token like `123456789:AA...`. Send it to me privately through this chat.
6. Treat that token like a password. Never share it publicly or commit it.

After the token is available, optionally configure the command menu with BotFather using `/setcommands`:

```text
start - Welcome and instructions
today - See today's revisions
schedule - View all saved topics
test_morning - Preview today's digest
```

Do not add `seed_demo` to the public command menu because it replaces saved topics with demo data.

## 3. Collect LLM configuration

Ask me to choose one provider and supply its API key. Use the latest available **DeepSeek Flash** model for the DeepSeek options.

### Option A: DeepSeek direct (default)

```env
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=<my DeepSeek key>
```

Get a key from `https://platform.deepseek.com/api_keys`. If the API returns `401 invalid api key`, stop retrying and ask me for a fresh key. Never loop on a bad key.

### Option B: OpenRouter

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-v4.1-flash-1017
LLM_API_KEY=<my OpenRouter key>
```

If that slug is no longer current when you run this, inspect OpenRouter's model list and use the newest DeepSeek Flash slug. Confirm the chosen model supports tool/function calling before proceeding.

### Option C: Another OpenAI-compatible provider

Use my supplied base URL, model, and key. Examples:

- OpenAI: `https://api.openai.com/v1`, `gpt-4o-mini`
- Google Gemini: `https://generativelanguage.googleapis.com/v1beta/openai/`, `gemini-2.5-flash`
- Groq: `https://api.groq.com/openai/v1`, `llama-3.3-70b-versatile`
- Local Ollama: `http://localhost:11434/v1`, `llama3.1`, key `ollama`

Do not silently switch providers or models. Tell me what you selected and why.

## 4. Collect timezone and reminder settings

Ask me for:

- My IANA timezone, for example `Asia/Kolkata`, `Europe/London`, or `America/New_York`
- The hour and minute for my daily digest in 24-hour time, default `09:00`

Validate the timezone with Python `zoneinfo.ZoneInfo`. Validate the hour (`0-23`) and minute (`0-59`). Do not use a fixed UTC offset.

## 5. Configure voice transcription

Default to fully local, offline speech-to-text:

```env
STT_MODE=local
LOCAL_WHISPER_MODEL=base
LOCAL_WHISPER_LOCAL_FILES_ONLY=false
```

Explain that:

- `faster-whisper` runs on CPU with `int8`.
- Telegram `.ogg` files are decoded by bundled PyAV; no system FFmpeg is needed.
- The first voice note downloads the Whisper model once.
- `base` is the default balance of speed and accuracy. `tiny` is faster on weak machines; `small` is more accurate but slower.

If a faster-whisper model is already cached, offer to point `LOCAL_WHISPER_MODEL` at its directory and set `LOCAL_WHISPER_LOCAL_FILES_ONLY=true` to guarantee no downloads. A usable model directory contains `model.bin`, `config.json`, `tokenizer.json`, and `vocabulary.txt`.

Only use cloud transcription if I choose it:

```env
STT_MODE=api
STT_BASE_URL=https://api.groq.com/openai/v1
STT_API_KEY=<my Groq or OpenAI key>
STT_MODEL=whisper-large-v3-turbo
```

Do not ask for an STT API key when `STT_MODE=local`.

## 6. Create `.env`

Copy `.env.example` to `.env` if needed, then write the values I supplied. At minimum:

```env
TELEGRAM_BOT_TOKEN=<real token>
TIMEZONE=<real IANA timezone>
REMINDER_HOUR=<0-23>
REMINDER_MINUTE=<0-59>
LLM_BASE_URL=<provider base URL>
LLM_API_KEY=<provider key>
LLM_MODEL=<provider model>
STT_MODE=local
LOCAL_WHISPER_MODEL=base
LOCAL_WHISPER_LOCAL_FILES_ONLY=false
```

On macOS/Linux, run `chmod 600 .env` after creating it. Confirm `.env` is ignored by Git.

## 7. Install the application

Detect the operating system and Python version. Require Python 3.10 or newer. If Python is missing, guide me through installing it for my OS.

Create and use a virtual environment:

**Windows PowerShell:**

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS/Linux:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Use the virtual environment's Python executable for every later command. Do not rely on shell activation.

If installation fails, capture the exact error and fix the cause. Do not remove dependencies from `requirements.txt` just to make the error disappear.

## 8. Run offline smoke tests

From the project directory, verify:

```bash
python -m py_compile database.py transcriber.py agent.py scheduler.py main.py
python -c "import database, transcriber, agent, scheduler, main; print('imports ok')"
```

Initialize and inspect the database. Confirm these four tables exist:

- `topics`
- `revisions`
- `pending_drafts`
- `chat_messages`

Confirm a test topic creates exactly four revisions on days 1, 3, 7, and 21. Do not leave test rows in the real database.

If `python-telegram-bot[job-queue]` is missing, install the requirements again; do not ignore the `JobQueue is unavailable` error.

## 9. Start the bot and verify startup

Start the bot in a controlled foreground or managed background process:

```bash
python main.py
```

Confirm the logs show all of these:

1. `Starting Telegram bot id ...`
2. `Connected to Telegram as @<expected username>`
3. The expected LLM base URL and model
4. `STT: local faster-whisper ...`
5. No traceback
6. No `401`, `402`, `409`, or repeated `500` errors

If the connected username is not the bot I gave you the token for:

- Stop the process.
- Check for stale `TELEGRAM_BOT_TOKEN` values in the OS environment.
- Confirm `.env` is loaded with `override=True`.
- Restart and verify again.

Only one process may long-poll a bot token. If you see Telegram `409 Conflict`, stop duplicate instances before continuing.

## 10. Run live Telegram acceptance tests

Ask me to open the bot and press Start. Then verify:

1. `/start` returns the welcome message.
2. `/today` returns either today's revision list or a clear "nothing due" message.
3. `/schedule` returns saved topics with all four revision dates.
4. I send a text such as: `I studied photosynthesis today. Plants use sunlight, water and CO2 to make glucose and release oxygen.`
5. The bot proposes a 3 to 4 word title and asks for confirmation.
6. I reply `yes`.
7. The bot confirms the exact Day 1, Day 3, Day 7, and Day 21 dates.
8. The SQLite database contains one topic and exactly four revision rows, dated `studied_date + 1`, `+3`, `+7`, and `+21` days.
9. I send a real voice note; the local Whisper model transcribes it and the normal confirmation flow continues.
10. For a disposable test chat only, `/seed_demo` followed by `/test_morning` produces the consolidated morning digest. Warn me first that `/seed_demo` deletes existing topics for that chat.

Inspect the database after each step to confirm the bot actually saved what it claimed. Report exact observed results, not assumptions.

## 11. Prepare production operation

Choose the option that fits my environment and ask before installing a system service.

### Linux VPS: systemd

Create a unit like `/etc/systemd/system/revisebot.service`, replacing paths and user:

```ini
[Unit]
Description=ReviseBot Telegram study bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=revisebot
WorkingDirectory=/opt/revisebot
ExecStart=/opt/revisebot/.venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now revisebot
sudo systemctl status revisebot
```

### Windows: Task Scheduler or NSSM

Ask whether I want Task Scheduler or NSSM. Configure the bot to start at login/boot with the `.venv` Python executable and the project folder as the working directory. Point logs to a file so failures are visible.

### macOS: launchd

Create a user LaunchAgent that runs `.venv/bin/python main.py` in the project directory and keeps it alive.

### Production checklist

- Exactly one bot instance per token.
- The process restarts automatically after crash/reboot.
- The machine stays awake and online for the daily 09:00 job.
- Timezone is correct and the job is registered at startup.
- `study_memory.db` is backed up regularly by copying the single file while the bot is stopped, or by using SQLite's backup mechanism.
- `.env` is readable only by the bot user.
- API keys can be rotated without code changes.
- Logs do not contain secrets.
- The bot uses long polling, so no inbound firewall ports are required.
- If the process is offline at the reminder time, that day's digest is not replayed automatically; start the process before the reminder time.

## 12. Final acceptance checklist

Do not claim success until every item is true and observed:

- [ ] Project found and only that project modified.
- [ ] Python 3.10+ virtual environment created.
- [ ] `requirements.txt` installed successfully.
- [ ] `.env` exists, is complete, and is Git-ignored.
- [ ] No secrets appear in source files or the final report.
- [ ] Telegram token validated with the expected bot username.
- [ ] LLM endpoint and latest DeepSeek Flash model validated with a real request.
- [ ] Local Whisper model loaded successfully in offline/local-files mode.
- [ ] All five Telegram commands are registered.
- [ ] `/start` and `/schedule` respond live.
- [ ] A real text message creates a topic plus four revisions.
- [ ] A real voice note is transcribed and creates a topic plus four revisions.
- [ ] The 09:00 daily JobQueue job is registered.
- [ ] Duplicate-instance / token-mismatch issues are resolved.
- [ ] Auto-restart and one-instance production setup are done or explicitly declined by me.
- [ ] Backup location for `study_memory.db` is documented.

## 13. Final report

Give me a short report with:

- Absolute project path
- Operating system and Python version
- Bot username
- LLM provider, base URL, and model
- STT mode and model
- Timezone and reminder time
- Exact commands to start and stop the bot
- Whether auto-restart was configured
- The live tests you observed
- The database path and backup instruction
- Any remaining action that only I can perform

Never include the Telegram token, API keys, or `.env` contents in the report.
````

## After setup

Once the agent reports success, test the bot yourself:

```text
/start
Today I studied the nitrogen cycle. Nitrogen-fixing bacteria convert N2 into ammonia, and nitrifying bacteria convert it into nitrites and nitrates.
```

Confirm the proposed title, reply `yes`, and verify all four dates. Then send a voice note to test the local transcription path.

---

## Manual quickstart

If you prefer to set it up yourself, see [README.md](README.md#2-minute-quickstart).
