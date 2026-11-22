"""Authenticated conversation management and streaming chat API."""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot.graph import chat_graph
from app.config.settings import get_settings
from app.database.session import async_session_factory, get_db_session
from app.dependencies.auth import get_current_user
from app.guardrails.rate_limiter import RedisRateLimiter
from app.guardrails.schemas import Decision
from app.guardrails.service import get_guardrails_service
from app.llm.registry import available_models, provider_options, validate_provider_model
from app.ai.gemini_media_service import (
    run_live_gemini_session,
    synthesize_speech_with_fallback,
    transcribe_audio_with_gemini,
)
from app.models.chat import ChatConversation, ChatMessage
from app.models.user import User
from app.services.cache_engine import SemanticCacheEngine
from app.schemas.chatbot import (
    AudioTranscribeResponse,
    ChatCompletionRequest,
    ChatMessageResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    LiveConnectRequest,
    LiveConnectResponse,
    ModelResponse,
    ProviderResponse,
    TextToSpeechRequest,
    TextToSpeechResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chatbot"])
settings = get_settings()


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _provider_error(exc: Exception) -> tuple[int, str]:
    error_name = type(exc).__name__.lower()
    error_text = str(exc).lower()
    upstream_status = _provider_status_code(exc)
    if (
        upstream_status == 503
        or "serviceunavailable" in error_name
        or "503" in error_text
        or "high demand" in error_text
        or "unavailable" in error_text
        or "overload" in error_text
    ):
        return 503, "This model is currently experiencing high demand, so use different models."
    if upstream_status == 429 or "ratelimit" in error_name or "toomanyrequests" in error_name or "resourceexhausted" in error_name or "429" in error_text:
        return 429, "The selected provider is rate-limited. Retry later or choose another configured model."
    if upstream_status in (408, 504) or "timeout" in error_name or "deadlineexceeded" in error_name:
        return 504, "We're sorry — the selected model took longer than 3 minutes to respond, so the request was stopped automatically. Please try again or switch to a faster model."
    if "authentication" in error_name or "permission" in error_name:
        return 502, "The selected provider rejected its backend credentials or model access."
    if "notfound" in error_name:
        return 502, "The selected provider does not currently expose this model to the configured account."
    return 502, "The selected model could not complete this response."


def _provider_status_code(exc: BaseException) -> int | None:
    """Extract an HTTP status from common SDK/HTTP-client exception shapes."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for candidate in (
            getattr(current, "status_code", None),
            getattr(getattr(current, "response", None), "status_code", None),
        ):
            try:
                status_code = int(candidate)
            except (TypeError, ValueError):
                continue
            if 100 <= status_code <= 599:
                return status_code
        current = current.__cause__ or current.__context__
    return None


async def _record_failed_cache_lookup(
    final_state: dict[str, object],
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    query: str,
    provider: str,
    model: str,
    total_latency_ms: int,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    """Keep a failed request visible as an error without misclassifying it as a normal miss."""
    if final_state.get("is_cached") is True:
        return

    lookup = final_state.get("cache_lookup")
    if error_type or error_message:
        cache_status = "error"
    else:
        cache_status = "bypass" if final_state.get("skip_cache") else "miss"
    try:
        async with async_session_factory() as telemetry_db:
            await SemanticCacheEngine(telemetry_db, user_id).record_telemetry(
                query=query,
                cache_status=cache_status,
                provider=provider,
                model=model,
                input_tokens=0,
                output_tokens=0,
                lookup_latency_ms=getattr(lookup, "lookup_latency_ms", 0),
                total_latency_ms=total_latency_ms,
                conversation_id=conversation_id,
                similarity_score=getattr(lookup, "similarity_score", None),
                detected_language=final_state.get("input_language"),
                requested_language=final_state.get("effective_response_language"),
                related_candidates=getattr(lookup, "related_candidates", None),
                current_query=query,
                rejected_candidates_snapshot=getattr(lookup, "rejected_candidates_snapshot", None),
                validation_explanation=getattr(lookup, "validation_explanation", None),
                error_type=error_type,
                error_message=error_message,
            )
    except Exception as telemetry_exc:
        logger.warning("Failed to persist failed chat cache telemetry (type=%s)", type(telemetry_exc).__name__)


async def _owned_conversation(db: AsyncSession, user: User, conversation_id: uuid.UUID) -> ChatConversation:
    conversation = await db.scalar(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.owner_id == user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


def _valid_model_pair(provider: str, model: str) -> bool:
    return any(option.provider == provider and option.id == model for option in available_models())


@router.get("/providers", response_model=list[ProviderResponse])
async def get_providers(_: User = Depends(get_current_user)) -> list[ProviderResponse]:
    return [ProviderResponse.model_validate(item) for item in provider_options()]


@router.get("/models", response_model=list[ModelResponse])
async def get_models(_: User = Depends(get_current_user)) -> list[ModelResponse]:
    return [ModelResponse(id=item.id, name=item.name, provider=item.provider, tier=item.tier) for item in available_models()]


@router.post("/tts/synthesize", response_model=TextToSpeechResponse)
async def synthesize_chat_audio(
    payload: TextToSpeechRequest,
    _: User = Depends(get_current_user),
) -> TextToSpeechResponse:
    audio_base64, audio_mime_type = await synthesize_speech_with_fallback(payload.text)
    return TextToSpeechResponse(audio_base64=audio_base64, audio_mime_type=audio_mime_type)


@router.post("/audio/transcribe", response_model=AudioTranscribeResponse)
async def transcribe_chat_audio(
    file: UploadFile = File(...),
    target_language: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> AudioTranscribeResponse:
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Audio file exceeds 20 MB limit.")
    transcript, used_model = await transcribe_audio_with_gemini(
        raw,
        mime_type=file.content_type or "audio/wav",
        target_language=target_language,
    )
    verdict = await get_guardrails_service().check_input(
        transcript,
        user_id=user.id,
        db=db,
    )
    await db.commit()
    if verdict.effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
        safe_transcript = verdict.user_safe_message or "I can't process that request."
    elif verdict.effective_decision == Decision.REDACT and verdict.redacted_content is not None:
        safe_transcript = verdict.redacted_content
    else:
        safe_transcript = verdict.redacted_content or transcript
    return AudioTranscribeResponse(transcript=safe_transcript, model=used_model, target_language=target_language)


@router.post("/live/session", response_model=LiveConnectResponse)
async def gemini_live_session(
    payload: LiveConnectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> LiveConnectResponse:
    verdict = await get_guardrails_service().check_input(
        payload.prompt,
        user_id=user.id,
        db=db,
    )
    await db.commit()
    if verdict.effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
        return LiveConnectResponse(
            text=verdict.user_safe_message or "I cannot fulfill this request due to safety guidelines.",
            thoughts=None,
            model=payload.model,
            mode=payload.mode,
            target_language=payload.target_language,
        )
    effective_prompt = verdict.redacted_content or payload.prompt
    text, thoughts, used_model = await run_live_gemini_session(
        effective_prompt,
        mode=payload.mode,
        target_language=payload.target_language,
        model=payload.model,
        thinking_budget=payload.thinking_budget,
    )
    return LiveConnectResponse(
        text=text,
        thoughts=thoughts,
        model=used_model,
        mode=payload.mode,
        target_language=payload.target_language,
    )


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ConversationResponse:
    if not _valid_model_pair(payload.provider, payload.model):
        raise HTTPException(status_code=422, detail="The selected model is not available for this provider.")
    conversation = ChatConversation(
        owner_id=user.id,
        title=payload.title.strip(),
        selected_provider=payload.provider,
        selected_model=payload.model,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate({**conversation.__dict__, "messages": []})


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
) -> list[ConversationResponse]:
    rows = await db.scalars(
        select(ChatConversation)
        .where(ChatConversation.owner_id == user.id)
        .order_by(ChatConversation.updated_at.desc())
        .limit(100)
    )
    return [ConversationResponse.model_validate({**row.__dict__, "messages": []}) for row in rows.all()]


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ConversationResponse:
    conversation = await _owned_conversation(db, user, conversation_id)
    result = await db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation.id,
            ChatMessage.owner_id == user.id,
            ChatMessage.status == "completed",
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    messages = [ChatMessageResponse.model_validate(row) for row in result.all()]
    return ConversationResponse.model_validate({**conversation.__dict__, "messages": messages})


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ConversationResponse:
    conversation = await _owned_conversation(db, user, conversation_id)
    changes = payload.model_dump(exclude_unset=True)
    provider = changes.get("provider", conversation.selected_provider)
    model = changes.get("model", conversation.selected_model)
    if not _valid_model_pair(provider, model):
        raise HTTPException(status_code=422, detail="The selected model is not available for this provider.")
    if "title" in changes:
        conversation.title = changes["title"].strip()
    conversation.selected_provider = provider
    conversation.selected_model = model
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate({**conversation.__dict__, "messages": []})


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    conversation = await _owned_conversation(db, user, conversation_id)
    await db.delete(conversation)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/chat/completions")
async def chat_completion(
    payload: ChatCompletionRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    validate_provider_model(payload.provider, payload.model)
    client_ip = request.client.host if (request is not None and request.client is not None) else "unknown"
    rate_limiter = RedisRateLimiter()
    await rate_limiter.check_and_acquire_stream(user.id, client_ip)
    existing_conversation: ChatConversation | None = None
    if payload.conversation_id:
        existing_conversation = await _owned_conversation(db, user, payload.conversation_id)

    verdict = await get_guardrails_service().check_input(
        payload.message,
        user_id=user.id,
        db=db,
    )

    if verdict.effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
        reason_cat = verdict.reason_category or "policy_violation"
        safe_message = verdict.user_safe_message or (
            f"I can't help with that request. If you think this is a mistake, reference ID: {verdict.request_id}."
        )
        blocked_conv_id = existing_conversation.id if existing_conversation is not None else None
        blocked_latency_ms = max(1, int(round(verdict.latency_ms)))
        blocked_query = verdict.redacted_content or payload.message
        await SemanticCacheEngine(db, user.id).record_telemetry(
            query=blocked_query[:250],
            cache_status="blocked",
            provider=payload.provider,
            model=payload.model,
            input_tokens=0,
            output_tokens=0,
            lookup_latency_ms=0,
            total_latency_ms=blocked_latency_ms,
            conversation_id=blocked_conv_id,
            response_preview=safe_message,
            current_query=blocked_query,
        )
        await db.close()

        async def blocked_event_stream() -> AsyncIterator[str]:
            try:
                conv_val = str(blocked_conv_id) if blocked_conv_id is not None else None
                yield _sse(
                    "response.start",
                    {
                        "conversation_id": conv_val,
                        "provider": payload.provider,
                        "model": payload.model,
                    },
                )
                yield _sse("content.delta", {"content": safe_message})
                yield _sse(
                    "response.complete",
                    {
                        "conversation_id": conv_val,
                        "message_id": "",
                        "provider": payload.provider,
                        "model": payload.model,
                        "switched_from": None,
                        "switch_reason": None,
                        "latency_ms": blocked_latency_ms,
                        "is_cached": False,
                        "effective_response_language": "English",
                        "input_language": "English",
                        "language_policy": "default",
                        "blocked": True,
                        "reason_category": reason_cat,
                    },
                )
            finally:
                await rate_limiter.release_stream(user.id)

        return StreamingResponse(
            blocked_event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    effective_message = verdict.redacted_content or payload.message

    if existing_conversation is not None:
        conversation = existing_conversation
    else:
        conversation = ChatConversation(
            owner_id=user.id,
            title=effective_message.replace("\n", " ")[:72],
            selected_provider=payload.provider,
            selected_model=payload.model,
        )
        db.add(conversation)
        await db.flush()

    conversation.selected_provider = payload.provider
    conversation.selected_model = payload.model
    if conversation.title == "New chat":
        conversation.title = effective_message.replace("\n", " ")[:72]
    user_message = ChatMessage(
        owner_id=user.id,
        conversation_id=conversation.id,
        role="user",
        content=effective_message,
        provider=payload.provider,
        model_id=payload.model,
        status="completed",
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)
    conversation_id = conversation.id
    user_message_id = user_message.id
    user_id = user.id
    # Release request-scoped session before returning StreamingResponse so the pool connection is not held/leaked.
    await db.close()

    async def event_stream() -> AsyncIterator[str]:
        yield _sse("response.start", {"conversation_id": str(conversation_id), "provider": payload.provider, "model": payload.model})
        final_state: dict[str, object] = {}
        stream_started_at = time.perf_counter()
        try:
            async with async_session_factory() as stream_db:
                try:
                    async for mode, item in chat_graph.astream(
                        {
                            "db": stream_db,
                            "user_id": user_id,
                            "conversation_id": conversation_id,
                            "user_message_id": user_message_id,
                            "message": effective_message,
                            "provider": payload.provider,
                            "model": payload.model,
                        },
                        stream_mode=["custom", "values"],
                    ):
                        if mode == "custom" and isinstance(item, dict) and item.get("event") == "content.delta":
                            yield _sse("content.delta", {"content": item.get("data", "")})
                        elif mode == "custom" and isinstance(item, dict) and item.get("event") == "status.update":
                            yield _sse("status.update", item.get("data", {}))
                        elif mode == "custom" and isinstance(item, dict) and item.get("event") == "cache.telemetry":
                            yield _sse("cache.telemetry", item.get("data", {}))
                        elif mode == "values" and isinstance(item, dict):
                            final_state = item
                except BaseException:
                    await stream_db.rollback()
                    raise
                finally:
                    await stream_db.close()
            usage = final_state.get("usage", {})
            if isinstance(usage, dict):
                yield _sse("usage", usage)
            yield _sse(
                "response.complete",
                {
                    "conversation_id": str(conversation_id),
                    "message_id": str(final_state.get("assistant_message_id", "")),
                    "provider": final_state.get("active_provider", payload.provider),
                    "model": final_state.get("active_model", payload.model),
                    "switched_from": final_state.get("switched_from"),
                    "switch_reason": final_state.get("switch_reason"),
                    "latency_ms": final_state.get("latency_ms"),
                    "is_cached": final_state.get("is_cached", False),
                    "effective_response_language": final_state.get("effective_response_language", "English"),
                    "input_language": final_state.get("input_language", "English"),
                    "language_policy": final_state.get("language_policy", "default"),
                },
            )
        except HTTPException as exc:
            yield _sse("response.error", {"status": exc.status_code, "detail": exc.detail})
        except Exception as exc:
            error_status, detail = _provider_error(exc)
            upstream_status = _provider_status_code(exc)
            logger.warning(
                "Chat generation failed (type=%s provider=%s model=%s upstream_status=%s response_status=%s)",
                type(exc).__name__,
                payload.provider,
                payload.model,
                upstream_status,
                error_status,
            )
            await _record_failed_cache_lookup(
                final_state,
                user_id=user_id,
                conversation_id=conversation_id,
                query=effective_message,
                provider=payload.provider,
                model=payload.model,
                total_latency_ms=max(0, int((time.perf_counter() - stream_started_at) * 1000)),
                error_type=type(exc).__name__,
                error_message=detail,
            )
            yield _sse("response.error", {"status": error_status, "detail": detail})
        finally:
            await rate_limiter.release_stream(user_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
