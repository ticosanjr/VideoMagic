"""Provider configuration, connectivity tests, and voice-clone contracts."""

from __future__ import annotations

import time
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from videoflow.application import voice_clone
from videoflow.application.providers import (
    ProviderConfig,
    delete_provider,
    fallback_manifest,
    list_providers,
    resolve_chain,
    set_default,
    upsert_provider,
    validate_secret_name,
)
from videoflow.application.secrets import (
    delete_secret,
    get_secret,
    secret_backend,
    secret_present,
    set_secret,
)
from videoflow.domain.errors import InvalidConfigError


class ProviderTestRequest(BaseModel):
    provider_id: str = ""
    base_url: str = ""
    api_key_env: str = ""
    model: str = ""
    path: str = "/models"
    mode: Literal["models", "chat"] = "models"


def register_provider_routes(app: FastAPI) -> None:
    """Register provider, secret, resolution, and voice-clone routes."""

    @app.post("/api/v1/providers/test")
    def test_provider(request: ProviderTestRequest) -> dict[str, object]:
        base_url = request.base_url
        api_key_env = request.api_key_env
        model = request.model
        if request.provider_id:
            provider = next(
                (
                    item
                    for item in list_providers()
                    if str(item.get("id")) == request.provider_id
                ),
                None,
            )
            if provider is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "ok": False,
                        "code": "provider_not_found",
                        "message": request.provider_id,
                    },
                )
            base_url = base_url or str(provider.get("base_url") or "")
            api_key_env = api_key_env or str(provider.get("api_key_env") or "")
            model = model or str(provider.get("model") or "")
        try:
            api_key_env = validate_secret_name(api_key_env)
        except InvalidConfigError as exc:
            raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
        base = base_url.rstrip("/")
        if not (base.startswith("http://") or base.startswith("https://")):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "invalid_url", "message": base_url},
            )
        api_key = get_secret(api_key_env)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        started = time.perf_counter()
        try:
            if request.mode == "chat":
                if not model:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "ok": False,
                            "code": "model_required",
                            "message": "Chat test requires a model.",
                        },
                    )
                response = httpx.post(
                    f"{base}/chat/completions",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "temperature": 0,
                        "max_tokens": 8,
                        "stream": False,
                        "messages": [
                            {"role": "user", "content": "Reply with OK only."}
                        ],
                    },
                    timeout=20.0,
                    follow_redirects=True,
                )
            else:
                response = httpx.get(
                    f"{base}{request.path}",
                    headers=headers,
                    timeout=10.0,
                    follow_redirects=True,
                )
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "status_code": None,
                "message": str(exc),
                "secret_present": bool(api_key),
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "mode": request.mode,
            }
        body = response.text[:500]
        if request.mode == "chat" and response.status_code < 400:
            try:
                payload = response.json()
                body = str(
                    payload.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )[:200] or body
            except (ValueError, AttributeError, IndexError, TypeError):
                pass
        return {
            "ok": 200 <= response.status_code < 400,
            "status_code": response.status_code,
            "message": body,
            "secret_present": bool(api_key),
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "mode": request.mode,
        }

    def _providers_payload() -> list[dict[str, object]]:
        return [
            {**item, "secret_present": secret_present(str(item.get("api_key_env") or ""))}
            for item in list_providers()
        ]

    @app.get("/api/v1/providers")
    def providers_list() -> dict[str, object]:
        return {
            "ok": True,
            "providers": _providers_payload(),
            "fallbacks": fallback_manifest(),
            "secret_backend": secret_backend(),
        }

    @app.post("/api/v1/providers/{provider_id}/secret")
    def providers_secret(provider_id: str, request: dict[str, str]) -> dict[str, object]:
        value = str(request.get("value") or "")
        if not value:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "empty_secret", "message": provider_id},
            )
        provider = next(
            (item for item in list_providers() if item["id"] == provider_id), None
        )
        if provider is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "provider_not_found", "message": provider_id},
            )
        name = str(provider.get("api_key_env") or "")
        if not name:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "secret_name_missing", "message": provider_id},
            )
        set_secret(name, value)
        return {
            "ok": True,
            "secret_present": True,
            "secret_backend": secret_backend(),
        }

    @app.delete("/api/v1/providers/{provider_id}/secret")
    def providers_secret_delete(provider_id: str) -> dict[str, object]:
        provider = next(
            (item for item in list_providers() if item["id"] == provider_id), None
        )
        if provider is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "provider_not_found", "message": provider_id},
            )
        name = str(provider.get("api_key_env") or "")
        if name:
            delete_secret(name)
        return {"ok": True, "secret_present": False, "secret_backend": secret_backend()}

    @app.put("/api/v1/providers/{provider_id}")
    def providers_save(provider_id: str, request: ProviderConfig) -> dict[str, object]:
        if request.id != provider_id:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "provider_id_mismatch", "message": provider_id},
            )
        payload = upsert_provider(request)
        return {"ok": True, "provider": payload, "fallbacks": fallback_manifest()}

    @app.delete("/api/v1/providers/{provider_id}")
    def providers_delete(provider_id: str) -> dict[str, object]:
        delete_provider(provider_id)
        return {"ok": True, "fallbacks": fallback_manifest()}

    @app.post("/api/v1/providers/{provider_id}/default")
    def providers_default(provider_id: str) -> dict[str, object]:
        payload = set_default(provider_id)
        return {"ok": True, "provider": payload, "fallbacks": fallback_manifest()}

    @app.get("/api/v1/voice-clone/status")
    def voice_clone_status() -> dict[str, object]:
        return voice_clone.status()

    @app.get("/api/v1/voice-clone/profiles")
    def voice_clone_profiles() -> dict[str, object]:
        return {
            "ok": True,
            "profiles": [
                profile.model_dump(mode="json")
                for profile in voice_clone.list_profiles()
            ],
        }

    @app.post("/api/v1/voice-clone/profiles", status_code=201)
    def voice_clone_create(
        request: voice_clone.VoiceProfileRequest,
    ) -> dict[str, object]:
        profile = voice_clone.create_profile(request)
        return {"ok": True, "profile": profile.model_dump(mode="json")}

    @app.delete("/api/v1/voice-clone/profiles/{profile_id}")
    def voice_clone_delete(profile_id: str) -> dict[str, object]:
        voice_clone.delete_profile(profile_id)
        return {"ok": True, "deleted": profile_id}

    @app.post("/api/v1/voice-clone/synthesize")
    def voice_clone_synthesize(
        request: voice_clone.VoiceSynthesizeRequest,
    ) -> dict[str, object]:
        voice_clone.synthesize(request)
        return {"ok": True}

    @app.get("/api/v1/providers/resolve")
    def providers_resolve(capability: str = "llm") -> dict[str, object]:
        known = {
            "llm",
            "asr",
            "tts",
            "vision",
            "stock",
            "translation",
            "diarization",
            "publishing",
        }
        if capability not in known:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "unknown_capability", "message": capability},
            )
        return {"ok": True, "capability": capability, "chain": resolve_chain(capability)}
