"""Local CUDA/NVENC selection must never require nvidia-smi or a GPU that is absent."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from videoflow.application.settings import AppSettings
from videoflow.domain.errors import TranscriptionError
from videoflow.domains.asr import profiles as asr_profiles


def _options(**overrides):
    defaults = {
        "quality_profile": "balanced",
        "mode": "auto",
        "model_id": "",
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
        "compute_policy": "auto",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_cuda_build_without_gpu_falls_back_to_cpu(monkeypatch) -> None:
    monkeypatch.setattr(asr_profiles, "_local_gpu_available", lambda: False)
    monkeypatch.delenv("VIDEOWFLOW_ASR_DEVICE", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_ASR_COMPUTE_TYPE", raising=False)
    plan = asr_profiles.resolve_asr_plan(
        AppSettings(),
        _options(),
        installed={"faster-whisper-large-v3-turbo": True},
    )
    assert plan.device == "cpu"
    assert plan.compute_type == "int8"


def test_local_gpu_policy_uses_cuda_and_float16(monkeypatch) -> None:
    monkeypatch.setattr(asr_profiles, "_local_gpu_available", lambda: True)
    monkeypatch.delenv("VIDEOWFLOW_ASR_DEVICE", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_ASR_COMPUTE_TYPE", raising=False)
    plan = asr_profiles.resolve_asr_plan(
        AppSettings(),
        _options(compute_policy="local_gpu"),
        installed={"faster-whisper-large-v3-turbo": True},
    )
    assert plan.device == "cuda"
    assert plan.compute_type == "float16"


def test_explicit_cuda_without_gpu_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(asr_profiles, "_local_gpu_available", lambda: False)
    monkeypatch.delenv("VIDEOWFLOW_ASR_DEVICE", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_ASR_COMPUTE_TYPE", raising=False)
    with pytest.raises(TranscriptionError, match="no local NVIDIA GPU"):
        asr_profiles.resolve_asr_plan(
            AppSettings(),
            _options(device="cuda"),
            installed={"faster-whisper-large-v3-turbo": True},
        )


def test_local_gpu_policy_without_gpu_returns_cpu(monkeypatch) -> None:
    monkeypatch.setattr(asr_profiles, "_local_gpu_available", lambda: False)
    monkeypatch.delenv("VIDEOWFLOW_ASR_DEVICE", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_ASR_COMPUTE_TYPE", raising=False)
    plan = asr_profiles.resolve_asr_plan(
        AppSettings(),
        _options(compute_policy="local_gpu"),
        installed={"faster-whisper-large-v3-turbo": True},
    )
    assert plan.device == "cpu"
    assert plan.compute_type == "int8"
    assert plan.fallback_reason


def test_router_reports_a_healthy_local_gpu(monkeypatch) -> None:
    from vf_shared.compute import ComputeRouter
    from vf_shared.compute import local_gpu as local_gpu_module

    monkeypatch.setattr(local_gpu_module, "local_gpu_available", lambda **_: True)
    monkeypatch.setattr(local_gpu_module, "local_gpu_name", lambda: "RTX 3060")
    router = ComputeRouter(mode="local_gpu", discovery_enabled=False)
    health = router.health()
    assert health.available is True
    assert health.gpu_name == "RTX 3060"
    assert health.nvenc is True
    assert router.execution_node == "local_cuda"
    assert router.decide("asr").is_remote is False


def test_auto_router_uses_local_gpu_without_a_worker(monkeypatch) -> None:
    from vf_shared.compute import ComputeRouter
    from vf_shared.compute import local_gpu as local_gpu_module

    monkeypatch.setattr(local_gpu_module, "local_gpu_available", lambda **_: True)
    monkeypatch.setattr(local_gpu_module, "local_gpu_name", lambda: "RTX 3060")
    router = ComputeRouter(mode="auto", discovery_enabled=False)
    assert router.health().available is True
    assert router.execution_node == "local_cuda"
    assert router.decide("render_nvenc").is_remote is False


def test_video_encoder_does_not_require_nvidia_smi(monkeypatch) -> None:
    from videoflow.exporters import mp4

    monkeypatch.setenv("VF_VIDEO_ENCODER", "auto")
    monkeypatch.setattr(mp4.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        "videoflow.core.nvenc.nvenc_available", lambda *_a, **_k: True
    )
    mp4.video_encoder.cache_clear()
    assert mp4.video_encoder() == "h264_nvenc"
    mp4.video_encoder.cache_clear()
