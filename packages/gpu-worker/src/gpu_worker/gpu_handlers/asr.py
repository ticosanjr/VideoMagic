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

def make_asr_handler(
    settings: Settings,
    models: ModelRegistry | None = None,
) -> Handler:
    """faster-whisper handler returning a JSON transcript with word timings."""

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
        report("transcribing", 15)
        try:
            segments, info = model.transcribe(
                str(input_paths[0]),
                language=language,
                beam_size=beam_size,
                word_timestamps=word_timestamps,
                vad_filter=bool(params.get("vad_filter", True)),
                condition_on_previous_text=bool(
                    params.get("condition_on_previous_text", False)
                ),
                no_speech_threshold=float(params.get("no_speech_threshold", 0.6)),
                compression_ratio_threshold=float(
                    params.get("compression_ratio_threshold", 2.2)
                ),
                repetition_penalty=float(params.get("repetition_penalty", 1.1)),
            )
            payload = {
                "schema_version": 1,
                "model": model_name,
                "language": str(getattr(info, "language", language) or language),
                "language_probability": float(
                    getattr(info, "language_probability", 0.0) or 0.0
                ),
                "segments": [],
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
                            "probability": float(
                                getattr(word, "probability", 0.0) or 0.0
                            ),
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
        except Exception as exc:  # noqa: BLE001 - runtime backend failure
            raise HandlerError(f"faster-whisper failed: {exc}") from exc
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
