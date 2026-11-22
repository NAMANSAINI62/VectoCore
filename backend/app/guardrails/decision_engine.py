"""Deterministic policy and decision engine for guardrail layers."""

from app.guardrails.schemas import (
    Decision,
    GuardrailVerdict,
    LayerMode,
    LayerResult,
    ScoreBand,
)

# Categories from content-safety models that represent privacy/PII rather than safety threats.
# Policy rule: Content-safety "privacy/PII" categories map to REDACT or ALLOW, never BLOCK/FALLBACK.
_PRIVACY_PII_CATEGORIES = frozenset({
    "pii",
    "privacy",
    "pii/privacy",
    "personal_data",
    "personal information",
    "sensitive_data",
    "private_information",
    "s15",
})

# Categories representing self-harm or suicide.
# Policy rule: Self-harm gets a supportive crisis-helpline message, not a cold block.
_SELF_HARM_CATEGORIES = frozenset({
    "self_harm",
    "self-harm",
    "suicide",
    "suicide_or_self_harm",
    "suicide and self harm",
    "self harm",
    "s11",
})

_DECISION_SEVERITY: dict[Decision, int] = {
    Decision.ALLOW: 0,
    Decision.REDACT: 1,
    Decision.REQUIRE_REVIEW: 2,
    Decision.FALLBACK: 3,
    Decision.BLOCK: 4,
}


def build_generic_safe_message(request_id: str) -> str:
    """Return a safe, generic refusal message without exposing internal IDs or detector details."""
    _ = request_id
    return "I cannot fulfill this request due to safety guidelines."


def build_supportive_self_harm_message(request_id: str) -> str:
    """Return a supportive crisis-resource message when self-harm is detected."""
    _ = request_id
    return (
        "If you or someone you know is going through a difficult time or having thoughts of self-harm, "
        "please know that you are not alone and caring support is available right now. "
        "In India, you can call Tele-MANAS at 14416 or 1800-891-4416 (free, 24/7). "
        "In the US and Canada, call or text 988. In the UK, call 111. "
        "If you are in immediate danger, please contact your local emergency services."
    )


def _normalize_category(cat: str) -> str:
    return (cat or "").strip().lower().replace("_", " ")


def is_privacy_only_categories(categories: list[str]) -> bool:
    """Return True if categories are non-empty and every category is a privacy/PII category."""
    if not categories:
        return False
    for raw in categories:
        norm_space = _normalize_category(raw)
        norm_under = norm_space.replace(" ", "_")
        if norm_space not in _PRIVACY_PII_CATEGORIES and norm_under not in _PRIVACY_PII_CATEGORIES:
            return False
    return True


def has_self_harm_category(categories: list[str]) -> bool:
    """Return True if any category corresponds to self-harm or suicide."""
    for raw in categories:
        norm_space = _normalize_category(raw)
        norm_under = norm_space.replace(" ", "_")
        if (
            norm_space in _SELF_HARM_CATEGORIES
            or norm_under in _SELF_HARM_CATEGORIES
            or "self harm" in norm_space
            or "suicide" in norm_space
        ):
            return True
    return False


class DecisionEngine:
    """Evaluates detector LayerResults into a single GuardrailVerdict according to layer mode and policy."""

    @staticmethod
    def map_content_safety_categories(
        categories: list[str],
        has_redacted_text: bool = False,
    ) -> tuple[Decision, ScoreBand, bool]:
        """Map content-safety categories to (Decision, ScoreBand, is_self_harm).

        - Empty categories -> (ALLOW, LOW, False)
        - Privacy/PII-only categories -> (REDACT if has_redacted_text else ALLOW, MEDIUM, False); never BLOCK.
        - Self-harm categories -> (FALLBACK, CRITICAL, True)
        - Other unsafe categories -> (FALLBACK, HIGH, False)
        """
        if not categories:
            return Decision.ALLOW, ScoreBand.LOW, False
        if has_self_harm_category(categories):
            return Decision.FALLBACK, ScoreBand.CRITICAL, True
        if is_privacy_only_categories(categories):
            return (Decision.REDACT if has_redacted_text else Decision.ALLOW), ScoreBand.MEDIUM, False
        return Decision.FALLBACK, ScoreBand.HIGH, False

    def evaluate(
        self,
        *,
        request_id: str,
        layer: str,
        mode: LayerMode,
        results: list[LayerResult],
        policy_version: str,
        guardrails_enabled: bool = True,
    ) -> GuardrailVerdict:
        """Combine detector outcomes for a layer and apply `off | shadow | enforce` mode rules.

        Policy rules enforced:
        1. If `guardrails_enabled` is False or `mode == LayerMode.OFF`, both `raw_decision`
           and `effective_decision` are `Decision.ALLOW`.
        2. If all detectors in a non-empty `results` list are `degraded` (both unavailable),
           `raw_decision` becomes `Decision.FALLBACK` (`degraded=True`).
        3. If one detector is `degraded` and another is healthy, the healthy detector's
           outcome is used and `degraded=True` is flagged.
        4. Content-safety privacy/PII-only categories never produce `BLOCK` or `FALLBACK`;
           they map to `REDACT` (if `redacted_text` is present) or `ALLOW`.
        5. For `layer == "input"`, if either input detector fires (`BLOCK` or `FALLBACK`),
           `raw_decision` is `Decision.FALLBACK`.
        6. In `shadow` mode, `raw_decision` records the true policy decision while
           `effective_decision` is always `Decision.ALLOW` (and `user_safe_message` is None).
        7. In `enforce` mode, `effective_decision == raw_decision`, and self-harm triggers
           a supportive helpline message instead of a cold refusal.
        """
        total_latency_ms = round(sum(r.latency_ms for r in results), 2)

        if not guardrails_enabled or mode == LayerMode.OFF:
            return GuardrailVerdict(
                request_id=request_id,
                layer=layer,
                mode=mode,
                effective_decision=Decision.ALLOW,
                raw_decision=Decision.ALLOW,
                policy_version=policy_version,
                latency_ms=total_latency_ms,
                user_safe_message=None,
                redacted_content=None,
                layer_results=results,
                degraded=False,
            )

        if not results:
            return GuardrailVerdict(
                request_id=request_id,
                layer=layer,
                mode=mode,
                effective_decision=Decision.ALLOW,
                raw_decision=Decision.ALLOW,
                policy_version=policy_version,
                latency_ms=0.0,
                user_safe_message=None,
                redacted_content=None,
                layer_results=[],
                degraded=False,
            )

        any_degraded = any(r.degraded for r in results)
        all_degraded = all(r.degraded for r in results)
        self_harm_detected = any(has_self_harm_category(r.categories) for r in results)

        normalized_results: list[LayerResult] = []
        redacted_content: str | None = None

        for res in results:
            if res.redacted_text is not None:
                redacted_content = res.redacted_text

            if res.degraded:
                normalized_results.append(res)
                continue

            decision = res.decision
            # Enforce policy rule: privacy/PII-only categories from content-safety never BLOCK/FALLBACK
            # (Presidio's explicit BLOCK for IN_AADHAAR / IN_PHONE is preserved.)
            if (
                res.detector != "presidio_pii"
                and decision in (Decision.BLOCK, Decision.FALLBACK)
                and is_privacy_only_categories(res.categories)
            ):
                decision = Decision.REDACT if res.redacted_text is not None else Decision.ALLOW

            # Enforce policy rule: either input detector firing maps to FALLBACK
            if layer == "input" and decision == Decision.BLOCK:
                decision = Decision.FALLBACK

            if decision != res.decision:
                normalized_results.append(res.model_copy(update={"decision": decision}))
            else:
                normalized_results.append(res)

        if all_degraded:
            raw_decision = Decision.FALLBACK
            reason_category: str | None = "guardrails_degraded"
        else:
            healthy = [r for r in normalized_results if not r.degraded]
            highest = max(healthy, key=lambda r: _DECISION_SEVERITY[r.decision])
            raw_decision = highest.decision
            if layer == "input" and raw_decision == Decision.BLOCK:
                raw_decision = Decision.FALLBACK
            if raw_decision == Decision.ALLOW:
                reason_category = None
            elif self_harm_detected:
                reason_category = "self_harm"
            elif highest.categories:
                reason_category = _normalize_category(highest.categories[0]).replace(" ", "_")
            else:
                reason_category = highest.detector

        if mode == LayerMode.SHADOW:
            effective_decision = Decision.ALLOW
            user_safe_message = None
        else:
            effective_decision = raw_decision
            if effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
                if self_harm_detected:
                    user_safe_message = build_supportive_self_harm_message(request_id)
                else:
                    user_safe_message = build_generic_safe_message(request_id)
            else:
                user_safe_message = None

        return GuardrailVerdict(
            request_id=request_id,
            layer=layer,
            mode=mode,
            effective_decision=effective_decision,
            raw_decision=raw_decision,
            policy_version=policy_version,
            latency_ms=total_latency_ms,
            user_safe_message=user_safe_message,
            redacted_content=redacted_content if effective_decision == Decision.REDACT else None,
            reason_category=reason_category if effective_decision != Decision.ALLOW else None,
            layer_results=normalized_results,
            degraded=any_degraded,
        )
