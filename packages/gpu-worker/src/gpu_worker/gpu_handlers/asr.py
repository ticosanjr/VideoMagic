"""Faster-Whisper ASR and forced-alignment handlers."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gpu_worker.handlers import Handler, HandlerError
from gpu_worker.progress import report

if TYPE_CHECKING:
    from gpu_worker.models import ModelRegistry
    from gpu_worker.settings import Settings

_ASR_MODELS: dict[tuple[str, str, str], Any] = {}
_ASR_LOCK = threading.RLock()

_VAD_MARKERS = (
    "onnxruntime",
    "sessionoptions",
    "inferencesession",
    "silero",
    "vad model",
)


def _vad_backend_error(exc: BaseException) -> bool:
    message = f"{type(exc).__name__}: {exc}".casefold()
    return any(marker in message for marker in _VAD_MARKERS)


def _transcribe_once(
    model: Any,
    path: str,
    *,
    language: str,
    beam_size: int,
    word_timestamps: bool,
    vad_filter: bool,
    params: dict[str, Any],
) -> dict[str, Any]:
    report("transcribing", 15)
    segments, info = model.transcribe(
        path,
        language=language,
        beam_size=beam_size,
        word_timestamps=word_timestamps,
        vad_filter=vad_filter,
        condition_on_previous_text=bool(
            params.get("condition_on_previous_text", False)
        ),
        no_speech_threshold=float(params.get("no_speech_threshold", 0.6)),
        compression_ratio_threshold=float(
            params.get("compression_ratio_threshold", 2.2)
        ),
        repetition_penalty=float(params.get("repetition_penalty", 1.1)),
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "segments": [],
        "vad_filter": bool(vad_filter),
    }
    total_duration = float(getattr(info, "duration", 0.0) or 0.0)
    for segment in segments:
        if total_duration > 0:
            report(
                "transcribing",
                15 + round(75 * min(1.0, float(segment.end) / total_duration)),
            )
        words = []
        for word in getattr(segment, "words", None) or []:
            words.append(
                {
                    "word": str(getattr(word, "word", "") or ""),
                    "start": float(getattr(word, "start", 0.0) or 0.0),
                    "end": float(getattr(word, "end", 0.0) or 0.0),
                    "probability": float(getattr(word, "probability", 0.0) or 0.0),
                }
            )
        payload["segments"].append(
            {
                "start": float(getattr(segment, "start", 0.0) or 0.0),
                "end": float(getattr(segment, "end", 0.0) or 0.0),
                "text": str(getattr(segment, "text", "") or "").strip(),
                "words": words,
            }
        )
    payload["language"] = str(getattr(info, "language", language) or language)
    payload["language_probability"] = float(
        getattr(info, "language_probability", 0.0) or 0.0
    )
    return payload


def make_asr_handler(
    settings: Settings,
    models: ModelRegistry | None = None,
) -> Handler:
    """faster-whisper handler returning a JSON transcript with word timings.

    If the optional ONNX runtime used by the Silero VAD is broken, the handler
    retries once without ``vad_filter``. Transcription keeps working remotely
    even before the ONNX package is repaired; the payload records the fallback.
    """

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("asr requires an input audio artifact")
        model_name = str(params.get("model") or settings.asr_model or "large-v3-turbo")
        device = str(params.get("device") or settings.asr_device or "cuda")
        compute_type = str(
            params.get("compute_type") or settings.asr_compute_type or "float16"
        )
        key = (model_name, device, compute_type)
        model_key = f"faster-whisper:{model_name}:{device}:{compute_type}"
        report("loading ASR model", 8)
        with _ASR_LOCK:
            model = _ASR_MODELS.get(key)
            if model is None:
                try:
                    from faster_whisper import WhisperModel
                except Exception as exc:  # noqa: BLE001 - optional dependency
                    raise HandlerError(f"faster-whisper is not installed: {exc}") from exc
                model = WhisperModel(
                    model_name,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=int(params.get("cpu_threads") or settings.asr_cpu_threads or 0),
                    num_workers=int(params.get("num_workers") or settings.asr_num_workers or 1),
                )
                _ASR_MODELS[key] = model

                def unload() -> None:
                    _ASR_MODELS.pop(key, None)

                if models is not None:
                    models.register(
                        model_key,
                        capability="asr",
                        unload=unload,
                        vram_mb=3277,
                        metadata={"model": model_name, "device": device},
                    )
            elif models is not None:
                models.touch(model_key)
        language = str(params.get("language") or "pt")
        beam_size = int(params.get("beam_size") or 5)
        word_timestamps = bool(params.get("word_timestamps", True))
        vad_filter = bool(params.get("vad_filter", True))
        try:
            payload = _transcribe_once(
                model,
                str(input_paths[0]),
                language=language,
                beam_size=beam_size,
                word_timestamps=word_timestamps,
                vad_filter=vad_filter,
                params=params,
            )
        except Exception as exc:  # noqa: BLE001 - runtime backend failure
            if not vad_filter or not _vad_backend_error(exc):
                raise HandlerError(f"faster-whisper failed: {exc}") from exc
            report("retrying without VAD", 20)
            try:
                payload = _transcribe_once(
                    model,
                    str(input_paths[0]),
                    language=language,
                    beam_size=beam_size,
                    word_timestamps=word_timestamps,
                    vad_filter=False,
                    params=params,
                )
            except Exception as retry_exc:  # noqa: BLE001
                raise HandlerError(f"faster-whisper failed: {retry_exc}") from retry_exc
            payload["vad_fallback"] = True
            payload["vad_error"] = f"{type(exc).__name__}: {exc}"[:500]
        payload["model"] = model_name
        report("writing transcript", 95)
        target = work_dir / "transcript.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return [target]

    return handler


def make_forced_align_handler(settings: Settings) -> Handler:
    """Word-level alignment using the worker ASR model.

    WhisperX is not part of the base Windows runtime, so faster-whisper word
    timestamps are the portable worker backend. The payload keeps the same
    ``segments`` contract as the ASR handler.
    """

    inner = make_asr_handler(settings)

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        options = dict(params)
        options.setdefault("beam_size", 1)
        options.setdefault("vad_filter", False)
        options.setdefault("word_timestamps", True)
        options.setdefault("condition_on_previous_text", False)
        outputs = inner(options, input_paths, work_dir)
        if not outputs:
            raise HandlerError("forced_align produced no transcript")
        target = work_dir / "alignment.json"
        Path(outputs[0]).replace(target)
        return [target]

    return handler
