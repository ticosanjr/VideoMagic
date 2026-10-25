"""Build an LLM client from configured providers with ordered fallback."""

from __future__ import annotations

import os
from typing import Any

from videoflow.adapters.llm import FallbackLlm, OpenAICompatibleLlm
from videoflow.application.circuit import CircuitBreakerLlm
from videoflow.application.providers import resolve_chain
from videoflow.application.secrets import get_secret
from videoflow.application.settings import load_settings
from videoflow.domain.errors import CapabilityUnavailableError


def build_llm() -> Any:
    settings = load_settings().llm
    providers = [item for item in resolve_chain("llm") if item.get("base_url")]
    base_url = os.environ.get("VIDEOWFLOW_LLM_BASE_URL", "")
    model = os.environ.get("VIDEOWFLOW_LLM_MODEL", "")
    if base_url and model:
        providers.insert(0, {"base_url": base_url, "model": model})
    clients = []
    for provider in providers:
        provider_url = str(provider.get("base_url") or "")
        provider_model = str(provider.get("model") or "")
        if not provider_url or not provider_model:
            continue
        clients.append(
            CircuitBreakerLlm(
                OpenAICompatibleLlm(
                base_url=provider_url,
                model=provider_model,
                api_key=get_secret(
                    str(provider.get("api_key_env") or "VIDEOWFLOW_LLM_API_KEY")
                ),
                timeout=float(settings.timeout_seconds or 90),
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                    retries=settings.retries,
                ),
                provider_url,
            )
        )
    if not clients:
        raise CapabilityUnavailableError(
            "llm", "Configure an LLM provider or VIDEOWFLOW_LLM_BASE_URL/MODEL."
        )
    if len(clients) == 1:
        return clients[0]
    return FallbackLlm(clients)
