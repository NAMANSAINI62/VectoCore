"""OpenRouter text-to-speech used by the chatbot's "Read aloud" action."""

import base64
import io
import logging
import wave

import httpx
from fastapi import HTTPException, status

from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _openrouter_headers() -> dict[str, str]:
    if not settings.OPENROUTER_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenRouter is not configured. Set OPENROUTER_API_KEY in the backend environment.",
        )
    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.FRONTEND_URL,
        "X-OpenRouter-Title": settings.APP_NAME,
    }


def _raise_upstream_error(response: httpx.Response) -> None:
    logger.warning("OpenRouter speech request failed with status %s", response.status_code)
    if response.status_code == 429:
        detail = "The speech model is rate-limited. Retry later."
        code = status.HTTP_429_TOO_MANY_REQUESTS
    elif response.status_code == 402:
        detail = "The OpenRouter account has insufficient credits or the API key spend limit was reached."
        code = status.HTTP_402_PAYMENT_REQUIRED
    elif response.status_code in (401, 403):
        detail = "OpenRouter rejected this request. Check the key, model access, and model terms."
        code = status.HTTP_502_BAD_GATEWAY
    elif response.status_code >= 500:
        detail = "The speech provider is temporarily unavailable."
        code = status.HTTP_502_BAD_GATEWAY
    else:
        detail = f"OpenRouter rejected the speech synthesis request (HTTP {response.status_code})."
        code = status.HTTP_502_BAD_GATEWAY
    raise HTTPException(status_code=code, detail=detail)


def _pcm_to_wav(pcm_data: bytes, sample_rate: int | None = None) -> bytes:
    """Wrap raw signed 16-bit mono PCM audio in a WAV container for browsers."""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate or settings.TTS_PCM_SAMPLE_RATE)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


async def synthesize_speech(text: str) -> tuple[str, str]:
    """Return base64 WAV audio from the configured text-to-speech model."""
    async with httpx.AsyncClient(timeout=settings.OPENROUTER_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/audio/speech",
            headers=_openrouter_headers(),
            json={"model": settings.TEXT_TO_SPEECH_MODEL, "input": text, "response_format": "pcm"},
        )
    if not response.is_success:
        _raise_upstream_error(response)
    if not response.headers.get("content-type", "").startswith("audio/"):
        raise HTTPException(status_code=502, detail="The speech provider returned an invalid audio response.")
    return base64.b64encode(_pcm_to_wav(response.content)).decode("ascii"), "audio/wav"
