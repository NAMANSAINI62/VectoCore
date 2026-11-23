"""Two-stage Stage 2 Intent Compatibility Validation using structured LLM output."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from app.llm.registry import available_models, get_chat_model

logger = logging.getLogger(__name__)


class IntentCompatibilitySchema(BaseModel):
    """Structured JSON output schema for LLM-based intent compatibility validation."""

    is_compatible: bool = Field(
        ...,
        description=(
            "True ONLY if both queries request substantially the same information "
            "with compatible scope, constraints, and explicit instructions."
        ),
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    intent_summary: str = Field(
        default="",
        description="Short summary of the primary intent comparison.",
    )
    reason: str = Field(
        ...,
        description="Concise explanation of why the candidate query was accepted or rejected.",
    )


@dataclass
class IntentValidationResult:
    """Outcome of Stage 2 intent compatibility validation."""

    is_valid: bool
    reason: str
    used_llm_judge: bool = False
    confidence: float = 0.0
    intent_summary: str = ""


_INTENT_VALIDATION_SYSTEM_PROMPT = """You are a strict semantic cache intent compatibility validator.
Your job is to decide whether a previously cached query can safely serve a cached response for the current user query.

Evaluate ALL of the following dimensions:
1. Primary Intent & Requested Information:
   - Accept ONLY if both queries ask for substantially the same core information.
   - Example EQUIVALENT intents:
     * "What are the advantages of Python?" and "What are the benefits of using Python?" or "Tell me the benefits of Python."
     * "What is Python?" and "Explain Python programming language." or "What is the meaning of Python?" (when neither adds extra scope constraints like "in detail" or "with code").
   - Example INCOMPATIBLE intents (MUST REJECT):
     * "What are the advantages of Python?" vs "Why is Python popular?"
     * "What are the advantages of Python?" vs "What is Python used for?"
     * "What are the advantages of Python?" vs "What is Python?"
     * "What are the advantages of Python?" vs "How does Python work?"
     * "What are the advantages of Python?" vs "What are the disadvantages of Python?"
     * "How to sort a list in Python?" vs "How to reverse a list in Python?"
2. Multilingual Equivalence:
   - Queries in different languages or scripts (e.g., English, Hindi, Hinglish such as "Python ke kya fayde hain?" or "Python की क्या खूबियाँ हैं?") ARE compatible with "What are the advantages of Python?" if they ask for the exact same underlying information and have no conflicting instructions.
3. Explicit Instructions & Constraints:
   - Check format, length, tone, audience, or constraint instructions (e.g., "in 3 bullet points" vs "detailed essay", "for a beginner" vs "for senior engineers", "with code example" vs "no code").
   - If explicit instructions or constraints conflict, set is_compatible = false.
4. Safety Rule:
   - Never accept a candidate merely because it shares topic keywords (e.g., both mention "Python").
   - When uncertain or ambiguous, set is_compatible = false."""


def extract_validation_entities(query: str) -> list[str]:
    """Extract lightweight metadata tokens for CacheEntry.critical_entities storage."""
    words = [w.strip(".,?!:;()[]{}\"'").lower() for w in (query or "").split()]
    seen: list[str] = []
    for w in words:
        if len(w) >= 4 and w not in seen:
            seen.append(w)
        if len(seen) >= 12:
            break
    return seen


_INTENT_OUTPUT_PARSER = PydanticOutputParser(pydantic_object=IntentCompatibilitySchema)


def _resolve_judge_model(provider: str, model: str) -> tuple[str, str]:
    """Select Groq 20B as the dedicated fast Stage-2 LLM judge when configured, else fallback to active registry."""
    all_opts = available_models()
    for opt in all_opts:
        if opt.provider.lower() == "groq" and "20b" in opt.id.lower():
            return opt.provider, opt.id

    prov = (provider or "groq").strip().lower()
    registered = [opt for opt in all_opts if opt.provider.lower() == prov] or all_opts
    if registered:
        for preferred_hint in ("20b", "mini", "flash-lite", "flash", "lite", "8b"):
            for opt in registered:
                if preferred_hint in opt.id.lower():
                    return opt.provider, opt.id
        return registered[0].provider, registered[0].id
    return prov, model


async def validate_candidate_intent(
    current_query: str,
    candidate_query: str,
    similarity_score: float,
    *,
    provider: str,
    model: str,
    use_llm_judge: bool = True,
    similarity_threshold: float = 0.72,
    timeout_seconds: float = 20.0,
) -> IntentValidationResult:
    """Validate whether candidate_query has the exact same underlying intent as current_query."""
    if not use_llm_judge:
        is_ok = similarity_score >= similarity_threshold
        return IntentValidationResult(
            is_valid=is_ok,
            reason=(
                f"Vector similarity ({similarity_score:.4f}) met threshold ({similarity_threshold:.2f}) with LLM judge disabled."
                if is_ok
                else f"Vector similarity ({similarity_score:.4f}) below threshold ({similarity_threshold:.2f}) with LLM judge disabled."
            ),
            used_llm_judge=False,
            confidence=max(0.0, min(1.0, float(similarity_score))),
            intent_summary="Vector threshold check",
        )

    judge_provider, judge_model = _resolve_judge_model(provider, model)
    user_prompt = (
        f"Current User Query: {current_query}\n"
        f"Cached Candidate Query: {candidate_query}\n"
        f"Vector Cosine Similarity: {similarity_score:.4f}\n\n"
        "Respond with JSON matching the IntentCompatibilitySchema: "
        '{"is_compatible": bool, "confidence": float, "intent_summary": str, "reason": str}.'
    )
    messages = [
        SystemMessage(content=_INTENT_VALIDATION_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    try:
        llm = get_chat_model(judge_provider, judge_model, streaming=False)
        try:
            llm = llm.bind(temperature=0)
        except Exception:
            pass

        parsed: IntentCompatibilitySchema | None = await _invoke_structured_with_fallback(
            llm,
            messages,
            IntentCompatibilitySchema,
            _INTENT_OUTPUT_PARSER,
            timeout_seconds,
        )

        if parsed is None:
            return IntentValidationResult(
                is_valid=False,
                reason="Intent validator returned empty or unparseable output; safely rejected.",
                used_llm_judge=True,
                confidence=0.0,
                intent_summary="Unparseable validation output",
            )

        return IntentValidationResult(
            is_valid=bool(parsed.is_compatible),
            reason=parsed.reason.strip() or (
                "Intent compatible." if parsed.is_compatible else "Intent incompatible."
            ),
            used_llm_judge=True,
            confidence=max(0.0, min(1.0, float(parsed.confidence))),
            intent_summary=parsed.intent_summary.strip(),
        )
    except asyncio.TimeoutError:
        logger.warning("Intent validation timed out after %.1fs; rejecting candidate.", timeout_seconds)
        return IntentValidationResult(
            is_valid=False,
            reason="Intent validation timed out; safely treated as incompatible.",
            used_llm_judge=True,
            confidence=0.0,
            intent_summary="Validation timeout",
        )
    except Exception as exc:
        logger.warning("Intent validation failed (%s); safely rejecting candidate.", exc)
        return IntentValidationResult(
            is_valid=False,
            reason=f"Intent validation unavailable ({type(exc).__name__}); safely treated as incompatible.",
            used_llm_judge=True,
            confidence=0.0,
            intent_summary="Validation error fallback",
        )


class _HinglishSearchPivotSchema(BaseModel):
    english_query: str = Field(
        ...,
        description="Concise semantic English equivalent of the Romanized Hinglish query.",
    )


_PIVOT_OUTPUT_PARSER = PydanticOutputParser(pydantic_object=_HinglishSearchPivotSchema)


def _supports_structured_output(llm: Any) -> bool:
    """Return False for provider models known to reject JSON-schema response_format calls."""
    bound = getattr(llm, "bound", llm)
    model_name = str(
        getattr(bound, "model_name", "")
        or getattr(bound, "model", "")
        or getattr(llm, "model_name", "")
        or getattr(llm, "model", "")
    ).lower()
    return "gpt-oss" not in model_name


async def _invoke_structured_with_fallback(
    llm: Any,
    messages: list[Any],
    schema_cls: type[BaseModel],
    parser: PydanticOutputParser,
    timeout_seconds: float,
) -> Any:
    """Invoke structured output, falling back cleanly to PydanticOutputParser on provider JSON replies."""
    if _supports_structured_output(llm):
        try:
            structured_llm = llm.with_structured_output(schema_cls)
            result = await asyncio.wait_for(
                structured_llm.ainvoke(messages),
                timeout=timeout_seconds,
            )
            if isinstance(result, schema_cls):
                return result
            if isinstance(result, dict):
                return schema_cls.model_validate(result)
        except Exception as structured_exc:
            logger.debug(
                "Structured output unavailable or failed (%s); falling back to parser invoke.",
                structured_exc,
            )
    raw_msg = await asyncio.wait_for(
        llm.ainvoke(messages),
        timeout=timeout_seconds,
    )
    content = str(getattr(raw_msg, "content", raw_msg) or "").strip()
    return parser.parse(content) if content else None


async def canonicalize_hinglish_query_for_search(
    query: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    timeout_seconds: float = 5.0,
) -> str | None:
    """Translate a Romanized Hinglish query to English solely for multilingual vector recall."""
    clean = (query or "").strip()
    if not clean:
        return None
    judge_provider, judge_model = _resolve_judge_model(provider, model)
    messages = [
        SystemMessage(
            content=(
                "Convert the user's Romanized Hinglish query into a clear, concise English "
                "question preserving exact entities, intent, and constraints. Return ONLY valid "
                'JSON matching {"english_query": "..."}.'
            )
        ),
        HumanMessage(content=clean),
    ]
    try:
        llm = get_chat_model(judge_provider, judge_model, streaming=False)
        try:
            llm = llm.bind(temperature=0)
        except Exception:
            pass
        parsed = await _invoke_structured_with_fallback(
            llm,
            messages,
            _HinglishSearchPivotSchema,
            _PIVOT_OUTPUT_PARSER,
            timeout_seconds,
        )
        if parsed is None:
            return None
        out = parsed.english_query.strip()
        return out or None
    except Exception as exc:
        logger.warning("Hinglish semantic pivot failed (%s).", exc)
        return None
