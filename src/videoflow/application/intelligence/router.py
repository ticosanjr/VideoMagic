"""Provider routing, fallback, validation, and telemetry."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from videoflow.application.intelligence import telemetry
from videoflow.application.intelligence.models import (
    IntelligenceError,
    IntelligenceResult,
    IntelligenceStatus,
    ProviderResult,
)
from videoflow.application.intelligence.providers.deepseek import DeepSeekProvider
from videoflow.application.intelligence.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from videoflow.application.intelligence.providers.opencode_cli import (
    OpenCodeCliProvider,
)
from videoflow.application.intelligence.providers.opencode_v2 import (
    OpenCodeV2Provider,
)
from videoflow.application.providers import list_providers
from videoflow.application.secrets import get_secret
from videoflow.application.settings import (
    AppSettings,
    IntelligenceSettings,
    TaskPolicy,
    load_settings,
)
from videoflow.domain.errors import LlmError

Validator = Callable[[dict[str, Any]], Any]


class Intelligence:
    """Resolve a task to a provider and validate the JSON result."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()
        self.config: IntelligenceSettings = self.settings.intelligence
        self._providers: dict[str, Any] | None = None

    def status(self) -> list[IntelligenceStatus]:
        return [provider.status() for provider in self._provider_list()]

    def available(self, task: str = "generic") -> bool:
        return any(status.ready for status in self.status())

    def models(self, provider_id: str) -> list[dict[str, Any]]:
        provider = self._provider(provider_id)
        if provider is None or not hasattr(provider, "list_models"):
            return []
        try:
            return provider.list_models()
        except Exception:  # noqa: BLE001 - model discovery is best effort
            return []

    def complete_json(
        self,
        task: str,
        prompt: str,
        schema_name: str,
        *,
        validator: Validator | None = None,
        provider_id: str = "",
        model: str = "",
        policy: TaskPolicy | None = None,
    ) -> IntelligenceResult:
        if not self.config.enabled:
            raise IntelligenceError("Intelligence is disabled in Settings.")
        selected = policy or self.config.tasks.get(task) or TaskPolicy()
        order = self._order(selected, provider_id)
        errors: list[str] = []
        for name in order:
            provider = self._provider(name)
            if provider is None:
                continue
            status = provider.status()
            if not status.ready:
                errors.append(f"{name}: {status.detail or 'not ready'}")
                continue
            started = time.perf_counter()
            try:
                result: ProviderResult = provider.complete_json(
                    prompt,
                    schema_name,
                    model=model or selected.model,
                    timeout=selected.timeout_seconds,
                    temperature=selected.temperature,
                    max_tokens=selected.max_tokens,
                )
                data = result.data
                if validator is not None:
                    data = _validated(validator, data)
                latency = result.latency_ms or round(
                    (time.perf_counter() - started) * 1000
                )
                telemetry.record(
                    task=task,
                    provider=result.provider,
                    model=result.model,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    latency_ms=latency,
                    cost_usd=result.cost_usd,
                    fallback="provider_fallback" if errors else "none",
                )
                return IntelligenceResult(
                    data=data,
                    task=task,
                    provider=result.provider,
                    model=result.model,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    cost_usd=result.cost_usd,
                    latency_ms=latency,
                    fallback="provider_fallback" if errors else "none",
                    errors=errors,
                )
            except Exception as exc:  # noqa: BLE001 - try the next provider
                message = f"{name}: {exc}"
                errors.append(message)
                telemetry.record(
                    task=task,
                    provider=name,
                    model=model or selected.model,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    error=str(exc),
                )
                continue
        detail = " | ".join(errors)
        raise IntelligenceError(
            "No intelligence provider could complete this task."
            + (f" {detail}" if detail else ""),
            errors=errors,
        )

    def generate_image(
        self,
        prompt: str,
        *,
        task: str = "image.broll",
        provider_id: str = "",
        model: str = "",
        width: int = 1024,
        height: int = 1024,
        count: int = 1,
    ) -> list[bytes]:
        selected = self.config.tasks.get(task) or TaskPolicy()
        order = self._order(selected, provider_id)
        errors: list[str] = []
        for name in order:
            provider = self._provider(name)
            if provider is None:
                continue
            status = provider.status()
            if not status.ready:
                errors.append(f"{name}: {status.detail or 'not ready'}")
                continue
            try:
                images = provider.generate_image(
                    prompt,
                    model=model or selected.model,
                    width=width,
                    height=height,
                    count=count,
                    timeout=selected.timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - try the next provider
                errors.append(f"{name}: {exc}")
                telemetry.record(
                    task=task,
                    provider=name,
                    model=model or selected.model,
                    error=str(exc),
                )
                continue
            telemetry.record(
                task=task,
                provider=name,
                model=model or selected.model,
                fallback="provider_fallback" if errors else "none",
            )
            return images
        detail = " | ".join(errors)
        raise IntelligenceError(
            "No intelligence provider could generate an image."
            + (f" {detail}" if detail else ""),
            errors=errors,
        )

    def _order(self, policy: TaskPolicy, provider_id: str) -> list[str]:
        if provider_id:
            return [provider_id]
        if policy.provider_order:
            return list(policy.provider_order)
        return list(self.config.provider_order)

    def _provider_list(self) -> list[Any]:
        if self._providers is None:
            self._providers = self._build_providers()
        return list(self._providers.values())

    def _provider(self, name: str) -> Any | None:
        if self._providers is None:
            self._providers = self._build_providers()
        if name in self._providers:
            return self._providers[name]
        for provider in self._providers.values():
            if getattr(provider, "kind", "") == name:
                return provider
        return None

    def _build_providers(self) -> dict[str, Any]:
        providers: dict[str, Any] = {}
        configured = list_providers()
        remote_allowed = bool(self.config.allow_network)
        for item in configured:
            capability = str(item.get("capability") or "")
            if capability != "llm":
                continue
            kind = str(item.get("kind") or "openai_compatible")
            provider = self._from_config(item, kind)
            if provider is not None:
                providers[str(item.get("id") or kind)] = provider
        if "opencode_v2" not in providers:
            base_url = self.config.opencode_base_url.strip()
            if base_url:
                providers["opencode_v2"] = OpenCodeV2Provider(
                    base_url=base_url,
                    model=self.config.opencode_model,
                    token=get_secret(self.config.opencode_token_env),
                    timeout=self.config.default_timeout_seconds,
                    retries=self.settings.llm.retries,
                )
        deepseek_key = get_secret(self.config.deepseek_api_key_env)
        if "deepseek" not in providers and remote_allowed and deepseek_key:
            providers["deepseek"] = DeepSeekProvider(
                base_url=self.config.deepseek_base_url,
                model=self.config.deepseek_model,
                api_key=deepseek_key,
                timeout=self.config.default_timeout_seconds,
                retries=self.settings.llm.retries,
            )
        if "opencode_cli" not in providers:
            binary = os.environ.get("VIDEOWFLOW_OPENCODE_BIN", "")
            if binary:
                providers["opencode_cli"] = OpenCodeCliProvider(
                    binary=binary,
                    model=self.config.opencode_model or "default",
                    timeout=self.config.default_timeout_seconds,
                )
        env_base = os.environ.get("VIDEOWFLOW_LLM_BASE_URL", "")
        env_model = os.environ.get("VIDEOWFLOW_LLM_MODEL", "")
        if env_base and env_model and "env_llm" not in providers:
            providers["env_llm"] = OpenAICompatibleProvider(
                provider_id="env_llm",
                base_url=env_base,
                model=env_model,
                api_key=get_secret("VIDEOWFLOW_LLM_API_KEY"),
                timeout=self.config.default_timeout_seconds,
                retries=self.settings.llm.retries,
            )
        return providers

    def _from_config(self, item: dict[str, Any], kind: str) -> Any | None:
        base_url = str(item.get("base_url") or "")
        model = str(item.get("model") or "")
        api_key_env = str(item.get("api_key_env") or "")
        if kind == "opencode_v2":
            return OpenCodeV2Provider(
                base_url=base_url or self.config.opencode_base_url,
                model=model or self.config.opencode_model,
                token=get_secret(api_key_env or self.config.opencode_token_env),
                timeout=self.config.default_timeout_seconds,
                retries=self.settings.llm.retries,
            )
        if kind == "opencode_cli":
            return OpenCodeCliProvider(
                binary=os.environ.get("VIDEOWFLOW_OPENCODE_BIN", "opencode"),
                model=model or "default",
                timeout=self.config.default_timeout_seconds,
            )
        if kind == "deepseek":
            return DeepSeekProvider(
                base_url=base_url or self.config.deepseek_base_url,
                model=model or self.config.deepseek_model,
                api_key=get_secret(api_key_env or self.config.deepseek_api_key_env),
                timeout=self.config.default_timeout_seconds,
                retries=self.settings.llm.retries,
            )
        if not base_url or not model:
            return None
        return OpenAICompatibleProvider(
            provider_id=str(item.get("id") or "openai_compatible"),
            base_url=base_url,
            model=model,
            api_key=get_secret(api_key_env),
            timeout=self.config.default_timeout_seconds,
            retries=self.settings.llm.retries,
        )


def _validated(validator: Validator, data: dict[str, Any]) -> dict[str, Any]:
    result = validator(data)
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return result if isinstance(result, dict) else data


class IntelligenceLlmAdapter:
    """Compatibility adapter for steps that still expect ``llm_client``."""

    def __init__(
        self,
        intelligence: Intelligence | None = None,
        *,
        provider_id: str = "",
    ) -> None:
        self.intelligence = intelligence or build_intelligence()
        self.provider_id = provider_id

    def complete_json(self, prompt: str, schema_name: str) -> dict[str, Any]:
        task = _task_for_schema(schema_name)
        try:
            return self.intelligence.complete_json(
                task,
                prompt,
                schema_name,
                provider_id=self.provider_id,
            ).data
        except IntelligenceError as exc:
            raise LlmError(str(exc)) from exc


def build_intelligence(settings: AppSettings | None = None) -> Intelligence:
    return Intelligence(settings)


def build_llm_adapter(settings: AppSettings | None = None) -> Any | None:
    intelligence = build_intelligence(settings)
    if not intelligence.available():
        return None
    return IntelligenceLlmAdapter(intelligence)


def _task_for_schema(schema_name: str) -> str:
    name = schema_name.casefold()
    if "short" in name or "curation" in name:
        return "curation.select"
    if "retake" in name:
        return "retakes.semantic"
    if "cleanup" in name:
        return "cleanup.context"
    if "factcheck" in name:
        return "factcheck.audit"
    if "translation" in name:
        return "translation.transcript"
    if "emoji" in name:
        return "caption.emoji"
    if "chapter" in name:
        return "chapters.title"
    if "narrative" in name or "style" in name:
        return "narrative.beats"
    if "timeline" in name or "zoom" in name:
        return "timeline.edit"
    return "generic"


