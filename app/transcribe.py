"""Local voice-message transcription via faster-whisper.

Runs entirely on CPU inside the container — no external API, no per-use cost.
The model is downloaded once into the mounted data volume so it survives
container rebuilds.
"""
import asyncio
import io
import logging

from config import (VOICE_LANG_MIN_PROB, VOICE_LANG_SHORT_SECONDS,
                    WHISPER_CACHE_DIR, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE,
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


def _whisper_code(lang: str | None, supported) -> str | None:
    """"pt-BR" / "it" / "" -> a code Whisper knows ("pt", "it") or None."""
    code = (lang or "").strip().lower().split("-")[0].split("_")[0]
    return code if code and code in supported else None


def _transcribe_sync(audio_bytes: bytes, hint: str | None) -> str:
    model = _get_model()

    def run(language):
        # Language detection happens here; the text is only decoded when the
        # segments are iterated, so a run we throw away costs little.
        return model.transcribe(
            io.BytesIO(audio_bytes),
            language=language,
            vad_filter=True,  # drop silence, avoids hallucinated text
        )

    segments, info = run(WHISPER_LANGUAGE or None)  # "" -> auto-detect
    if not WHISPER_LANGUAGE:
        detected = info.language
        prob = info.language_probability or 0.0
        duration = info.duration or 0.0
        fallback = _whisper_code(hint, model.supported_languages)
        unsure = duration < VOICE_LANG_SHORT_SECONDS or prob < VOICE_LANG_MIN_PROB
        if fallback and fallback != detected and unsure:
            log.info("voice language %s (p=%.2f, %.1fs) not trusted -> using %s",
                     detected, prob, duration, fallback)
            segments, info = run(fallback)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    log.info("transcribed %.1fs audio (lang=%s, p=%.2f) -> %d chars",
             getattr(info, "duration", 0.0), getattr(info, "language", "?"),
             getattr(info, "language_probability", 0.0) or 0.0, len(text))
    return text


async def transcribe(audio_bytes: bytes, hint: str | None = None) -> str:
    """Transcribe an Opus/OGG voice note. Runs the blocking model in a thread
    so the asyncio event loop (and the rest of the bot) stays responsive.

    hint: the language this chat is likely in, used instead of Whisper's own
    guess when that guess is unreliable (very short clip, low confidence)."""
    if not WHISPER_ENABLED:
        raise RuntimeError("voice transcription disabled (WHISPER_ENABLED=0)")
    return await asyncio.to_thread(_transcribe_sync, audio_bytes, hint)
