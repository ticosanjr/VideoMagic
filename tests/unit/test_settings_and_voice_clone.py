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
    assert "invalid" in settings_module.settings_error()

    save_settings(AppSettings())
    assert load_settings() == AppSettings()
    assert settings_module.settings_error() == ""


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


def test_elevenlabs_clone_profile_and_synthesis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    sample = tmp_path / "speaker.wav"
    sample.write_bytes(b"RIFFdata")
    monkeypatch.setenv("VIDEOWFLOW_VOICE_CLONE_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    calls: list[dict[str, object]] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        if str(url).endswith("/voices/add"):
            return httpx.Response(
                200,
                json={"voice_id": "voice-123"},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            content=b"mp3-bytes",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(voice_clone.httpx, "post", fake_post)
    profile = create_profile(
        VoiceProfileRequest(
            name="Host clone",
            consent_ref="consent-123",
            sample_paths=[str(sample)],
        )
    )
    assert profile.provider == "elevenlabs"
    assert profile.provider_voice_id == "voice-123"
    assert profile.sample_count == 1
    assert calls[0]["headers"]["xi-api-key"] == "test-key"  # type: ignore[index]

    audio = synthesize(
        VoiceSynthesizeRequest(profile_id=profile.id, text="hello")
    )
    assert audio == b"mp3-bytes"
    assert str(calls[1]["url"]).endswith("/text-to-speech/voice-123")
    status = voice_clone.status()
    assert status["available"] is True
    assert status["provider"] == "elevenlabs"

    delete_profile(profile.id)
    assert list_profiles() == []


def test_settings_cache_invalidates_when_the_file_changes(tmp_path: Path) -> None:
    save_settings(AppSettings())
    first = load_settings()
    path = settings_module.settings_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["paths"]["ffmpeg"] = "/tmp/other-ffmpeg"
    path.write_text(json.dumps(payload), encoding="utf-8")

    second = load_settings()
    assert first is not second
    assert second.paths.ffmpeg == "/tmp/other-ffmpeg"
