"""Voice-clone shell: contracts and metadata only, no synthesis engine yet."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from videoflow.domain.errors import CapabilityUnavailableError, StateNotReadyError
from videoflow.runtime import portable_home

_LOCK = threading.RLock()
PROVIDERS = {"none"}


class VoiceCloneConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "none"
    base_url: str = ""
    model: str = ""
    secret_name: str = "VIDEOWFLOW_VOICE_CLONE_API_KEY"
    consent_required: bool = True


class VoiceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    provider: str = "none"
    consent_ref: str = ""
    sample_count: int = Field(default=0, ge=0)
    created_at: str
    metadata: dict[str, str] = Field(default_factory=dict)


class VoiceProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    consent_ref: str = Field(min_length=1, max_length=300)
    sample_count: int = Field(default=0, ge=0, le=100)
    metadata: dict[str, str] = Field(default_factory=dict)


class VoiceSynthesizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)


class VoiceCloneProvider(Protocol):
    def create_profile(self, request: VoiceProfileRequest) -> VoiceProfile: ...
    def synthesize(self, profile: VoiceProfile, text: str) -> bytes: ...
    def delete_profile(self, profile_id: str) -> None: ...


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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


def status() -> dict[str, object]:
    return {
        "ok": True,
        "available": False,
        "provider": "none",
        "providers": sorted(PROVIDERS - {"none"}),
        "consent_required": True,
        "reason": (
            "Voice cloning is a shell in this build. Configure a provider with an "
            "explicit clone contract before enabling synthesis."
        ),
        "profiles": len(_read()),
    }


def list_profiles() -> list[VoiceProfile]:
    return sorted(_read(), key=lambda item: item.created_at, reverse=True)


def create_profile(request: VoiceProfileRequest) -> VoiceProfile:
    if not request.consent_ref.strip():
        raise StateNotReadyError(
            "Voice cloning requires an explicit consent reference before a profile is stored."
        )
    profile = VoiceProfile(
        id=f"voice-{uuid4().hex[:10]}",
        name=request.name.strip(),
        provider="none",
        consent_ref=request.consent_ref.strip(),
        sample_count=request.sample_count,
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
        kept = [profile for profile in payload if profile.id != profile_id]
        if len(kept) == len(payload):
            raise StateNotReadyError(f"Unknown voice profile: {profile_id}")
        _write(kept)


def synthesize(request: VoiceSynthesizeRequest) -> bytes:
    profile = next(
        (item for item in _read() if item.id == request.profile_id), None
    )
    if profile is None:
        raise StateNotReadyError(f"Unknown voice profile: {request.profile_id}")
    raise CapabilityUnavailableError(
        "voice_clone",
        "Voice cloning has no synthesis provider in this build. "
        "Configure an approved provider or use the existing TTS voices.",
    )
