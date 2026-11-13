#!/usr/bin/env python
"""Benchmark one speech profile on a 16 kHz WAV sample."""

from __future__ import annotations

import argparse
import json
import time
import wave
from pathlib import Path
from types import SimpleNamespace

from videoflow.adapters.faster_whisper import FasterWhisperAdapter
from videoflow.adapters.whisper import WhisperCliAdapter
from videoflow.application.asr_profiles import resolve_asr_plan
from videoflow.application.models import installed_path
from videoflow.application.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument(
        "--profile",
        default="",
        help="auto, fast, balanced, quality, vulkan, or custom",
    )
    parser.add_argument("--model", default="", help="Explicit model id for custom.")
    parser.add_argument("--beam", type=int, default=0)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--language", default="")
    parser.add_argument("--no-words", action="store_true")
    args = parser.parse_args()

    audio = args.audio.expanduser().resolve()
    if not audio.is_file():
        raise SystemExit(f"Audio does not exist: {audio}")
    with wave.open(str(audio), "rb") as handle:
        if handle.getframerate() != 16000:
            raise SystemExit("Audio must be 16 kHz")
        duration = handle.getnframes() / 16000
        sample_rate = handle.getframerate()

    settings = load_settings()
    profile = args.profile or "auto"
    options = SimpleNamespace(
        quality_profile=profile,
        mode="auto",
        model_id=args.model,
        model_size="small",
        device="cpu",
        compute_type="int8",
        beam_size=args.beam,
        cpu_threads=args.threads,
        word_timestamps="off" if args.no_words else "auto",
        vad_filter=None,
        condition_on_previous_text=None,
        base_url=None,
        model="whisper-1",
        api_key_env="VIDEOWFLOW_ASR_API_KEY",
        language=args.language or "pt",
    )
    plan = resolve_asr_plan(settings, options)
    model_path = installed_path(plan.model_id) if plan.model_id else None
    started = time.perf_counter()
    if plan.mode == "whisper_cpp":
        client = WhisperCliAdapter(
            model=model_path,
            language=options.language,
            threads=plan.cpu_threads or None,
            beam_size=plan.beam_size,
            word_timestamps=plan.word_timestamps,
            vulkan=plan.profile == "vulkan",
        )
    else:
        client = FasterWhisperAdapter(
            model=model_path,
            model_size=plan.model_size,
            device=plan.device,
            compute_type=plan.compute_type,
            language=options.language,
            vad_filter=plan.vad_filter,
            beam_size=plan.beam_size,
            threads=plan.cpu_threads or None,
            word_timestamps=plan.word_timestamps,
            condition_on_previous_text=plan.condition_on_previous_text,
        )
    sentences = client.transcribe(audio, sample_rate)
    elapsed = time.perf_counter() - started
    payload = {
        "audio": str(audio),
        "audio_seconds": round(duration, 3),
        "elapsed_seconds": round(elapsed, 3),
        "rtf": round(duration / elapsed, 3) if elapsed else 0.0,
        "profile": plan.profile,
        "mode": plan.mode,
        "model": plan.model_id or plan.model_size,
        "beam_size": plan.beam_size,
        "cpu_threads": plan.cpu_threads,
        "word_timestamps": plan.word_timestamps,
        "vad_filter": plan.vad_filter,
        "sentences": len(sentences),
        "words": sum(len(item.words) for item in sentences),
        "fallback_reason": plan.fallback_reason,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
