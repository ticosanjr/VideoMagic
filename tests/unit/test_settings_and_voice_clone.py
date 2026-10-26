"""Settings persistence and the voice-clone shell edge paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application import settings as settings_module
from videoflow.application import voice_clone
from videoflow.application.settings import (
    AppSettings,
    effective_ffmpeg,
    effective_roots,
    load_settings,
    save_settings,
)
from videoflow.application.voice_clone import (
    VoiceProfileRequest,
    VoiceSynthesizeRequest,
    create_profile,
    delete_profile,
    list_profiles,
    synthesize,
)
from videoflow.domain.errors import CapabilityUnavailableError, StateNotReadyError


def test_settings_round_trip_and_corrupt_fallback(tmp_path: Path) -> None:
    assert load_settings() == AppSettings()

    original = AppSettings()
    original.paths.ffmpeg = "/usr/bin/ffmpeg"
    save_settings(original)
    assert load_settings().paths.ffmpeg == "/usr/bin/ffmpeg"

    settings_module.settings_path().write_text("not json", encoding="utf-8")
    assert load_settings() == AppSettings()


def test_effective_roots_and_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path / "a"))
    assert effective_roots() == [str(tmp_path / "a")]

    monkeypatch.delenv("VIDEOWFLOW_ALLOWED_ROOTS")
    configured = AppSettings()
    configured.paths.allowed_roots = [str(tmp_path)]
    assert effective_roots(configured) == [str(tmp_path)]
    assert effective_roots(AppSettings()) == []

    binary = tmp_path / "ffmpeg"
    binary.write_bytes(b"x")
    configured.paths.ffmpeg = str(binary)
    assert effective_ffmpeg("ffmpeg", configured) == str(binary)
    assert effective_ffmpeg("ffprobe", configured) == ""
    configured.paths.ffprobe = str(tmp_path / "missing")
    assert effective_ffmpeg("ffprobe", configured) == ""


def test_voice_profiles_round_trip(tmp_path: Path) -> None:
    assert list_profiles() == []

    profile = create_profile(
        VoiceProfileRequest(
            name="Narrator",
            consent_ref="consent-123",
            sample_count=3,
            metadata={"lang": "pt"},
        )
    )

    assert profile.provider == "none"
    assert list_profiles()[0].id == profile.id

    delete_profile(profile.id)
    assert list_profiles() == []

    with pytest.raises(StateNotReadyError, match="Unknown voice profile"):
        delete_profile(profile.id)


def test_voice_profiles_require_consent(tmp_path: Path) -> None:
    request = VoiceProfileRequest.model_construct(
        name="Narrator", consent_ref="   ", sample_count=0, metadata={}
    )

    with pytest.raises(StateNotReadyError, match="consent"):
        create_profile(request)


def test_voice_read_skips_corrupt_entries(tmp_path: Path) -> None:
    path = voice_clone._profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    assert list_profiles() == []

    path.write_text("[]", encoding="utf-8")
    assert list_profiles() == []

    path.write_text(json.dumps([{"id": "ok"}, "bad", {"id": ""}]), encoding="utf-8")
    assert list_profiles() == []


def test_voice_synthesis_is_unavailable(tmp_path: Path) -> None:
    profile = create_profile(
        VoiceProfileRequest(name="Narrator", consent_ref="consent")
    )

    with pytest.raises(CapabilityUnavailableError, match="no synthesis provider"):
        synthesize(VoiceSynthesizeRequest(profile_id=profile.id, text="hello"))

    with pytest.raises(StateNotReadyError, match="Unknown voice profile"):
        synthesize(VoiceSynthesizeRequest(profile_id="missing", text="hello"))
