"""Provider configuration, connectivity tests, and voice-clone contracts."""

from __future__ import annotations

import json
import os
import time
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Response
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
    secret_value: str = ""
    model: str = ""
    path: str = "/models"
    mode: Literal["models", "chat"] = "models"


def _test_secret(api_key_env: str, secret_value: str) -> tuple[str, str]:
    """Return the key to use and where it came from."""

    if secret_value.strip():
        return secret_value.strip(), "request"
    environment = os.environ.get(api_key_env, "") if api_key_env else ""
    if environment:
        return environment, "environment"
    stored = get_secret(api_key_env)
    if stored:
        return stored, "stored"
    return "", "missing"


def _provider_message(body: str) -> str:
    """Extract the human part of a provider error while keeping the raw text."""

    text = body.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except ValueError:
        return text[:1000]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail")
            if message:
                return str(message)[:1000]
        if isinstance(error, str) and error:
            return error[:1000]
        for key in ("message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value[:1000]
    return text[:1000]


def _provider_failure(
    status: int,
    api_key: str,
    api_key_env: str,
    endpoint: str,
    provider_message: str,
) -> tuple[str, str, str]:
    """Map a provider HTTP failure to a code, message, and hint."""

    if status in {401, 403}:
        if not api_key:
            return (
                "secret_missing",
                f"No API key was found for {api_key_env or 'this provider'}.",
                "Paste the key in Secret value and test again, or save the provider first.",
            )
        return (
            "auth_failed",
            f"The provider rejected the API key (HTTP {status}).",
            "Check that the key is valid, not expired, and belongs to this provider.",
        )
    if status == 404:
        return (
            "endpoint_not_found",
            "The endpoint was not found (HTTP 404).",
            f"Check Base URL and path. Tried {endpoint}.",
        )
    if status == 429:
        return (
            "rate_limited",
            "The provider rate-limited the request or the account has no credit (HTTP 429).",
            "Check the provider quota and billing, then try again later.",
        )
    if status >= 500:
        return (
            "provider_error",
            f"The provider returned a server error (HTTP {status}).",
            "Try again later or check the provider status page.",
        )
    return (
        "http_error",
        f"The provider returned HTTP {status}.",
        provider_message[:300] or "Check the provider settings and the request.",
    )


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
                        "message": (
                            f"Provider {request.provider_id!r} was not found. "
                            "Save it first or choose another provider."
                        ),
                    },
                )
            base_url = base_url or str(provider.get("base_url") or "")
            api_key_env = api_key_env or str(provider.get("api_key_env") or "")
            model = model or str(provider.get("model") or "")
        try:
            api_key_env = validate_secret_name(api_key_env)
        except InvalidConfigError as exc:
            raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
        base = base_url.strip().rstrip("/")
        if not base:
            raise HTTPException(
                status_code=422,
                detail={
                    "ok": False,
                    "code": "invalid_url",
                    "message": (
                        "Enter a Base URL, for example "
                        "https://api.deepseek.com/v1."
                    ),
                },
            )
        if not (base.startswith("http://") or base.startswith("https://")):
            raise HTTPException(
                status_code=422,
                detail={
                    "ok": False,
                    "code": "invalid_url",
                    "message": (
                        "Base URL must start with http:// or https:// "
                        f"(got {base_url!r})."
                    ),
                },
            )
        path = request.path or "/models"
        if not path.startswith("/"):
            path = f"/{path}"
        if request.mode == "chat":
            endpoint = (
                base
                if base.endswith("/chat/completions")
                else f"{base}/chat/completions"
            )
        else:
            endpoint = f"{base}{path}"
        if request.mode == "chat" and not model:
            raise HTTPException(
                status_code=422,
                detail={
                    "ok": False,
                    "code": "model_required",
                    "message": (
                        "Chat test requires a model. Enter the model name, "
                        "for example deepseek-chat."
                    ),
                },
            )
        api_key, secret_source = _test_secret(api_key_env, request.secret_value)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        started = time.perf_counter()
        try:
            if request.mode == "chat":
                response = httpx.post(
                    endpoint,
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
                    endpoint,
                    headers=headers,
                    timeout=10.0,
                    follow_redirects=True,
                )
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "status_code": None,
                "code": "network_error",
                "message": f"Could not reach the provider: {exc}",
                "hint": "Check the base URL, the network, and any proxy.",
                "provider_message": str(exc),
                "secret_present": bool(api_key),
                "secret_source": secret_source,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "mode": request.mode,
                "endpoint": endpoint,
            }
        raw = response.text[:1000]
        provider_message = _provider_message(raw)
        ok = 200 <= response.status_code < 400
        if ok:
            code = "ok"
            if request.mode == "chat":
                message = ""
                try:
                    payload = response.json()
                    message = str(
                        payload.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )[:200]
                except (ValueError, AttributeError, IndexError, TypeError):
                    message = ""
                message = message or "Connection OK"
            else:
                message = "Connection OK. The models endpoint answered."
            if secret_source == "request":
                hint = "This key is used only for the test. Save the provider to store it."
            elif secret_source == "missing":
                hint = "Connected without an API key."
            else:
                hint = ""
        else:
            code, message, hint = _provider_failure(
                response.status_code,
                api_key,
                api_key_env,
                endpoint,
                provider_message,
            )
        return {
            "ok": ok,
            "status_code": response.status_code,
            "code": code,
            "message": message,
            "hint": hint,
            "provider_message": provider_message,
            "secret_present": bool(api_key),
            "secret_source": secret_source,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "mode": request.mode,
            "endpoint": endpoint,
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
    ) -> Response:
        audio = voice_clone.synthesize(request)
        return Response(content=audio, media_type="audio/mpeg")

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
        }
        if capability not in known:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "unknown_capability", "message": capability},
            )
        return {"ok": True, "capability": capability, "chain": resolve_chain(capability)}
