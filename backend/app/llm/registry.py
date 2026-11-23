"""Provider registry and model validation for supported LangChain chat backends."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
import threading
import time

from cachetools import TTLCache
from fastapi import HTTPException
from langchain_cohere import ChatCohere
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_openai import ChatOpenAI

from app.config.settings import get_settings

settings = get_settings()


@dataclass(frozen=True)
class ModelOption:
    id: str
    name: str
    provider: str
    tier: str | None = None


import re

MAX_SAFE_RPM = 10

# Exclusive, zero-duplication UI category mapping for Gemini models (from AI Studio free-tier dashboard)
_MODEL_UI_TIERS: dict[str, str] = {
    "gemma-4-31b-it": "deep_research",
    "gemini-3.8-flash": "complex",
    "gemini-3-flash-preview": "complex",
    "gemini-3.5-flash-lite": "balanced",
    "gemini-3.1-flash-lite": "fast",
    "gemini-3.1-flash-lite-preview": "fast",
    "gemini-flash-lite-latest": "fast",
}

_MODEL_LABELS: dict[str, str] = {
    "openai/gpt-oss-20b": "GPT-OSS 20B",
    "openai/gpt-oss-120b": "GPT-OSS 120B",
    "baidu/ernie-5.5-flash-preview:free": "ERNIE 5.5 Flash",
    "gemma-4-31b-it": "Gemma 4 31B",
    "gemini-3.8-flash": "3.8 Flash",
    "gemini-3-flash-preview": "3 Flash",
    "gemini-3.5-flash-lite": "3.5 Flash-Lite",
    "gemini-flash-lite-latest": "Flash-Lite",
    "gemini-3.1-flash-lite": "3.1 Flash-Lite",
    "gemini-3.1-flash-lite-preview": "3.1 Lite Prev",
    "gemini-3.8-flash-tts": "3.8 Flash TTS",
    "gemini-3.1-flash-tts-preview": "3.1 TTS Prev",
    "gemini-3.8-flash-lite-tts": "3.8 Lite TTS",
    "gemini-2.5-flash-preview-tts": "2.5 Flash TTS",
    "gemini-3.5-transcribe": "3.5 Transcribe",
    "gemini-3.8-live-extended-thinking": "3.8 Live Think",
    "gemini-3.8-live": "3.8 Live",
    "gemini-3.1-flash-live-preview": "3.1 Live Prev",
    "command-a-03-2025": "Command A",
    "nvidia/nemotron-3.5-super-vl-120b-a12b": "Nemotron 120B",
    "nvidia/nemotron-3.5-bolt-e4b": "Nemotron Bolt",
}


def get_model_label(model_id: str) -> str:
    return _MODEL_LABELS.get(model_id, model_id)


# Per-model short-term memory context token budgets (falls back to settings.MEMORY_MAX_CONTEXT_TOKENS)
_MODEL_MEMORY_TOKEN_BUDGETS: dict[str, int] = {
    "gemini-3.8-flash": 8000,
    "gemini-3-flash-preview": 8000,
    "gemini-3.5-flash-lite": 6000,
    "gemini-3.1-flash-lite": 4000,
    "gemini-3.1-flash-lite-preview": 4000,
    "gemini-flash-lite-latest": 4000,
    "gemma-4-31b-it": 4000,
    "openai/gpt-oss-120b": 4000,
    "openai/gpt-oss-20b": 3000,
    "command-a-03-2025": 6000,
    "nvidia/nemotron-3.5-super-vl-120b-a12b": 6000,
    "nvidia/nemotron-3.5-bolt-e4b": 3000,
}


def get_model_memory_token_budget(model_id: str) -> int:
    """Return the per-model short-term memory token budget, bounded by MEMORY_MAX_CONTEXT_TOKENS."""
    per_model = _MODEL_MEMORY_TOKEN_BUDGETS.get(model_id, settings.MEMORY_MAX_CONTEXT_TOKENS)
    return min(per_model, settings.MEMORY_MAX_CONTEXT_TOKENS)


# Free-tier safety budgets per model (soft pre-switch threshold triggers before hitting 429)
@dataclass(frozen=True)
class ModelQuotaPolicy:
    rpm_limit: int
    rpd_limit: int
    rpm_soft_ratio: float = 0.85
    rpd_soft_ratio: float = 0.96

    @property
    def rpm_soft_cap(self) -> int:
        # Global safety ceiling: never push more than 10 RPM per model, and switch early on 3-5 RPM models
        return min(MAX_SAFE_RPM, max(1, int(self.rpm_limit * self.rpm_soft_ratio)))

    @property
    def rpd_soft_cap(self) -> int:
        if self.rpd_limit <= 1:
            return 1
        return max(1, min(self.rpd_limit - 1, int(self.rpd_limit * self.rpd_soft_ratio)))


_MODEL_QUOTA_POLICIES: dict[str, ModelQuotaPolicy] = {
    "gemma-4-31b-it": ModelQuotaPolicy(rpm_limit=30, rpd_limit=14400),
    "gemini-3.8-flash": ModelQuotaPolicy(rpm_limit=5, rpd_limit=20),
    "gemini-3-flash-preview": ModelQuotaPolicy(rpm_limit=5, rpd_limit=20),
    "gemini-3.5-flash-lite": ModelQuotaPolicy(rpm_limit=15, rpd_limit=500),
    "gemini-flash-lite-latest": ModelQuotaPolicy(rpm_limit=10, rpd_limit=20),
    "gemini-3.1-flash-lite": ModelQuotaPolicy(rpm_limit=15, rpd_limit=500),
    "gemini-3.1-flash-lite-preview": ModelQuotaPolicy(rpm_limit=15, rpd_limit=500),
    "gemini-3.8-flash-tts": ModelQuotaPolicy(rpm_limit=3, rpd_limit=10),
    "gemini-3.1-flash-tts-preview": ModelQuotaPolicy(rpm_limit=3, rpd_limit=10),
    "gemini-3.8-flash-lite-tts": ModelQuotaPolicy(rpm_limit=3, rpd_limit=10),
    "gemini-2.5-flash-preview-tts": ModelQuotaPolicy(rpm_limit=3, rpd_limit=10),
    "gemini-3.5-transcribe": ModelQuotaPolicy(rpm_limit=3, rpd_limit=25),
    "gemini-3.8-live-extended-thinking": ModelQuotaPolicy(rpm_limit=10, rpd_limit=500),
    "gemini-3.8-live": ModelQuotaPolicy(rpm_limit=10, rpd_limit=500),
    "gemini-3.1-flash-live-preview": ModelQuotaPolicy(rpm_limit=10, rpd_limit=500),
    "command-a-03-2025": ModelQuotaPolicy(rpm_limit=5, rpd_limit=1000),
    "baidu/ernie-5.5-flash-preview:free": ModelQuotaPolicy(rpm_limit=20, rpd_limit=50),
}

_DEEP_RESEARCH_INTENT_RE = re.compile(
    r"\b("
    r"deep research|research report|literature review|thorough investigation|"
    r"exhaustive analysis|multi[- ]source analysis|comprehensive research|state of the art"
    r")\b",
    re.IGNORECASE,
)

_COMPLEX_INTENT_RE = re.compile(
    r"\b("
    r"architecture|system design|tradeoff|trade-off|root cause|"
    r"step[- ]by[- ]step|comprehensive|prove|mathematical|algorithm|optimi[sz]e|"
    r"refactor|debug|security audit|distributed|concurrency|benchmark|"
    r"end[- ]to[- ]end|production grade|analyze in detail|compare in detail|"
    r"explain in depth|design a|build a full|migrate"
    r")\b",
    re.IGNORECASE,
)

_BALANCED_INTENT_RE = re.compile(
    r"\b("
    r"explain|compare|difference|versus|vs\b|how does|why does|implement|"
    r"code|python|sql|typescript|javascript|react|fastapi|postgres|redis|"
    r"write a|example|pros and cons|summari[sz]e|tutorial|guide"
    r")\b",
    re.IGNORECASE,
)

# Runtime performance & quota failover ranking per intent tier (with automatic 503/429 failover)
_GEMINI_TIER_RANKINGS: dict[str, tuple[str, ...]] = {
    "deep_research": (
        "gemma-4-31b-it",
        "gemini-3.8-flash",
        "gemini-3-flash-preview",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-lite-latest",
    ),
    "complex": (
        "gemini-3.8-flash",
        "gemini-3-flash-preview",
        "gemma-4-31b-it",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-lite-latest",
    ),
    "balanced": (
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-lite-latest",
        "gemini-3-flash-preview",
        "gemma-4-31b-it",
        "gemini-3.8-flash",
    ),
    "fast": (
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview",
        "gemma-4-31b-it",
        "gemini-3.8-flash",
    ),
}


def classify_query_intent_and_complexity(message: str, history_len: int = 0) -> tuple[str, str]:
    """Classify prompt into ('deep_research'|'complex'|'balanced'|'fast', intent_label) for dynamic routing."""
    clean = (message or "").strip()
    words = len(clean.split())
    lines = clean.count("\n") + (1 if clean else 0)

    if _DEEP_RESEARCH_INTENT_RE.search(clean):
        return "deep_research", "deep research & multi-step synthesis"
    if _COMPLEX_INTENT_RE.search(clean) or len(clean) >= 220 or words >= 38 or lines >= 5 or (history_len >= 8 and words >= 18):
        return "complex", "complex reasoning & deep analysis"
    if _BALANCED_INTENT_RE.search(clean) or len(clean) >= 75 or words >= 14:
        return "balanced", "balanced code & structured explanation"
    return "fast", "fast lookup & concise response"


class ModelQuotaRouter:
    """Tracks per-model rolling RPM/RPD budgets and cooldowns for proactive & reactive failover."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._minute_hits: dict[str, deque[float]] = {}
        self._daily_hits: dict[str, deque[float]] = {}
        self._rpm_cooldown: TTLCache[str, str] = TTLCache(maxsize=128, ttl=65)
        self._rpd_cooldown: TTLCache[str, str] = TTLCache(maxsize=128, ttl=21600)

    @staticmethod
    def _key(provider: str, model: str) -> str:
        return f"{provider.strip().lower()}:{model.strip()}"

    def _prune(self, key: str, now: float) -> tuple[int, int]:
        m_q = self._minute_hits.setdefault(key, deque())
        while m_q and (now - m_q[0]) >= 60.0:
            m_q.popleft()
        d_q = self._daily_hits.setdefault(key, deque())
        while d_q and (now - d_q[0]) >= 86400.0:
            d_q.popleft()
        return len(m_q), len(d_q)

    def check_availability(self, provider: str, model: str, now: float | None = None) -> tuple[bool, str | None]:
        """Return (is_healthy, skip_reason) before making an upstream call."""
        ts = time.monotonic() if now is None else now
        key = self._key(provider, model)
        with self._lock:
            if key in self._rpd_cooldown:
                return False, self._rpd_cooldown[key]
            if key in self._rpm_cooldown:
                return False, self._rpm_cooldown[key]
            policy = _MODEL_QUOTA_POLICIES.get(model)
            if policy is not None:
                m_count, d_count = self._prune(key, ts)
                if d_count >= policy.rpd_soft_cap:
                    return False, f"proactive RPD guard ({d_count}/{policy.rpd_limit} daily)"
                if m_count >= policy.rpm_soft_cap:
                    return False, f"proactive RPM guard ({m_count}/{policy.rpm_limit}/min, cap {policy.rpm_soft_cap})"
        return True, None

    def record_request(self, provider: str, model: str, now: float | None = None) -> None:
        ts = time.monotonic() if now is None else now
        key = self._key(provider, model)
        with self._lock:
            self._prune(key, ts)
            self._minute_hits[key].append(ts)
            self._daily_hits[key].append(ts)

    def mark_rate_limited(self, provider: str, model: str, *, is_daily: bool = False, reason: str = "rate limit") -> None:
        key = self._key(provider, model)
        with self._lock:
            if is_daily:
                self._rpd_cooldown[key] = reason
            else:
                self._rpm_cooldown[key] = reason

    def reset(self) -> None:
        with self._lock:
            self._minute_hits.clear()
            self._daily_hits.clear()
            self._rpm_cooldown.clear()
            self._rpd_cooldown.clear()


_QUOTA_ROUTER = ModelQuotaRouter()


def get_quota_router() -> ModelQuotaRouter:
    return _QUOTA_ROUTER


def _ordered_tier_backups(all_opts: list[ModelOption], tier: str) -> list[ModelOption]:
    """Order Gemini concrete models by tier performance ranking, followed by configured fast backups."""
    by_pair = {(opt.provider, opt.id): opt for opt in all_opts}
    ordered: list[ModelOption] = []
    seen: set[tuple[str, str]] = set()

    def _add(opt: ModelOption | None) -> None:
        if opt is None:
            return
        sig = (opt.provider, opt.id)
        if sig not in seen:
            seen.add(sig)
            ordered.append(opt)

    for model_id in _GEMINI_TIER_RANKINGS.get(tier, _GEMINI_TIER_RANKINGS["balanced"]):
        _add(by_pair.get(("gemini", model_id)))

    for opt in all_opts:
        if opt.provider == "gemini":
            _add(opt)

    cross_backups = (
        ("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b")
        if tier in ("deep_research", "complex")
        else ("nvidia", "nvidia/nemotron-3.5-bolt-e4b"),
        ("nvidia", "nvidia/nemotron-3.5-bolt-e4b"),
        ("groq", "openai/gpt-oss-120b") if tier in ("deep_research", "complex") else ("groq", "openai/gpt-oss-20b"),
        ("groq", "openai/gpt-oss-20b"),
    )
    for backup_pair in cross_backups:
        _add(by_pair.get(backup_pair))
    for opt in all_opts:
        _add(opt)
    return ordered


def build_fallback_candidates(
    provider: str,
    model: str,
    *,
    message: str = "",
    history_len: int = 0,
) -> list[ModelOption]:
    """Build dynamic intent-aware candidate chain."""
    tier, _ = classify_query_intent_and_complexity(message, history_len=history_len)
    all_opts = [
        opt for opt in available_models()
        if _is_provider_configured(opt.provider)
    ]
    ordered: list[ModelOption] = []
    seen: set[tuple[str, str]] = set()

    def _add(opt: ModelOption) -> None:
        sig = (opt.provider, opt.id)
        if sig not in seen:
            seen.add(sig)
            ordered.append(opt)

    for opt in all_opts:
        if opt.provider == provider and opt.id == model:
            _add(opt)
    if provider != "gemini":
        for opt in all_opts:
            if opt.provider == provider and opt.id != model:
                _add(opt)

    for opt in _ordered_tier_backups(all_opts, tier):
        _add(opt)
    return ordered


def select_best_model_candidate(
    provider: str,
    model: str,
    *,
    message: str = "",
    history_len: int = 0,
) -> tuple[str, str, str | None]:
    """Select the healthiest concrete model dynamically using query intent/complexity + quota state."""
    candidates = build_fallback_candidates(provider, model, message=message, history_len=history_len)
    if not candidates:
        return provider, model, None
    first_reason: str | None = None
    for idx, opt in enumerate(candidates):
        healthy, reason = _QUOTA_ROUTER.check_availability(opt.provider, opt.id)
        if healthy:
            if idx == 0:
                return opt.provider, opt.id, None
            return opt.provider, opt.id, first_reason or "proactive quota guard"
        if idx == 0:
            first_reason = reason
    return candidates[0].provider, candidates[0].id, None


def _split_models(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_provider_configured(provider: str) -> bool:
    checks: dict[str, Callable[[], bool]] = {
        "groq": lambda: bool(settings.GROQ_API_KEY.strip()),
        "openrouter": lambda: bool(settings.OPENROUTER_API_KEY.strip()),
        "gemini": lambda: bool(settings.GEMINI_API_KEY.strip()),
        "cohere": lambda: bool(settings.COHERE_API_KEY.strip()),
        "nvidia": lambda: bool(settings.NVIDIA_API_KEY.strip()),
    }
    return checks.get(provider, lambda: False)()


def available_models() -> list[ModelOption]:
    provider_lists: tuple[tuple[str, str], ...] = (
        ("groq", settings.GROQ_AVAILABLE_MODELS),
        ("openrouter", settings.CHAT_AVAILABLE_MODELS),
        ("gemini", settings.GEMINI_AVAILABLE_MODELS),
        ("cohere", settings.COHERE_AVAILABLE_MODELS),
        ("nvidia", settings.NVIDIA_AVAILABLE_MODELS),
    )
    return [
        ModelOption(
            model_id,
            _MODEL_LABELS.get(model_id, model_id),
            provider,
            tier=_MODEL_UI_TIERS.get(model_id) if provider == "gemini" else None,
        )
        for provider, raw in provider_lists
        for model_id in _split_models(raw)
    ]


def provider_options() -> list[dict[str, object]]:
    providers: list[dict[str, object]] = []
    all_models = available_models()
    for provider in ("groq", "openrouter", "gemini", "cohere", "nvidia"):
        entries = [item for item in all_models if item.provider == provider]
        if entries:
            providers.append(
                {
                    "id": provider,
                    "configured": _is_provider_configured(provider),
                    "models": [item.id for item in entries],
                }
            )
    return providers


def validate_provider_model(provider: str, model: str) -> None:
    if not any(item.provider == provider and item.id == model for item in available_models()):
        raise HTTPException(status_code=422, detail="The selected model is not available for this provider.")
    if not _is_provider_configured(provider):
        raise HTTPException(status_code=503, detail=f"The {provider} provider is not configured on the backend.")


def get_chat_model(provider: str, model: str, *, streaming: bool = True) -> BaseChatModel:
    validate_provider_model(provider, model)
    builders: dict[str, Callable[[], BaseChatModel]] = {
        "groq": lambda: ChatGroq(
            model=model,
            api_key=settings.GROQ_API_KEY,
            timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
            max_retries=1,
            streaming=streaming,
        ),
        "openrouter": lambda: ChatOpenAI(
            model=model,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
            max_retries=1,
            streaming=streaming,
            extra_body={"provider": {"allow_fallbacks": False}},
        ),
        "gemini": lambda: ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.GEMINI_API_KEY,
            timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
            max_retries=1,
        ),
        "cohere": lambda: ChatCohere(
            model=model,
            cohere_api_key=settings.COHERE_API_KEY,
            timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
        ),
        "nvidia": lambda: (
            ChatNVIDIA(
                base_url="https://integrate.api.nvidia.com/v1",
                model=model,
                api_key=settings.NVIDIA_API_KEY,
                temperature=1,
                top_p=0.95,
                max_completion_tokens=16384,
                model_kwargs={"chat_template_kwargs": {"enable_thinking": True}},
            )
            if "super-vl" in model or "ultra" in model
            else ChatNVIDIA(
                base_url="https://integrate.api.nvidia.com/v1",
                model=model,
                api_key=settings.NVIDIA_API_KEY,
                temperature=0.5,
                top_p=0.95,
                max_completion_tokens=4096,
            )
        ),
    }
    return builders[provider]()
