"""Centralized Response Language Resolver enforcing English-by-default with lingua-py + explicit overrides."""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from lingua import Language, LanguageDetector, LanguageDetectorBuilder
from pydantic import BaseModel, Field

from app.llm.registry import available_models, get_chat_model
from app.services.intent_service import _invoke_structured_with_fallback

logger = logging.getLogger(__name__)


def _build_canonical_languages() -> dict[str, str]:
    mapping: dict[str, str] = {
        "hinglish": "Hinglish",
        "mandarin": "Chinese",
        "español": "Spanish",
        "espanol": "Spanish",
        "français": "French",
        "francais": "French",
        "deutsch": "German",
        "português": "Portuguese",
        "italiano": "Italian",
    }
    for lang in Language.all():
        title = lang.name.title()
        mapping[lang.name.lower()] = title
        if lang.iso_code_639_1 is not None:
            mapping[lang.iso_code_639_1.name.lower()] = title
    return mapping


_CANONICAL_LANGUAGES: dict[str, str] = _build_canonical_languages()

_LANG_PATTERN = "|".join(sorted((re.escape(k) for k in _CANONICAL_LANGUAGES if len(k) > 2), key=len, reverse=True))

# Quoted text removal so discussing an instruction ('Answer in French') does not trigger an override
_QUOTED_TEXT_RE = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1")

# Bilingual / multi-language directive: "in both English and Hindi", "in English and Hindi"
_BILINGUAL_DIRECTIVE_RE = re.compile(
    rf"\b(?:in|into)\s+(?:both\s+)?({_LANG_PATTERN})\s+(?:and|&|\+)\s+({_LANG_PATTERN})\b",
    re.IGNORECASE,
)

# Explicit single-language directive in English
_SINGLE_DIRECTIVE_RE = re.compile(
    rf"(?:"
    rf"(?:answer|reply|respond|explain|write|translate|output|give(?:\s+(?:me|the))?\s+(?:answer|response)|speak|summarize)"
    rf"(?:\s+(?:this|it|everything|the\s+following(?:\s+\w+)?))?"
    rf"\s+(?:in|into)\s+({_LANG_PATTERN})\b"
    rf"|\b(?:in|into)\s+({_LANG_PATTERN})\s*(?:language|only)?\s*(?:please|plz)?[\.\!\?]*$"
    rf"|\b({_LANG_PATTERN})\s+(?:mein|me)\s+(?:answer|reply|jawaab|jawab|uttar|batao|btao|samjhao|likho)\b"
    rf")",
    re.IGNORECASE,
)

# Multilingual native-script / foreign-phrase output directives
_NATIVE_DIRECTIVES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:हिंदी|हिन्दी)\s*में(?:\s*(?:जवाब|उत्तर|बताइए|बताओ|समझाओ|लिखो))?"), "Hindi"),
    (re.compile(r"(?:अंग्रेजी|इंग्लिश)\s*में(?:\s*(?:जवाब|उत्तर|बताइए|बताओ|समझाओ|लिखो))?"), "English"),
    (re.compile(r"日本語で(?:回答|説明|答え)"), "Japanese"),
    (re.compile(r"英語で(?:回答|説明|答え)?"), "English"),
    (re.compile(r"(?:réponds|reponds|explique|écris|ecris|en)\s+français\b", re.IGNORECASE), "French"),
    (re.compile(r"(?:responde|explica|escribe|en)\s+español\b", re.IGNORECASE), "Spanish"),
    (re.compile(r"(?:antworte|erkläre|erklaere|auf)\s+deutsch\b", re.IGNORECASE), "German"),
    (re.compile(r"(?:بالعربية|باللغة العربية)"), "Arabic"),
    (re.compile(r"(?:用中文|用汉语|用英文)"), "Chinese"),
]

# Indirect output-language phrasing (e.g., "Reply in the language spoken in Tokyo")
_INDIRECT_OVERRIDE_TRIGGER_RE = re.compile(
    r"\b(?:answer|reply|respond|explain|write|describe|summarize|tell|speak|output|use)\b"
    r"[^.!?\n]{0,50}?\b(?:in|using)\s+(?:the\s+)?(?:(?:official|national|native|local|primary|main)\s+)?language\s+"
    r"(?:(?:spoken|used)\s+in|of)\b",
    re.IGNORECASE,
)

_HINGLISH_MARKERS = {
    "kya", "hai", "hain", "hota", "hoti", "hote", "kaise", "kar", "karo", "kare", "karein",
    "karte", "karta", "karti", "sakta", "sakti", "hoon", "hu", "batao", "btao", "samjhao",
    "mujhe", "apne", "apni", "mein", "ke", "ki", "ka", "ko", "se", "aur", "fayde", "faede",
    "kyon", "kyu", "nahi", "nhi", "chahiye", "ye", "yeh", "woh",
}


class _IndirectLanguageOverrideSchema(BaseModel):
    has_override: bool = Field(default=False)
    target_language: str | None = Field(default=None)


@lru_cache(maxsize=1)
def get_lingua_detector() -> LanguageDetector:
    """Build and cache lingua-language-detector across all supported languages."""
    return LanguageDetectorBuilder.from_all_languages().build()


@dataclass(frozen=True)
class ResponseLanguageResolution:
    """Resolved language policy for a request prior to cache lookup or LLM invocation."""

    input_language: str
    explicit_language_override: bool
    requested_response_language: str | None
    effective_response_language: str
    language_policy: str  # 'default' | 'explicit_override' | 'conversation_preference'
    clean_query_for_cache: str


def _detect_non_latin_script_language(text: str) -> tuple[str, int, int] | None:
    """Count unmistakable non-Latin script letters so mixed technical English terms don't skew scoring."""
    script_counts: dict[str, int] = {}
    total_alpha = 0
    for ch in text:
        if not ch.isalpha():
            continue
        total_alpha += 1
        uname = unicodedata.name(ch, "")
        if "DEVANAGARI" in uname:
            script_counts["Hindi"] = script_counts.get("Hindi", 0) + 1
        elif "HIRAGANA" in uname or "KATAKANA" in uname:
            script_counts["Japanese"] = script_counts.get("Japanese", 0) + 1
        elif "HANGUL" in uname:
            script_counts["Korean"] = script_counts.get("Korean", 0) + 1
        elif "ARABIC" in uname:
            script_counts["Arabic"] = script_counts.get("Arabic", 0) + 1
        elif "CJK UNIFIED" in uname:
            script_counts["Chinese"] = script_counts.get("Chinese", 0) + 1
        elif "BENGALI" in uname:
            script_counts["Bengali"] = script_counts.get("Bengali", 0) + 1
        elif "TAMIL" in uname:
            script_counts["Tamil"] = script_counts.get("Tamil", 0) + 1
        elif "TELUGU" in uname:
            script_counts["Telugu"] = script_counts.get("Telugu", 0) + 1
    if not script_counts:
        return None
    if "Japanese" in script_counts:
        return "Japanese", script_counts["Japanese"] + script_counts.get("Chinese", 0), total_alpha
    lang, count = max(script_counts.items(), key=lambda kv: kv[1])
    return lang, count, total_alpha


def detect_input_language(query: str) -> str:
    """Detect input query language using lingua-py with Unicode script and Romanized Hinglish guards."""
    raw = unicodedata.normalize("NFC", query or "").strip()
    if not raw:
        return "English"

    lowered = raw.lower()
    tokens = set(re.findall(r"[^\W\d_]+", lowered))
    if raw.isascii() and (tokens & _HINGLISH_MARKERS):
        return "Hinglish"

    detected = get_lingua_detector().detect_language_of(raw)
    lingua_lang = (
        _CANONICAL_LANGUAGES.get(detected.name.lower(), detected.name.title())
        if detected is not None
        else "English"
    )

    script_info = _detect_non_latin_script_language(raw)
    if script_info is not None:
        script_lang, script_count, total_alpha = script_info
        ratio = script_count / max(1, total_alpha)
        if ratio >= 0.22 or lingua_lang != "English":
            return script_lang

    return lingua_lang


def _canonicalize_lang(name: str) -> str:
    return _CANONICAL_LANGUAGES.get(name.strip().lower(), name.strip().title())


def extract_explicit_override(query: str) -> str | None:
    """Extract an intentional response-language directive while ignoring quoted text and language mentions."""
    unquoted = _QUOTED_TEXT_RE.sub(" ", unicodedata.normalize("NFC", query or ""))

    # 1. Bilingual / combination directive (e.g. "in both English and Hindi")
    bi_matches = list(_BILINGUAL_DIRECTIVE_RE.finditer(unquoted))
    if bi_matches:
        m = bi_matches[-1]
        l1 = _canonicalize_lang(m.group(1))
        l2 = _canonicalize_lang(m.group(2))
        if l1 != l2:
            return f"{l1} + {l2}"
        return l1

    # 2. English explicit directives
    single_matches = list(_SINGLE_DIRECTIVE_RE.finditer(unquoted))
    if single_matches:
        m = single_matches[-1]
        lang_token = m.group(1) or m.group(2) or m.group(3)
        if lang_token:
            return _canonicalize_lang(lang_token)

    # 3. Native-script / non-English explicit directives
    for pattern, lang_name in _NATIVE_DIRECTIVES:
        if pattern.search(unquoted):
            if lang_name == "Chinese" and "英文" in unquoted:
                return "English"
            return lang_name

    return None


def resolve_response_language(
    query: str,
    *,
    conversation_language_preference: str | None = None,
) -> ResponseLanguageResolution:
    """Determine effective response language with strict precedence:
    1. Explicit response-language override in current request.
    2. Active conversation-level explicit language preference (if any).
    3. Default: 'English'.
    """
    input_lang = detect_input_language(query)
    override = extract_explicit_override(query)

    if override:
        return ResponseLanguageResolution(
            input_language=input_lang,
            explicit_language_override=True,
            requested_response_language=override,
            effective_response_language=override,
            language_policy="explicit_override",
            clean_query_for_cache=query.strip(),
        )

    if conversation_language_preference:
        return ResponseLanguageResolution(
            input_language=input_lang,
            explicit_language_override=True,
            requested_response_language=conversation_language_preference,
            effective_response_language=conversation_language_preference,
            language_policy="conversation_preference",
            clean_query_for_cache=query.strip(),
        )

    return ResponseLanguageResolution(
        input_language=input_lang,
        explicit_language_override=False,
        requested_response_language=None,
        effective_response_language="English",
        language_policy="default",
        clean_query_for_cache=query.strip(),
    )


_INDIRECT_OVERRIDE_PARSER = PydanticOutputParser(pydantic_object=_IndirectLanguageOverrideSchema)


async def resolve_response_language_async(
    query: str,
    *,
    conversation_language_preference: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> ResponseLanguageResolution:
    """Async resolver that adds structured LLM classification for indirect directives (no city map)."""
    base = resolve_response_language(
        query,
        conversation_language_preference=conversation_language_preference,
    )
    if base.language_policy == "explicit_override":
        return base

    unquoted = _QUOTED_TEXT_RE.sub(" ", unicodedata.normalize("NFC", query or ""))
    if not _INDIRECT_OVERRIDE_TRIGGER_RE.search(unquoted):
        return base

    try:
        opts = available_models()
        target_prov = provider or (opts[0].provider if opts else "groq")
        target_mod = model or (opts[0].id if opts else "")
        llm = get_chat_model(target_prov, target_mod, streaming=False)
        parsed = await _invoke_structured_with_fallback(
            llm,
            [
                SystemMessage(
                    content=(
                        "Determine if the user query explicitly commands the assistant to reply in a specific "
                        "target language indirectly (for example via a city or country). Return target_language "
                        'in English title case (e.g. "Japanese", "French") ONLY as JSON matching '
                        '{"has_override": bool, "target_language": str | null}.'
                    )
                ),
                HumanMessage(content=query),
            ],
            _IndirectLanguageOverrideSchema,
            _INDIRECT_OVERRIDE_PARSER,
            5.0,
        )
        if parsed and parsed.has_override and parsed.target_language:
            lang_name = _canonicalize_lang(parsed.target_language)
            return ResponseLanguageResolution(
                input_language=base.input_language,
                explicit_language_override=True,
                requested_response_language=lang_name,
                effective_response_language=lang_name,
                language_policy="explicit_override",
                clean_query_for_cache=query.strip(),
            )
    except Exception as exc:
        logger.debug("Indirect language override LLM check skipped: %s", exc)

    return base
