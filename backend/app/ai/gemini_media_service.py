"""Gemini TTS & Audio Transcription service backed by google-genai and quota-aware model rotation."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from typing import Any

from fastapi import HTTPException, status
from google import genai
from google.genai import types

from app.ai.openrouter_service import _pcm_to_wav, synthesize_speech as openrouter_synthesize_speech
from app.config.settings import get_settings
from app.llm.registry import get_quota_router

logger = logging.getLogger(__name__)
settings = get_settings()

_RATE_PARAM_RE = re.compile(r"rate=(\d+)", re.IGNORECASE)


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _extract_audio_part(response: Any) -> tuple[bytes, str] | None:
    """Extract inline audio bytes and mime type from a google-genai GenerateContentResponse."""
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                data = inline.data
                raw_bytes = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                mime = str(getattr(inline, "mime_type", "") or "audio/L16;rate=24000")
                return raw_bytes, mime
    return None


def _is_quota_or_transient_error(exc: Exception) -> tuple[bool, bool]:
    text = str(exc).lower()
    name = type(exc).__name__.lower()
    is_rate = "429" in text or "quota" in text or "resourceexhausted" in name or "rate" in text
    is_transient = is_rate or "503" in text or "504" in text or "timeout" in text or "notfound" in name or "404" in text
    is_daily = "per-day" in text or "per day" in text or "daily" in text or "rpd" in text
    return is_transient, is_daily


async def synthesize_speech_with_fallback(text: str, *, voice_name: str = "Kore") -> tuple[str, str]:
    """Synthesize speech via quota-aware Gemini TTS pool, falling back to OpenRouter TTS if unavailable."""
    clean_text = (text or "").strip()
    if not clean_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Text cannot be empty.")

    router = get_quota_router()
    gemini_key = settings.GEMINI_API_KEY.strip()
    tts_models = _split_csv(settings.GEMINI_TTS_MODELS)

    if gemini_key and tts_models:
        client = genai.Client(api_key=gemini_key)
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        )
        for model_id in tts_models:
            healthy, skip_reason = router.check_availability("gemini", model_id)
            if not healthy:
                logger.info("Skipping Gemini TTS model %s (%s)", model_id, skip_reason)
                continue
            try:
                router.record_request("gemini", model_id)
                response = await client.aio.models.generate_content(
                    model=model_id,
                    contents=clean_text,
                    config=config,
                )
                extracted = _extract_audio_part(response)
                if extracted is None:
                    continue
                audio_bytes, mime = extracted
                lower_mime = mime.lower()
                if "wav" in lower_mime:
                    return base64.b64encode(audio_bytes).decode("ascii"), "audio/wav"
                if "mp3" in lower_mime or "mpeg" in lower_mime:
                    return base64.b64encode(audio_bytes).decode("ascii"), "audio/mpeg"
                if "ogg" in lower_mime:
                    return base64.b64encode(audio_bytes).decode("ascii"), "audio/ogg"
                rate_match = _RATE_PARAM_RE.search(mime)
                sample_rate = int(rate_match.group(1)) if rate_match else settings.GEMINI_TTS_SAMPLE_RATE
                wav_bytes = _pcm_to_wav(audio_bytes, sample_rate=sample_rate)
                return base64.b64encode(wav_bytes).decode("ascii"), "audio/wav"
            except Exception as exc:
                should_retry, is_daily = _is_quota_or_transient_error(exc)
                if should_retry:
                    router.mark_rate_limited("gemini", model_id, is_daily=is_daily, reason=type(exc).__name__)
                    logger.warning("Gemini TTS model %s failed (%s); rotating to next TTS model.", model_id, type(exc).__name__)
                    continue
                logger.warning("Gemini TTS model %s error (%s); falling back.", model_id, exc)
                break

    if settings.OPENROUTER_API_KEY.strip():
        return await openrouter_synthesize_speech(clean_text)

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No healthy TTS backend is currently available.",
    )


async def transcribe_audio_with_gemini(
    audio_bytes: bytes,
    *,
    mime_type: str,
    target_language: str | None = None,
) -> tuple[str, str]:
    """Transcribe (and optionally translate) uploaded audio using Gemini's transcribe model."""
    gemini_key = settings.GEMINI_API_KEY.strip()
    if not gemini_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key is required for audio transcription.",
        )
    if not audio_bytes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Audio payload is empty.")

    router = get_quota_router()
    candidates = [settings.GEMINI_TRANSCRIBE_MODEL.strip() or "gemini-3.5-transcribe", "gemini-2.5-flash"]
    prompt = (
        f"Transcribe this audio accurately and translate the output cleanly into {target_language.strip()}."
        if target_language and target_language.strip()
        else "Transcribe this audio accurately word for word. Return only the transcription text."
    )
    client = genai.Client(api_key=gemini_key)
    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type or "audio/wav")

    last_exc: Exception | None = None
    for model_id in candidates:
        healthy, _ = router.check_availability("gemini", model_id)
        if not healthy:
            continue
        try:
            router.record_request("gemini", model_id)
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[prompt, audio_part],
            )
            transcript = (getattr(response, "text", None) or "").strip()
            if transcript:
                return transcript, model_id
        except Exception as exc:
            last_exc = exc
            should_retry, is_daily = _is_quota_or_transient_error(exc)
            if should_retry:
                router.mark_rate_limited("gemini", model_id, is_daily=is_daily, reason=type(exc).__name__)
                continue
            break

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Audio transcription failed ({type(last_exc).__name__ if last_exc else 'no transcript returned'}).",
    )


_LIVE_MODE_DEFAULTS: dict[str, tuple[str, ...]] = {
    "translate": (
        "gemini-3.8-live",
        "gemini-3.1-flash-live-preview",
        "gemini-3.5-live-translate-preview",
    ),
    "extended_thinking": (
        "gemini-3.8-live-extended-thinking",
        "gemini-3.8-live",
        "gemini-3.1-flash-live-preview",
    ),
    "preview": (
        "gemini-3.8-live",
        "gemini-3.1-flash-live-preview",
        "gemini-3.8-live-extended-thinking",
    ),
}


def _live_candidate_models(mode: str, preferred_model: str | None) -> list[str]:
    configured = [m for m in _split_csv(settings.GEMINI_LIVE_MODELS) if mode != "translate" or "translate" not in m]
    mode_defaults = _LIVE_MODE_DEFAULTS.get(mode, _LIVE_MODE_DEFAULTS["preview"])
    ordered: list[str] = []
    for candidate in ([preferred_model.strip()] if preferred_model and preferred_model.strip() else []) + list(mode_defaults) + configured:
        if candidate and candidate not in ordered:
            ordered.append(candidate)
    return ordered


def _resolve_thinking_level(thinking_budget: int | None) -> types.ThinkingLevel:
    if thinking_budget is None or thinking_budget >= 2048:
        return types.ThinkingLevel.HIGH
    if thinking_budget >= 512:
        return types.ThinkingLevel.MEDIUM
    if thinking_budget > 0:
        return types.ThinkingLevel.LOW
    return types.ThinkingLevel.MINIMAL


def _build_live_connect_config(
    mode: str,
    *,
    model_id: str,
    target_language: str | None,
    thinking_budget: int | None,
) -> types.LiveConnectConfig:
    kwargs: dict[str, Any] = {
        "response_modalities": ["AUDIO"],
        "output_audio_transcription": types.AudioTranscriptionConfig(),
    }
    if mode == "translate":
        lang = (target_language or "English").strip() or "English"
        kwargs["system_instruction"] = (
            f"You are a real-time translator. Translate the user's input accurately into {lang}, "
            "preserving meaning and tone. Return only the translated output."
        )
    elif mode == "extended_thinking":
        kwargs["system_instruction"] = (
            "Think step by step carefully before answering, then give a clear, accurate, concise final response."
        )
    else:
        kwargs["system_instruction"] = "Provide a direct, accurate, and helpful response."

    if "thinking" in model_id.lower():
        kwargs["thinking_config"] = types.ThinkingConfig(
            include_thoughts=True,
            thinking_level=_resolve_thinking_level(thinking_budget),
        )
    return types.LiveConnectConfig(**kwargs)


async def _collect_live_turn(session: Any) -> tuple[str, str | None]:
    """Read messages from a Live API AsyncSession until the turn completes."""
    text_chunks: list[str] = []
    transcription_chunks: list[str] = []
    thought_chunks: list[str] = []
    async for msg in session.receive():
        server_content = getattr(msg, "server_content", None)
        if server_content is None:
            continue
        model_turn = getattr(server_content, "model_turn", None)
        for part in getattr(model_turn, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if not part_text:
                continue
            if getattr(part, "thought", False):
                thought_chunks.append(part_text)
            else:
                text_chunks.append(part_text)
        output_tx = getattr(server_content, "output_transcription", None)
        if output_tx and getattr(output_tx, "text", None):
            transcription_chunks.append(output_tx.text)
        if getattr(server_content, "turn_complete", False) or getattr(server_content, "generation_complete", False):
            break
    final_text = ("".join(text_chunks) or "".join(transcription_chunks)).strip()
    thoughts = "".join(thought_chunks).strip() or None
    return final_text, thoughts


async def run_live_gemini_session(
    prompt: str,
    *,
    mode: str = "preview",
    target_language: str | None = None,
    model: str | None = None,
    thinking_budget: int | None = 2048,
    timeout_seconds: float = 20.0,
) -> tuple[str, str | None, str]:
    """Execute a real-time bidirectional Live API turn via genai client.aio.live.connect."""
    gemini_key = settings.GEMINI_API_KEY.strip()
    if not gemini_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key is required for Gemini Live sessions.",
        )
    clean_prompt = (prompt or "").strip()
    if not clean_prompt:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Prompt cannot be empty.")

    router = get_quota_router()
    client = genai.Client(api_key=gemini_key)
    candidates = _live_candidate_models(mode, model)

    last_exc: Exception | None = None
    for model_id in candidates:
        healthy, skip_reason = router.check_availability("gemini", model_id)
        if not healthy:
            logger.info("Skipping Gemini Live model %s (%s)", model_id, skip_reason)
            continue
        config = _build_live_connect_config(
            mode,
            model_id=model_id,
            target_language=target_language,
            thinking_budget=thinking_budget,
        )
        try:
            router.record_request("gemini", model_id)
            async with client.aio.live.connect(model=model_id, config=config) as session:
                await session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part.from_text(text=clean_prompt)]),
                    turn_complete=True,
                )
                text, thoughts = await asyncio.wait_for(_collect_live_turn(session), timeout=timeout_seconds)
            if text:
                return text, thoughts, model_id
        except Exception as exc:
            last_exc = exc
            should_retry, is_daily = _is_quota_or_transient_error(exc)
            if (
                should_retry
                or isinstance(exc, asyncio.TimeoutError)
                or "not found" in str(exc).lower()
                or "unsupported" in str(exc).lower()
                or "not supported" in str(exc).lower()
            ):
                if should_retry:
                    router.mark_rate_limited("gemini", model_id, is_daily=is_daily, reason=type(exc).__name__)
                logger.warning("Gemini Live model %s failed (%s); trying next Live candidate.", model_id, type(exc).__name__)
                continue
            break

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Gemini Live session failed ({type(last_exc).__name__ if last_exc else 'no live response'}).",
    )
