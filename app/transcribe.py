"""Local voice-message transcription via faster-whisper.

Runs entirely on CPU inside the container — no external API, no per-use cost.
The model is downloaded once into the mounted data volume so it survives
container rebuilds.
"""
import asyncio
import io
import logging

from config import (WHISPER_CACHE_DIR, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE,
                    WHISPER_ENABLED, WHISPER_LANGUAGE, WHISPER_MODEL)

log = logging.getLogger(__name__)

_model = None  # lazy: loaded on first voice message, then reused


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        log.info("Loading faster-whisper model=%s device=%s compute=%s",
                 WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE)
        _model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
            download_root=str(WHISPER_CACHE_DIR),
        )
    return _model


def _transcribe_sync(audio_bytes: bytes) -> str:
    model = _get_model()
    segments, info = model.transcribe(
        io.BytesIO(audio_bytes),
        language=WHISPER_LANGUAGE or None,  # "" -> auto-detect
        vad_filter=True,                    # drop silence, avoids hallucinated text
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    log.info("transcribed %.1fs audio (lang=%s) -> %d chars",
             getattr(info, "duration", 0.0), getattr(info, "language", "?"), len(text))
    return text


async def transcribe(audio_bytes: bytes) -> str:
    """Transcribe an Opus/OGG voice note. Runs the blocking model in a thread
    so the asyncio event loop (and the rest of the bot) stays responsive."""
    if not WHISPER_ENABLED:
        raise RuntimeError("voice transcription disabled (WHISPER_ENABLED=0)")
    return await asyncio.to_thread(_transcribe_sync, audio_bytes)
