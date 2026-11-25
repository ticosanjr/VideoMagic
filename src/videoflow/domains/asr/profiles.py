"""Adaptive speech-to-text profile resolution.

The profile is the flexible knob: it selects an engine, model, decoding budget,
thread count, and fallback. Explicit step parameters still win when the profile
is ``custom``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from videoflow.application.settings import AppSettings

from .provisioning import auto_install_model


@dataclass(frozen=True)
class AsrPlan:
    profile: str
    mode: str
    model_id: str = ""
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 1
    cpu_threads: int = 0
    vad_filter: bool = True
    word_timestamps: bool = True
    condition_on_previous_text: bool = False
    remote_base_url: str = ""
    remote_model: str = "whisper-1"
    remote_api_key_env: str = "VIDEOWFLOW_ASR_API_KEY"
    fallback_reason: str = ""


def physical_threads() -> int:
    """Use physical cores, not SMT siblings, for CTranslate2."""

    count = os.cpu_count() or 2
    return max(1, min(8, count // 2 or count))


def _local_gpu_available() -> bool:
    """Whether a local NVIDIA CUDA device can run Faster-Whisper."""

    try:
        from vf_shared.compute.local_gpu import local_gpu_available
    except Exception:  # noqa: BLE001 - detection must never break planning
        return False
    return local_gpu_available()


def _installed_models() -> dict[str, bool]:
    try:
        from videoflow.application.models import list_models

        return {
            str(item.get("id")): bool(item.get("installed"))
            for item in list_models()
        }
    except Exception:  # noqa: BLE001 - preflight must not fail
        return {}


def _model_size(model_id: str) -> str:
    for size in (
        "large-v3-turbo",
        "large-v3",
        "large-v2",
        "medium",
        "small",
        "base",
        "tiny",
    ):
        if size in model_id:
            return size
    return "small"


def _first_installed(
    candidates: tuple[str, ...], installed: dict[str, bool]
) -> str:
    return next((item for item in candidates if installed.get(item)), "")


def _vulkan_available() -> bool:
    """Whether whisper.cpp has a Vulkan build and a non-software device."""

    marker = os.environ.get("VIDEOWFLOW_WHISPER_VULKAN", "").strip().lower()
    if marker in {"0", "false", "no", "off"}:
        return False
    try:
        from videoflow.runtime import find_whisper_binary

        binary = find_whisper_binary()
    except Exception:  # noqa: BLE001
        binary = None
    if not binary:
        return False
    from pathlib import Path

    flag = Path(binary).parent / "vulkan.flag"
    if not flag.is_file() and marker not in {"1", "true", "yes"}:
        return False
    try:
        completed = os.popen("vulkaninfo --summary 2>/dev/null").read()
    except OSError:
        return True
    if not completed:
        return True
    return "llvmpipe" not in completed.casefold()


def _resolve_threads(settings: AppSettings, options: Any) -> int:
    explicit = int(getattr(options, "cpu_threads", 0) or 0)
    if explicit > 0:
        return explicit
    if settings.speech.cpu_threads > 0:
        return settings.speech.cpu_threads
    if settings.models.threads > 0:
        return settings.models.threads
    return physical_threads()


def resolve_asr_plan(
    settings: AppSettings,
    options: Any,
    *,
    installed: dict[str, bool] | None = None,
    vulkan: bool | None = None,
) -> AsrPlan:
    """Resolve one run into a concrete engine/model/decoding plan."""

    installed_models = installed if installed is not None else _installed_models()
    requested = str(getattr(options, "quality_profile", "auto") or "auto")
    if requested == "auto":
        requested = settings.speech.quality_profile
    if requested == "auto":
        requested = "balanced"
    profile = requested

    requested_device = str(getattr(options, "device", "cpu") or "cpu")
    explicit_cuda = requested_device == "cuda"
    device = requested_device
    if device == "cpu":
        device = settings.speech.device
    forced_device = os.environ.get("VIDEOWFLOW_ASR_DEVICE", "").strip().lower()
    if forced_device in {"cpu", "cuda", "auto"}:
        device = forced_device
        explicit_cuda = explicit_cuda or forced_device == "cuda"
    policy = str(getattr(options, "compute_policy", "auto") or "auto").strip().lower()
    gpu_fallback = ""
    local_gpu = False
    if policy in {"auto", "local_gpu"} and forced_device != "cpu":
        local_gpu = _local_gpu_available()
        if local_gpu:
            device = "cuda"
    elif policy == "local_gpu":
        device = "cpu"
        gpu_fallback = "local_gpu requested but VIDEOWFLOW_ASR_DEVICE forced cpu"
    if policy == "local_gpu" and not local_gpu and not gpu_fallback:
        if forced_device != "cuda":
            device = "cpu"
        gpu_fallback = "local_gpu requested but no local CUDA device was detected"
    if device == "cuda" and not local_gpu:
        if explicit_cuda or forced_device == "cuda":
            from videoflow.domain.errors import TranscriptionError

            raise TranscriptionError(
                "CUDA ASR was requested but no local NVIDIA GPU was detected"
            )
        device = "cpu"
        gpu_fallback = (
            gpu_fallback
            or "CUDA runtime requested but no local NVIDIA GPU was detected; using CPU"
        )
    compute_type = str(getattr(options, "compute_type", "int8") or "int8")
    if compute_type == "int8":
        compute_type = settings.speech.compute_type
    forced_compute = os.environ.get("VIDEOWFLOW_ASR_COMPUTE_TYPE", "").strip()
    if forced_compute:
        compute_type = forced_compute
    elif device == "cuda" and compute_type == "int8":
        compute_type = "float16" if local_gpu else "int8_float16"
    if gpu_fallback and device == "cpu" and not forced_compute:
        compute_type = "int8"
    if profile == "custom":
        model_id = str(getattr(options, "model_id", "") or "") or str(
            settings.models.defaults.get("asr", "")
        )
        mode = str(getattr(options, "mode", "auto") or "auto")
        return AsrPlan(
            profile=profile,
            mode=mode,
            model_id=model_id,
            model_size=_model_size(model_id),
            device=device,
            compute_type=compute_type,
            beam_size=int(getattr(options, "beam_size", 0) or settings.speech.beam_size),
            cpu_threads=_resolve_threads(settings, options),
            vad_filter=bool(
                getattr(options, "vad_filter", None)
                if getattr(options, "vad_filter", None) is not None
                else settings.speech.vad_filter
            ),
            word_timestamps=str(getattr(options, "word_timestamps", "auto"))
            != "off",
            condition_on_previous_text=bool(
                getattr(options, "condition_on_previous_text", None)
                if getattr(options, "condition_on_previous_text", None)
                is not None
                else settings.speech.condition_on_previous_text
            ),
            remote_base_url=str(getattr(options, "base_url", "") or ""),
            remote_model=str(getattr(options, "model", "whisper-1") or "whisper-1"),
            remote_api_key_env=str(
                getattr(options, "api_key_env", "VIDEOWFLOW_ASR_API_KEY")
                or "VIDEOWFLOW_ASR_API_KEY"
            ),
            fallback_reason=gpu_fallback,
        )

    fallback = ""
    if profile == "remote":
        base_url = (
            str(getattr(options, "base_url", "") or "")
            or settings.speech.remote_base_url
            or os.environ.get("VIDEOWFLOW_ASR_BASE_URL", "")
        )
        return AsrPlan(
            profile=profile,
            mode="http",
            remote_base_url=base_url,
            remote_model=settings.speech.remote_model
            or str(getattr(options, "model", "") or "whisper-1"),
            remote_api_key_env=str(
                getattr(options, "api_key_env", "")
                or settings.speech.remote_api_key_env
            ),
            fallback_reason="" if base_url else "remote ASR base URL is not configured",
        )

    if profile == "vulkan":
        whisper_model = _first_installed(
            (
                "whisper-large-v3-turbo-q5_0",
                "whisper-large-v3-turbo",
                "whisper-large-v3",
                "whisper-medium",
            ),
            installed_models,
        )
        if whisper_model and (vulkan if vulkan is not None else _vulkan_available()):
            return AsrPlan(
                profile=profile,
                mode="whisper_cpp",
                model_id=whisper_model,
                model_size=_model_size(whisper_model),
                device="cpu",
                compute_type=compute_type,
                beam_size=1,
                cpu_threads=_resolve_threads(settings, options),
                vad_filter=True,
                word_timestamps=True,
                condition_on_previous_text=False,
                fallback_reason=gpu_fallback,
            )
        fallback = (
            "Vulkan whisper.cpp backend or turbo model is unavailable; "
            "using the balanced faster-whisper profile"
        )
        profile = "balanced"

    explicit_model = str(getattr(options, "model_id", "") or "").strip()
    candidates = {
        "fast": (
            "faster-whisper-small",
            "faster-whisper-base",
            "faster-whisper-tiny",
        ),
        "balanced": (
            (
                "faster-whisper-large-v3-turbo",
                "faster-whisper-large-v3",
                "faster-whisper-medium",
                "faster-whisper-small",
            )
            if local_gpu
            else (
                "faster-whisper-small",
                "faster-whisper-base",
                "faster-whisper-tiny",
            )
        ),
        "quality": (
            "faster-whisper-large-v3",
            "faster-whisper-large-v3-turbo",
            "faster-whisper-medium",
        ),
    }.get(profile, ())
    model_id = _first_installed(candidates, installed_models)
    if (
        not model_id
        and candidates
        and not explicit_model
        and installed is None
        and auto_install_model(candidates[0])
    ):
        installed_models[candidates[0]] = True
        model_id = candidates[0]
    if not model_id:
        # Prefer whisper.cpp only for its own checkpoints, then any installed
        # Faster-Whisper model, then the HTTP fallback.
        whisper_model = _first_installed(
            (
                "whisper-large-v3-turbo-q5_0",
                "whisper-large-v3-turbo",
                "whisper-large-v3",
                "whisper-medium",
                "whisper-small",
            ),
            installed_models,
        )
        if whisper_model:
            return AsrPlan(
                profile=profile,
                mode="whisper_cpp",
                model_id=whisper_model,
                model_size=_model_size(whisper_model),
                device="cpu",
                compute_type=compute_type,
                beam_size=1,
                cpu_threads=_resolve_threads(settings, options),
                vad_filter=True,
                word_timestamps=True,
                condition_on_previous_text=False,
                fallback_reason=fallback
                or "No faster-whisper model is installed; using whisper.cpp",
            )
        model_id = _first_installed(
            (
                "faster-whisper-large-v3",
                "faster-whisper-large-v3-turbo",
                "faster-whisper-medium",
                "faster-whisper-small",
                "faster-whisper-base",
                "faster-whisper-tiny",
            ),
            installed_models,
        )
        if not model_id:
            return AsrPlan(
                profile=profile,
                mode="auto",
                device=device,
                compute_type=compute_type,
                beam_size=1,
                cpu_threads=_resolve_threads(settings, options),
                vad_filter=True,
                word_timestamps=True,
                fallback_reason=fallback or "No local ASR model is installed",
            )

    vad = getattr(options, "vad_filter", None)
    beam = int(getattr(options, "beam_size", 0) or 0)
    if beam <= 0:
        beam = 5 if profile == "quality" else 1
    words = str(
        getattr(options, "word_timestamps", "auto")
        or settings.speech.word_timestamps
    )
    return AsrPlan(
        profile=profile,
        mode="faster_whisper",
        model_id=model_id,
        model_size=_model_size(model_id),
        device=device,
        compute_type=compute_type,
        beam_size=beam,
        cpu_threads=_resolve_threads(settings, options),
        vad_filter=bool(True if vad is None else vad),
        word_timestamps=words != "off",
        condition_on_previous_text=bool(
            settings.speech.condition_on_previous_text
            if getattr(options, "condition_on_previous_text", None) is None
            else options.condition_on_previous_text
        ),
        fallback_reason=fallback or gpu_fallback,
    )
