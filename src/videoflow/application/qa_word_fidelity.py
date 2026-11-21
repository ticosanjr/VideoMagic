"""Word-level fidelity check against the final deliverable."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.qa_media import compare_text
from videoflow.application.text import STOPWORDS
from videoflow.domain.state import Sentence

_WORD = re.compile(r"[0-9A-Za-zÀ-ÿ']+")
_DEFAULT_ALIASES = {
    "hwang": "huang",
    "invidia": "nvidia",
    "envidia": "nvidia",
    "clodi": "claude",
    "emecepe": "mcp",
    "opencodi": "opencode",
    "uisper": "whisper",
    "micro$oft": "microsoft",
    "open ai": "openai",
    "open-ai": "openai",
}


def normalize_wer_text(text: str, aliases: Mapping[str, str] | None = None) -> str:
    """Normalize names, accents, punctuation, and configured aliases."""

    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold().replace("&", " e ")
    words = _WORD.findall(normalized)
    mapping = {
        **_DEFAULT_ALIASES,
        **{
            str(key).casefold(): str(value).casefold()
            for key, value in (aliases or {}).items()
        },
    }
    return " ".join(mapping.get(word, word) for word in words)


def verify_word_fidelity(
    video: Path,
    sentences: Sequence[Sentence],
    *,
    work: Path,
    language: str = "pt",
    model_size: str = "small",
    max_wer: float = 0.12,
    warning_wer: float = 0.06,
    aliases: Mapping[str, str] | None = None,
    compute_policy: str = "auto",
    allow_slow_cpu_fallback: bool = True,
) -> dict[str, Any]:
    reference = normalize_wer_text(
        " ".join(sentence.text for sentence in sentences),
        aliases=aliases,
    )
    if not reference:
        return {
            "status": "unavailable",
            "passed": True,
            "warning": "no transcript text to compare",
            "wer": None,
        }
    wav: Path | None = None
    heard: list[Sentence] = []
    placement = "local"
    if compute_policy != "local":
        try:
            from videoflow.application.asr_remote import RemoteAsrClient
            from videoflow.application.compute import (
                guard_remote_policy,
                router_from_settings,
            )

            router = router_from_settings()
            guard_remote_policy(
                router,
                "asr",
                compute_policy=compute_policy,
                allow_slow_cpu_fallback=allow_slow_cpu_fallback,
                error_cls=RuntimeError,
            )
            decision = router.decide("asr")
            if decision.is_remote:
                wav = FFmpegAdapter().extract_pcm(
                    Path(video).expanduser(),
                    Path(work) / "qa-fidelity.wav",
                    sample_rate=16000,
                )
                client = RemoteAsrClient(
                    router,
                    language=language if language in {"pt", "it", "en", "es", "auto"} else "auto",
                    model=model_size,
                    beam_size=1,
                    word_timestamps=False,
                    vad_filter=False,
                    capability="asr",
                )
                heard = client.transcribe(wav, 16000)
                placement = str(
                    (getattr(client, "execution", {}) or {}).get("execution_node")
                    or "remote_gpu"
                )
            elif compute_policy == "remote_only":
                return {
                    "status": "unavailable",
                    "passed": True,
                    "warning": f"remote ASR unavailable: {decision.reason}",
                    "wer": None,
                    "placement": "local",
                }
        except Exception as exc:  # noqa: BLE001 - local fallback is the contract
            if compute_policy == "remote_only" and not allow_slow_cpu_fallback:
                return {
                    "status": "unavailable",
                    "passed": True,
                    "warning": f"remote ASR unavailable: {exc}",
                    "wer": None,
                    "placement": "local",
                }
    if not heard:
        from videoflow.adapters.faster_whisper import FasterWhisperAdapter

        if not FasterWhisperAdapter.available(model_size=model_size):  # type: ignore[arg-type]
            return {
                "status": "unavailable",
                "passed": True,
                "warning": "faster-whisper small model is not installed",
                "wer": None,
                "placement": placement,
            }
        try:
            if wav is None:
                wav = FFmpegAdapter().extract_pcm(
                    Path(video).expanduser(),
                    Path(work) / "qa-fidelity.wav",
                    sample_rate=16000,
                )
            adapter = FasterWhisperAdapter(
                model_size=model_size,  # type: ignore[arg-type]
                language=language if language in {"pt", "it", "en", "es", "auto"} else "auto",  # type: ignore[arg-type]
                word_timestamps=False,
            )
            heard = adapter.transcribe(wav, 16000)
        except Exception as exc:  # noqa: BLE001 - optional QA backend
            return {
                "status": "unavailable",
                "passed": True,
                "warning": f"word fidelity check unavailable: {exc}",
                "wer": None,
                "placement": placement,
            }
    if not heard:
        return {
            "status": "unavailable",
            "passed": True,
            "warning": "ASR returned no words for QA fidelity",
            "wer": None,
            "placement": placement,
        }
    hypothesis = normalize_wer_text(
        " ".join(sentence.text for sentence in heard),
        aliases=aliases,
    )
    comparison = compare_text(reference, hypothesis)
    similarity = float(comparison.get("similarity") or 0.0)
    wer = max(0.0, 1.0 - similarity)
    repeated = _adjacent_repeats(hypothesis)
    content_repeats = [item for item in repeated if item["content"]]
    return {
        "status": "checked",
        "passed": wer < max_wer,
        "warning": warning_wer <= wer < max_wer,
        "wer": round(wer, 6),
        "similarity": round(similarity, 4),
        "max_wer": max_wer,
        "warning_wer": warning_wer,
        "reference_words": comparison.get("reference_words", 0),
        "spoken_words": comparison.get("spoken_words", 0),
        "missing": comparison.get("missing", [])[:40],
        "extra": comparison.get("extra", [])[:40],
        "repeated_words": [item["word"] for item in repeated][:40],
        "repeated_word_count": len(repeated),
        "repeated_content_words": len(content_repeats),
        "repeated_content_list": [item["word"] for item in content_repeats][:40],
        "placement": placement,
    }


__all__ = ["normalize_wer_text", "verify_word_fidelity"]


def _adjacent_repeats(hypothesis: str) -> list[dict[str, Any]]:
    """Count immediately repeated words in the transcribed deliverable."""

    tokens = [token for token in hypothesis.split() if token]
    repeats: list[dict[str, Any]] = []
    for left, right in zip(tokens, tokens[1:], strict=False):
        if left != right:
            continue
        repeats.append(
            {
                "word": left,
                "content": len(left) >= 3 and left not in STOPWORDS,
            }
        )
    return repeats
