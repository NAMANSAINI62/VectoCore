"""Guardrails package exposing only the public GuardrailsService facade."""

from app.guardrails.service import GuardrailsService, get_guardrails_service

__all__ = ["GuardrailsService", "get_guardrails_service"]
