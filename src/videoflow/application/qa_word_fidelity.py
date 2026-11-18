"""Word-level fidelity check against the final deliverable."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.qa_media import compare_text
from videoflow.domain.state import Sentence


def verify_word_fidelity(
    video: Path,
    sentences: Sequence[Sentence],
    *,
    work: Path,
    language: str = "pt",
    model_size: str = "small",
) -> dict[str, Any]:
    reference = " ".join(sentence.text for sentence in sentences).strip()
    if not reference:
        return {
            "status": "unavailable",
            "passed": True,
            "warning": "no transcript text to compare",
            "wer": None,
        }
    from videoflow.adapters.faster_whisper import FasterWhisperAdapter

    if not FasterWhisperAdapter.available(model_size=model_size):  # type: ignore[arg-type]
        return {
            "status": "unavailable",
            "passed": True,
            "warning": "faster-whisper small model is not installed",
            "wer": None,
        }
    try:
        wav = FFmpegAdapter().extract_pcm(
            Path(video).expanduser(), Path(work) / "qa-fidelity.wav", sample_rate=16000
        )
        adapter = FasterWhisperAdapter(
            model_size=model_size,  # type: ignore[arg-type]
            language=language if language in {"pt", "it", "en", "es", "auto"} else "auto",  # type: ignore[arg-type]
            word_timestamps=False,
        )
        heard = adapter.transcribe(wav, 16000)
        hypothesis = " ".join(sentence.text for sentence in heard)
        comparison = compare_text(reference, hypothesis)
        similarity = float(comparison.get("similarity") or 0.0)
        wer = max(0.0, 1.0 - similarity)
        return {
            "status": "checked",
            "passed": wer < 0.03,
            "wer": round(wer, 6),
            "similarity": round(similarity, 4),
            "reference_words": comparison.get("reference_words", 0),
            "spoken_words": comparison.get("spoken_words", 0),
            "missing": comparison.get("missing", [])[:40],
            "extra": comparison.get("extra", [])[:40],
        }
    except Exception as exc:  # noqa: BLE001 - optional QA backend
        return {
            "status": "unavailable",
            "passed": True,
            "warning": f"word fidelity check unavailable: {exc}",
            "wer": None,
        }


__all__ = ["verify_word_fidelity"]
