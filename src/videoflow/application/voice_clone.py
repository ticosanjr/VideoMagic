"""Voice-clone profiles and the optional ElevenLabs synthesis provider."""

from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.clock import now_iso as _now
from videoflow.application.secrets import get_secret, secret_present
from videoflow.domain.errors import (
    CapabilityUnavailableError,
    StateNotReadyError,
    TtsError,
)
from videoflow.runtime import portable_home

_LOCK = threading.RLock()
PROVIDERS = {"none", "elevenlabs"}


class VoiceCloneConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["none", "elevenlabs"] = "none"
    base_url: str = "https://api.elevenlabs.io/v1"
    model: str = "eleven_multilingual_v2"
    secret_name: str = "ELEVENLABS_API_KEY"
    consent_required: bool = True


class VoiceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    provider: str = "none"
    consent_ref: str = ""
    sample_count: int = Field(default=0, ge=0)
    sample_paths: list[str] = Field(default_factory=list)
    provider_voice_id: str = ""
    created_at: str
    metadata: dict[str, str] = Field(default_factory=dict)


class VoiceProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    consent_ref: str = Field(min_length=1, max_length=300)
    sample_count: int = Field(default=0, ge=0, le=100)
    sample_paths: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict[str, str] = Field(default_factory=dict)


class VoiceSynthesizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)


class VoiceCloneProvider(Protocol):
    def create_profile(self, request: VoiceProfileRequest) -> VoiceProfile: ...
    def synthesize(self, profile: VoiceProfile, text: str) -> bytes: ...
    def delete_profile(self, profile_id: str) -> None: ...




def store_dir() -> Path:
    directory = portable_home() / "voice_clone"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _profiles_path() -> Path:
    return store_dir() / "profiles.json"


def _read() -> list[VoiceProfile]:
    path = _profiles_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    profiles: list[VoiceProfile] = []
    for item in payload:
        if isinstance(item, dict):
            try:
                profiles.append(VoiceProfile.model_validate(item))
            except ValueError:
                continue
    return profiles


def _write(profiles: list[VoiceProfile]) -> None:
    path = _profiles_path()
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            [profile.model_dump(mode="json") for profile in profiles],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def config() -> VoiceCloneConfig:
    provider = os.environ.get("VIDEOWFLOW_VOICE_CLONE_PROVIDER", "none").strip().lower()
    if provider not in PROVIDERS:
        provider = "none"
    return VoiceCloneConfig(
        provider=provider,  # type: ignore[arg-type]
        base_url=os.environ.get(
            "VIDEOWFLOW_VOICE_CLONE_BASE_URL", "https://api.elevenlabs.io/v1"
        ).strip()
        or "https://api.elevenlabs.io/v1",
        model=os.environ.get(
            "VIDEOWFLOW_VOICE_CLONE_MODEL", "eleven_multilingual_v2"
        ).strip()
        or "eleven_multilingual_v2",
        secret_name=os.environ.get(
            "VIDEOWFLOW_VOICE_CLONE_SECRET_NAME", "ELEVENLABS_API_KEY"
        ).strip()
        or "ELEVENLABS_API_KEY",
    )


def _headers(cfg: VoiceCloneConfig) -> dict[str, str]:
    return {
        "xi-api-key": get_secret(cfg.secret_name),
        "accept": "audio/mpeg",
    }


def _provider_error(response: httpx.Response, action: str) -> TtsError:
    return TtsError(
        f"ElevenLabs {action} failed with HTTP {response.status_code}: "
        f"{response.text.strip()[:500] or 'empty response'}"
    )


def status() -> dict[str, object]:
    cfg = config()
    available = cfg.provider == "elevenlabs" and secret_present(cfg.secret_name)
    if cfg.provider == "none":
        reason = (
            "Voice cloning is opt-in. Set VIDEOWFLOW_VOICE_CLONE_PROVIDER=elevenlabs "
            "and ELEVENLABS_API_KEY to enable it."
        )
    elif not available:
        reason = f"Set the {cfg.secret_name} secret to enable the ElevenLabs clone provider."
    else:
        reason = f"ElevenLabs voice cloning is available with {cfg.model}."
    return {
        "ok": True,
        "available": available,
        "provider": cfg.provider,
        "providers": sorted(PROVIDERS - {"none"}),
        "consent_required": True,
        "reason": reason,
        "model": cfg.model,
        "profiles": len(_read()),
    }


def list_profiles() -> list[VoiceProfile]:
    return sorted(_read(), key=lambda item: item.created_at, reverse=True)


def create_profile(request: VoiceProfileRequest) -> VoiceProfile:
    consent = request.consent_ref.strip()
    if not consent:
        raise StateNotReadyError(
            "Voice cloning requires an explicit consent reference before a profile is stored."
        )
    cfg = config()
    paths = [item.strip() for item in request.sample_paths if item.strip()]
    provider_voice_id = ""
    if cfg.provider == "elevenlabs":
        key = get_secret(cfg.secret_name)
        if not key:
            raise CapabilityUnavailableError(
                "voice_clone",
                f"The {cfg.secret_name} secret is not configured.",
            )
        if not paths:
            raise StateNotReadyError(
                "ElevenLabs cloning requires at least one local reference sample path."
            )
        files: list[tuple[str, tuple[str, bytes, str]]] = []
        for raw in paths:
            path = Path(raw).expanduser()
            if not path.is_file():
                raise StateNotReadyError(f"Voice sample not found: {path}")
            files.append(
                ("files", (path.name, path.read_bytes(), "audio/wav"))
            )
        response = httpx.post(
            f"{cfg.base_url.rstrip('/')}/voices/add",
            headers={**_headers(cfg), "accept": "application/json"},
            data={
                "name": request.name.strip(),
                "description": f"consent:{consent}",
            },
            files=files,
            timeout=120.0,
        )
        if response.status_code >= 400:
            raise _provider_error(response, "voice creation")
        try:
            provider_voice_id = str(response.json().get("voice_id") or "")
        except (ValueError, AttributeError):
            provider_voice_id = ""
        if not provider_voice_id:
            raise TtsError("ElevenLabs did not return a voice_id")
    profile = VoiceProfile(
        id=f"voice-{uuid4().hex[:10]}",
        name=request.name.strip(),
        provider=cfg.provider,
        consent_ref=consent,
        sample_count=request.sample_count or len(paths),
        sample_paths=paths,
        provider_voice_id=provider_voice_id,
        created_at=_now(),
        metadata={str(key): str(value) for key, value in request.metadata.items()},
    )
    with _LOCK:
        payload = _read()
        payload.append(profile)
        _write(payload)
    return profile


def delete_profile(profile_id: str) -> None:
    with _LOCK:
        payload = _read()
        profile = next((item for item in payload if item.id == profile_id), None)
        if profile is None:
            raise StateNotReadyError(f"Unknown voice profile: {profile_id}")
        if profile.provider == "elevenlabs" and profile.provider_voice_id:
            cfg = config()
            with contextlib.suppress(Exception):
                httpx.delete(
                    f"{cfg.base_url.rstrip('/')}/voices/{profile.provider_voice_id}",
                    headers=_headers(cfg),
                    timeout=30.0,
                )
        kept = [item for item in payload if item.id != profile_id]
        _write(kept)


def synthesize(request: VoiceSynthesizeRequest) -> bytes:
    profile = next(
        (item for item in _read() if item.id == request.profile_id), None
    )
    if profile is None:
        raise StateNotReadyError(f"Unknown voice profile: {request.profile_id}")
    cfg = config()
    if profile.provider != "elevenlabs" or not profile.provider_voice_id:
        raise CapabilityUnavailableError(
            "voice_clone",
            "Voice cloning has no synthesis provider for this profile. Configure "
            "the provider and create a new profile with reference samples, or use "
            "the existing TTS voices.",
        )
    key = get_secret(cfg.secret_name)
    if not key:
        raise CapabilityUnavailableError(
            "voice_clone",
            f"The {cfg.secret_name} secret is not configured.",
        )
    response = httpx.post(
        f"{cfg.base_url.rstrip('/')}/text-to-speech/{profile.provider_voice_id}",
        headers={**_headers(cfg), "content-type": "application/json"},
        json={"text": request.text, "model_id": cfg.model},
        timeout=120.0,
    )
    if response.status_code >= 400:
        raise _provider_error(response, "speech synthesis")
    if not response.content:
        raise TtsError("ElevenLabs returned empty audio")
    return response.content
