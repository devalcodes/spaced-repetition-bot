"""Adaptive speech-to-text for Telegram voice notes.

Two modes are supported:

* ``STT_MODE=local`` - free, offline transcription via faster-whisper.  The
  model is imported and loaded lazily so text-only usage stays lightweight.
* ``STT_MODE=api`` - any OpenAI-compatible ``/audio/transcriptions`` endpoint
  (Groq's whisper-large-v3-turbo, OpenAI's whisper-1, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_local_model: Any | None = None
_local_model_name: str | None = None
_local_files_only: bool | None = None
_model_lock = threading.Lock()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _settings() -> dict[str, Any]:
    """Read STT settings at call time so dotenv can load first."""
    return {
        "mode": os.getenv("STT_MODE", "local").strip().lower(),
        "local_model": os.getenv("LOCAL_WHISPER_MODEL", "base").strip() or "base",
        "local_files_only": _env_bool("LOCAL_WHISPER_LOCAL_FILES_ONLY", False),
        "base_url": os.getenv("STT_BASE_URL", "https://api.openai.com/v1").strip(),
        "api_key": os.getenv("STT_API_KEY", "").strip(),
        "model": os.getenv("STT_MODEL", "whisper-1").strip() or "whisper-1",
    }


def _get_local_model(model_name: str, local_files_only: bool = False) -> Any:
    """Load and cache faster-whisper's WhisperModel exactly once."""
    global _local_model, _local_model_name, _local_files_only

    with _model_lock:
        if (
            _local_model is None
            or _local_model_name != model_name
            or _local_files_only != local_files_only
        ):
            from faster_whisper import WhisperModel

            logger.info(
                "Loading local Whisper model '%s' (CPU, int8, local_files_only=%s).",
                model_name,
                local_files_only,
            )
            _local_model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                local_files_only=local_files_only,
            )
            _local_model_name = model_name
            _local_files_only = local_files_only
        return _local_model


def _transcribe_local_sync(
    file_path: str, model_name: str, local_files_only: bool
) -> str:
    """Synchronous faster-whisper work; always executed in a worker thread."""
    model = _get_local_model(model_name, local_files_only)
    segments, _info = model.transcribe(file_path, beam_size=5)

    # ``segments`` is a lazy generator, so it must be consumed in this thread.
    return " ".join(
        segment.text.strip() for segment in segments if segment.text.strip()
    ).strip()


async def _transcribe_with_api(file_path: str, settings: dict[str, Any]) -> str:
    from openai import AsyncOpenAI

    if not settings["api_key"]:
        raise RuntimeError(
            "STT_API_KEY is required when STT_MODE=api. "
            "Set it in your .env file."
        )

    client = AsyncOpenAI(
        base_url=settings["base_url"],
        api_key=settings["api_key"],
    )
    with open(file_path, "rb") as audio_file:  # noqa: ASYNC230 - SDK needs a file
        transcription = await client.audio.transcriptions.create(
            model=settings["model"],
            file=audio_file,
        )
    return (transcription.text or "").strip()


async def transcribe_audio_file(file_path: str) -> str:
    """Transcribe a Telegram ``.ogg`` voice note using the configured mode.

    Args:
        file_path: Path to the downloaded temporary audio file.

    Returns:
        The stripped transcript.  An empty string means no speech was found.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    settings = _settings()
    mode = settings["mode"]

    if mode == "api":
        return await _transcribe_with_api(str(path), settings)
    if mode != "local":
        raise RuntimeError(
            f"Unknown STT_MODE '{mode}'. Use either 'local' or 'api'."
        )

    transcript = await asyncio.to_thread(
        _transcribe_local_sync,
        str(path),
        settings["local_model"],
        settings["local_files_only"],
    )
    return transcript.strip()


# Compatibility alias for the capitalised spelling used in some integrations.
transcribe_Audio_file = transcribe_audio_file
