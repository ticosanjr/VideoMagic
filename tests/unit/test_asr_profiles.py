from __future__ import annotations

from types import SimpleNamespace

from videoflow.application.asr_profiles import (
    physical_threads,
    resolve_asr_plan,
)
from videoflow.application.settings import AppSettings


def _settings(**speech) -> AppSettings:
    base = AppSettings()
    return base.model_copy(update={"speech": base.speech.model_copy(update=speech)})


def _options(**kwargs):
    defaults = {
        "quality_profile": "auto",
        "mode": "auto",
        "model_id": "",
        "model_size": "small",
        "device": "cpu",
        "compute_type": "int8",
        "beam_size": 0,
        "cpu_threads": 0,
        "word_timestamps": "auto",
        "vad_filter": None,
        "condition_on_previous_text": None,
        "base_url": None,
        "model": "whisper-1",
        "api_key_env": "VIDEOWFLOW_ASR_API_KEY",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_balanced_prefers_turbo_and_greedy_cpu() -> None:
    settings = _settings(quality_profile="balanced")
    plan = resolve_asr_plan(
        settings,
        _options(),
        installed={
            "faster-whisper-large-v3": True,
            "faster-whisper-large-v3-turbo": True,
            "faster-whisper-small": True,
        },
    )
    assert plan.mode == "faster_whisper"
    assert plan.model_id == "faster-whisper-large-v3-turbo"
    assert plan.beam_size == 1
    assert plan.vad_filter is True
    assert plan.word_timestamps is True
    assert plan.cpu_threads == physical_threads()


def test_fast_and_quality_profiles() -> None:
    settings = _settings(quality_profile="fast")
    fast = resolve_asr_plan(
        settings,
        _options(),
        installed={"faster-whisper-small": True, "faster-whisper-large-v3": True},
    )
    assert fast.model_id == "faster-whisper-small"
    assert fast.beam_size == 1

    settings = _settings(quality_profile="quality")
    quality = resolve_asr_plan(
        settings,
        _options(),
        installed={"faster-whisper-small": True, "faster-whisper-large-v3": True},
    )
    assert quality.model_id == "faster-whisper-large-v3"
    assert quality.beam_size == 5


def test_explicit_decoding_options_win() -> None:
    settings = _settings(quality_profile="balanced")
    plan = resolve_asr_plan(
        settings,
        _options(
            beam_size=3,
            cpu_threads=2,
            vad_filter=False,
            word_timestamps="off",
            condition_on_previous_text=True,
        ),
        installed={"faster-whisper-large-v3-turbo": True},
    )
    assert plan.beam_size == 3
    assert plan.cpu_threads == 2
    assert plan.vad_filter is False
    assert plan.word_timestamps is False
    assert plan.condition_on_previous_text is True


def test_vulkan_and_remote_profiles() -> None:
    settings = _settings(quality_profile="vulkan")
    vulkan = resolve_asr_plan(
        settings,
        _options(),
        installed={"whisper-large-v3-turbo-q5_0": True},
        vulkan=True,
    )
    assert vulkan.mode == "whisper_cpp"
    assert vulkan.model_id == "whisper-large-v3-turbo-q5_0"
    assert vulkan.beam_size == 1

    fallback = resolve_asr_plan(
        settings,
        _options(),
        installed={"faster-whisper-large-v3-turbo": True},
        vulkan=False,
    )
    assert fallback.mode == "faster_whisper"
    assert fallback.fallback_reason

    settings = _settings(
        quality_profile="remote",
        remote_base_url="http://100.64.0.2:8000/v1",
        remote_model="large-v3-turbo",
    )
    remote = resolve_asr_plan(settings, _options())
    assert remote.mode == "http"
    assert remote.remote_base_url == "http://100.64.0.2:8000/v1"
    assert remote.remote_model == "large-v3-turbo"


def test_custom_profile_keeps_explicit_model_and_no_models_falls_back() -> None:
    settings = _settings(quality_profile="balanced")
    custom = resolve_asr_plan(
        settings,
        _options(
            quality_profile="custom",
            mode="faster_whisper",
            model_id="faster-whisper-small",
        ),
        installed={"faster-whisper-small": True},
    )
    assert custom.profile == "custom"
    assert custom.mode == "faster_whisper"
    assert custom.model_id == "faster-whisper-small"

    none = resolve_asr_plan(settings, _options(), installed={})
    assert none.mode == "auto"
    assert none.fallback_reason


def test_vulkan_availability_checks(tmp_path, monkeypatch) -> None:
    from videoflow.application import asr_profiles

    monkeypatch.setenv("VIDEOWFLOW_WHISPER_VULKAN", "0")
    assert asr_profiles._vulkan_available() is False

    monkeypatch.delenv("VIDEOWFLOW_WHISPER_VULKAN", raising=False)
    monkeypatch.setattr(
        "videoflow.runtime.find_whisper_binary", lambda: None
    )
    assert asr_profiles._vulkan_available() is False

    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"bin")
    marker = tmp_path / "vulkan.flag"
    marker.write_text("vulkan\\n", encoding="utf-8")
    monkeypatch.setattr(
        "videoflow.runtime.find_whisper_binary", lambda: str(binary)
    )
    monkeypatch.setattr(
        asr_profiles.os,
        "popen",
        lambda command: SimpleNamespace(
            read=lambda: "deviceName = llvmpipe (LLVM)"
        ),
    )
    assert asr_profiles._vulkan_available() is False

    monkeypatch.setattr(
        asr_profiles.os,
        "popen",
        lambda command: SimpleNamespace(read=lambda: "deviceName = Radeon 680M"),
    )
    assert asr_profiles._vulkan_available() is True

    marker.unlink()
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_VULKAN", "1")
    assert asr_profiles._vulkan_available() is True
