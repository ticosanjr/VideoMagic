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


def _intelligence_configured(settings: Any) -> bool:
    config = getattr(settings, "intelligence", None)
    if config is None:
        return False
    if config.enabled and (
        config.opencode_base_url.strip()
        or os.environ.get("VIDEOWFLOW_OPENCODE_BASE_URL", "").strip()
    ):
        return True
    if config.enabled and os.environ.get(config.deepseek_api_key_env, "").strip():
        return True
    try:
        from videoflow.application.providers import list_providers

        return any(
            str(item.get("capability")) == "llm"
            and str(item.get("kind")) in {"opencode_v2", "opencode_cli", "deepseek"}
            for item in list_providers()
        )
    except Exception:  # noqa: BLE001 - provider discovery is best effort
        return False


def build_llm() -> Any:
    settings_obj = load_settings()
    if _intelligence_configured(settings_obj):
        from videoflow.application.intelligence import build_llm_adapter

        adapter = build_llm_adapter(settings_obj)
        if adapter is not None:
            return adapter
    settings = settings_obj.llm
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
