"""Generate and mix a voice-over for one completed Short."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.adapters.tts import OpenAITtsAdapter
from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.shorts import slugify
from videoflow.domain.config import TtsConfig
from videoflow.domain.errors import ShortEditError, StateNotReadyError, TtsError
from videoflow.domain.state import ProjectState


def generate_short_voiceover(
    *,
    output: Path,
    index: int,
    result: dict[str, Any],
    text: str,
    config: TtsConfig,
    api_key: str | None = None,
    allow_external_services: bool = False,
    allowed_external_hosts: tuple[str, ...] = (),
) -> dict[str, object]:
    if config.provider != "openai_compatible" or not config.base_url:
        raise TtsError(
            "Configure an OpenAI-compatible TTS provider and base URL first."
        )
    if not text.strip():
        raise ShortEditError("Voice-over text is empty.")
    ensure_external_allowed(
        config.base_url,
        capability="external_tts",
        allow_external_services=allow_external_services,
        allowed_hosts=allowed_external_hosts,
    )
    shorts = result.get("shorts")
    if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
        raise ShortEditError(f"Short index {index} is out of range.")
    entry = shorts[index]
    if not isinstance(entry, dict):
        raise ShortEditError(f"Short index {index} is invalid.")
    raw_source = entry.get("path")
    if not isinstance(raw_source, str) or not Path(raw_source).is_file():
        raise ShortEditError("The Short MP4 is missing.")
    output = output.expanduser().resolve()
    state_path = output / "project_state.json"
    shorts_path = output / "shorts.json"
    try:
        ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        report = json.loads(shorts_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateNotReadyError(
            f"Cannot read the completed Shorts project: {exc}"
        ) from exc
    duration = float(entry.get("duration_sec") or 0.0)
    voice_dir = output / "shorts" / "voiceover"
    voice_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    slug = slugify(str(entry.get("title") or "short"), index + 1)
    audio_path = voice_dir / f"{slug}-{stamp}.mp3"
    OpenAITtsAdapter(
        base_url=config.base_url,
        model=config.model,
        voice=config.voice,
        api_key=api_key,
    ).synthesize(
        text,
        audio_path,
        speed=config.speed,
    )
    mixed_path = voice_dir / f"{slug}-{stamp}.mp4"
    FFmpegAdapter().mix_voiceover(
        Path(raw_source),
        audio_path,
        mixed_path,
        duration_sec=duration,
        voice_volume=config.volume,
        original_volume=config.original_volume,
    )
    previous = entry.get("path")
    payload = {
        "text": text,
        "audio_path": str(audio_path),
        "path": str(mixed_path),
        "provider": config.provider,
        "model": config.model,
        "voice": config.voice,
        "volume": config.volume,
        "original_volume": config.original_volume,
    }
    entry["voiceover"] = payload
    entry["path"] = str(mixed_path)
    if previous is not None:
        entry["previous_path"] = previous
    clips = report.get("clips")
    if isinstance(clips, list) and 0 <= index < len(clips):
        clips[index] = entry
    shorts_path.write_text(
        json.dumps(
            {"ok": True, "clips": clips if isinstance(clips, list) else shorts},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return payload
