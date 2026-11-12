"""Narration synthesis for source-less, script-first recipes."""

from __future__ import annotations

import contextlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

from videoflow.adapters.tts import OpenAITtsAdapter, PiperTtsAdapter
from videoflow.application import voice_clone
from videoflow.application.providers import resolve_chain
from videoflow.application.secrets import get_secret
from videoflow.application.settings import load_settings
from videoflow.domain.errors import TtsError
from videoflow.runtime import find_binary


def _provider_chain(provider_id: str = "") -> list[dict[str, object]]:
    chain = resolve_chain("tts")
    if provider_id:
        selected = [item for item in chain if str(item.get("id")) == provider_id]
        if selected:
            return selected + [item for item in chain if item not in selected]
    return chain


def _synth_part(
    text: str,
    target: Path,
    *,
    provider_id: str,
    speed: float,
) -> str:
    payload = text.strip()
    if not payload:
        raise TtsError("Narration text is empty.")
    tts = load_settings().tts
    for provider in _provider_chain(provider_id):
        kind = str(provider.get("kind") or "openai_compatible")
        if kind == "openai_compatible":
            base_url = str(provider.get("base_url") or "")
            if not base_url:
                continue
            OpenAITtsAdapter(
                base_url=base_url,
                model=str(provider.get("model") or tts.model or "tts-1"),
                voice=str(provider.get("voice") or tts.voice or "alloy"),
                api_key=get_secret(str(provider.get("api_key_env") or "")),
            ).synthesize(payload, target, speed=speed)
            return str(provider.get("id") or kind)
        if kind == "piper":
            PiperTtsAdapter(
                binary=str(provider.get("binary") or "piper"),
                model_path=str(provider.get("model_path") or ""),
            ).synthesize(payload, target, speed=speed)
            return str(provider.get("id") or kind)
    if tts.provider == "piper":
        PiperTtsAdapter(
            binary=str(
                provider.get("binary") if provider_id else ""
            )
            or "piper",
            model_path=str(
                provider.get("model_path") if provider_id else ""
            )
            or "",
        ).synthesize(payload, target, speed=speed)
        return "piper"
    raise TtsError(
        "No usable TTS provider is configured. Add one in Setup → AI providers."
    )


def _concat_parts(parts: list[Path], target: Path, sample_rate: int) -> Path:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise TtsError("FFmpeg is required to assemble the narration.")
    target.parent.mkdir(parents=True, exist_ok=True)
    list_path = target.with_suffix(".concat.txt")
    lines = []
    for part in parts:
        escaped = str(part).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    with contextlib.suppress(OSError):
        list_path.unlink()
    if completed.returncode != 0:
        raise TtsError(
            "Could not concatenate narration parts: "
            + (completed.stderr.strip() or f"exit {completed.returncode}")
        )
    return target


def _normalize(source: Path, target: Path, sample_rate: int) -> Path:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise TtsError("FFmpeg is required to normalize the narration.")
    temporary = target.with_name(f".{target.stem}.norm.wav") if source == target else target
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(temporary),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise TtsError(
            "Could not normalize the narration: "
            + (completed.stderr.strip() or f"exit {completed.returncode}")
        )
    if temporary != target:
        temporary.replace(target)
    return target


def probe_duration(path: Path) -> float:
    binary = find_binary("ffprobe")
    if binary is None:
        return 0.0
    completed = subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return max(0.0, float(completed.stdout.strip()))
    except ValueError:
        return 0.0


def synthesize_narration(
    texts: list[str],
    directory: Path,
    *,
    provider_id: str = "",
    profile_id: str = "",
    speed: float = 1.0,
    sample_rate: int = 48000,
) -> dict[str, Any]:
    """Synthesize one part per script section and return a normalized WAV."""

    clean = [text.strip() for text in texts if text.strip()]
    if not clean:
        raise TtsError("The script has no narration text.")
    directory = Path(directory)
    parts_dir = directory / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    provider = ""
    for index, text in enumerate(clean, start=1):
        target = parts_dir / f"part-{index:03d}.mp3"
        if profile_id:
            try:
                audio = voice_clone.synthesize(
                    voice_clone.VoiceSynthesizeRequest(
                        profile_id=profile_id, text=text
                    )
                )
                target.write_bytes(audio)
                provider = "voice_clone"
            except Exception as exc:  # noqa: BLE001 - provider fallback
                if isinstance(exc, TtsError):
                    raise
                provider = _synth_part(
                    text, target, provider_id=provider_id, speed=speed
                )
        else:
            provider = _synth_part(
                text, target, provider_id=provider_id, speed=speed
            )
        parts.append(target)
    joined = directory / "narration-joined.wav"
    _concat_parts(parts, joined, sample_rate)
    target = directory / "narration.wav"
    _normalize(joined, target, sample_rate)
    with contextlib.suppress(OSError):
        joined.unlink()
    return {
        "path": str(target),
        "provider": provider,
        "parts": [str(part) for part in parts],
        "duration_sec": round(probe_duration(target), 3),
        "sections": len(clean),
        "profile_id": profile_id,
    }


def copy_narration(source: Path, target: Path, sample_rate: int = 48000) -> dict[str, Any]:
    """Use an operator-provided narration file as the generated track."""

    source = Path(source).expanduser()
    if not source.is_file():
        raise TtsError(f"Narration file not found: {source}")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        if source.suffix.lower() == ".wav":
            shutil.copy2(source, target)
        else:
            _normalize(source, target, sample_rate)
    return {
        "path": str(target),
        "provider": "human",
        "parts": [str(source)],
        "duration_sec": round(probe_duration(target), 3),
        "sections": 1,
        "profile_id": "",
    }
