"""Default ASR checkpoint selection and on-demand installation."""

from __future__ import annotations


def default_asr_model_id() -> str:
    """Default Whisper checkpoint for this machine.

    A local CUDA device gets ``large-v3-turbo``; CPU-only machines keep the
    small model so transcription stays interactive.
    """

    from .profiles import _local_gpu_available

    return (
        "faster-whisper-large-v3-turbo"
        if _local_gpu_available()
        else "faster-whisper-small"
    )


def auto_install_model(model_id: str) -> bool:
    """Install ``model_id`` when automatic downloads are allowed."""

    try:
        from videoflow.application.bootstrap_runtime import auto_download_disabled

        if auto_download_disabled():
            return False
        from videoflow.application.models import install_model, invalidate_model_cache

        result = install_model(model_id, allow_network=True)
        invalidate_model_cache()
        return bool(result.get("installed"))
    except Exception:  # noqa: BLE001 - planning must survive offline machines
        return False


__all__ = ["auto_install_model", "default_asr_model_id"]
