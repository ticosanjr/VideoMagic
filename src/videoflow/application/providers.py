"""Persistent provider configuration and capability fallback chains."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.schema_migrations import migrate_providers
from videoflow.domain.errors import InvalidConfigError, StateNotReadyError
from videoflow.runtime import portable_home

PROVIDERS_FILE = "providers.json"
_SECRET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

Capability = Literal[
    "llm",
    "asr",
    "tts",
    "vision",
    "stock",
    "translation",
    "diarization",
    "publishing",
]


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=120)
    capability: Capability
    base_url: str = ""
    api_key_env: str = ""
    model: str = ""
    enabled: bool = True
    is_default: bool = False
    fallback: list[str] = Field(default_factory=list)
    notes: str = ""


def validate_secret_name(value: str) -> str:
    """Accept an environment variable name, never a literal API key."""

    value = value.strip()
    if value and not _SECRET_NAME.fullmatch(value):
        raise InvalidConfigError(
            "api_key_env must be an environment variable name such as "
            "DEEPSEEK_API_KEY, not the API key itself."
        )
    return value


def providers_path() -> Path:
    return portable_home() / PROVIDERS_FILE


def load_providers() -> list[ProviderConfig]:
    path = providers_path()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    payload = migrate_providers(payload) if isinstance(payload, dict) else payload
    items = payload.get("providers", []) if isinstance(payload, dict) else payload
    result: list[ProviderConfig] = []
    for item in items if isinstance(items, list) else []:
        try:
            result.append(ProviderConfig.model_validate(item))
        except ValueError:
            continue
    return result


def save_providers(providers: list[ProviderConfig]) -> list[ProviderConfig]:
    path = providers_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "providers": [item.model_dump(mode="json") for item in providers],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return providers


def provider_readiness(item: dict[str, object]) -> tuple[bool, list[str]]:
    """Return whether a provider is usable and which fields are missing."""

    if not bool(item.get("enabled", True)):
        return False, ["enabled"]
    capability = str(item.get("capability") or "")
    base_url = str(item.get("base_url") or "").strip()
    model = str(item.get("model") or "").strip()
    api_key_env = str(item.get("api_key_env") or "").strip()
    missing: list[str] = []
    if capability == "llm":
        if not base_url:
            missing.append("base_url")
        if not model:
            missing.append("model")
    elif capability in {"asr", "tts", "translation", "vision", "diarization"}:
        if not base_url:
            missing.append("base_url")
    elif capability in {"stock", "publishing"}:
        if not (api_key_env or base_url):
            missing.append("api_key_env")
    elif not (base_url or model or api_key_env):
        missing.append("base_url")
    return not missing, missing


def list_providers() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for provider in load_providers():
        item = provider.model_dump(mode="json")
        configured, missing = provider_readiness(item)
        item["configured"] = configured
        item["missing"] = missing
        items.append(item)
    return items


def upsert_provider(provider: ProviderConfig) -> dict[str, object]:
    provider = provider.model_copy(
        update={"api_key_env": validate_secret_name(provider.api_key_env)}
    )
    providers = [item for item in load_providers() if item.id != provider.id]

    def same_capability(item: ProviderConfig) -> bool:
        return item.capability == provider.capability

    if provider.is_default:
        providers = [
            item.model_copy(update={"is_default": False}) if same_capability(item) else item
            for item in providers
        ]
    if not provider.fallback:
        provider = provider.model_copy(
            update={"fallback": [item.id for item in providers if same_capability(item)][:3]}
        )
    providers.append(provider)
    # Remove self references and duplicates. A fallback may name a provider
    # that is configured later; resolution ignores ids that do not exist yet.
    providers = [
        item.model_copy(
            update={
                "fallback": [
                    entry for entry in dict.fromkeys(item.fallback) if entry != item.id
                ]
            }
        )
        for item in providers
    ]
    save_providers(providers)
    return provider.model_dump(mode="json")


def delete_provider(provider_id: str) -> None:
    providers = load_providers()
    remaining = [item for item in providers if item.id != provider_id]
    if len(remaining) == len(providers):
        raise StateNotReadyError(f"Unknown provider: {provider_id}")
    for item in remaining:
        if provider_id in item.fallback:
            item.fallback = [entry for entry in item.fallback if entry != provider_id]
    save_providers(remaining)


def set_default(provider_id: str) -> dict[str, object]:
    providers = load_providers()
    target = next((item for item in providers if item.id == provider_id), None)
    if target is None:
        raise StateNotReadyError(f"Unknown provider: {provider_id}")
    providers = [
        item.model_copy(
            update={"is_default": item.id == provider_id}
        )
        if item.capability == target.capability
        else item
        for item in providers
    ]
    save_providers(providers)
    saved = next(item for item in providers if item.id == provider_id)
    return saved.model_dump(mode="json")


def resolve_chain(capability: Capability) -> list[dict[str, object]]:
    """Return the enabled default provider followed by its fallbacks."""

    providers = {
        item.id: item
        for item in load_providers()
        if item.capability == capability and item.enabled
    }
    if not providers:
        return []
    default = next((item for item in providers.values() if item.is_default), None)
    if default is None:
        default = next(iter(providers.values()))
    chain: list[dict[str, object]] = []
    seen: set[str] = set()
    queue = [default.id]
    while queue:
        provider_id = queue.pop(0)
        if provider_id in seen:
            continue
        provider = providers.get(provider_id)
        if provider is None:
            continue
        seen.add(provider_id)
        chain.append(provider.model_dump(mode="json"))
        queue.extend(provider.fallback)
    return chain


def first_provider(capability: Capability) -> dict[str, object] | None:
    chain = resolve_chain(capability)
    if chain:
        return chain[0]
    from videoflow import plugin_api

    fallback = plugin_api.provider(capability)
    return fallback if fallback else None


def fallback_manifest() -> dict[str, list[dict[str, object]]]:
    capabilities: tuple[Capability, ...] = (
        "llm",
        "asr",
        "tts",
        "vision",
        "stock",
        "translation",
        "diarization",
        "publishing",
    )
    return {capability: resolve_chain(capability) for capability in capabilities}
