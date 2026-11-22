"""Word-aligned captions, SRT and ASS rendering."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import commands, common, storage
from .common import _assets_payload, _ensure_input, _path_from_value
from .errors import (
    InvalidArgumentError,
    MissingCommandError,
    OutputNotProducedError,
    RemoteResultError,
)


def transcribe_word_aligned(
    project_id: str,
    audio_path: str,
    language: str = "pt",
    style: str = "shorts_karaoke",
) -> dict[str, Any]:
    """Transcribe audio to word-aligned captions in JSON, SRT, and ASS."""

    tool = "transcribe_word_aligned"
    source = _ensure_input(audio_path, "audio_path")
    if not language or not str(language).strip():
        raise InvalidArgumentError("language must not be empty", details={"argument": "language"})
    if not style or not str(style).strip():
        raise InvalidArgumentError("style must not be empty", details={"argument": "style"})

    model_marker = os.environ.get("VF_WHISPER_MODEL") or os.environ.get("VF_STABLE_TS_MODEL")
    key = storage.cache_key(
        tool,
        storage.file_fingerprint(source),
        language,
        style,
        model_marker or "",
    )
    transcript_relative = "captions/transcript.json"
    caption_relatives = ("captions.srt", "captions.ass")
    cached_transcript = storage.cached_asset(project_id, transcript_relative, key)
    cached_captions = [
        storage.cached_asset(project_id, relative, key) for relative in caption_relatives
    ]
    if cached_transcript is not None and all(cached_captions):
        records = [cached_transcript, *[record for record in cached_captions if record]]
        payload = _assets_payload(tool, project_id, records, mode="cache")
        payload["transcript"] = str(cached_transcript.path)
        payload["language"] = language
        payload["style"] = style
        return payload

    segments: list[dict[str, Any]] | None = None
    backend = ""
    if common.ROUTER.health("asr"):
        try:
            segments = _transcribe_remote(source, language)
            backend = "remote:asr"
        except Exception:  # noqa: BLE001 - the local fallback is the contract
            segments = None

    if segments is None:
        binary = commands.resolve_binary(
            "whisper-cli",
            "whisper-cpp",
            "whisper",
            env="VF_WHISPER_BIN",
        )
        if binary:
            segments = _transcribe_with_whisper(binary, source, language)
            backend = "local:whisper.cpp"
        elif _stable_whisper_available():
            segments = _transcribe_with_stable_whisper(source, language)
            backend = "local:stable-ts"
        else:
            raise MissingCommandError(
                "whisper.cpp was not found and stable-ts is not installed; "
                "set VF_WHISPER_BIN or install stable-ts",
                details={
                    "env": ["VF_WHISPER_BIN", "VF_WHISPER_MODEL"],
                    "capability": "asr",
                },
            )

    transcript = {
        "version": 1,
        "language": language,
        "style": style,
        "backend": backend,
        "segments": segments,
    }
    records = [
        storage.write_output(
            project_id,
            transcript_relative,
            data=(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            kind="captions",
            license="source",
            source=backend,
            cache_key=key,
            metadata={"language": language, "style": style, "segments": len(segments)},
        ),
        storage.write_output(
            project_id,
            "captions.srt",
            data=segments_to_srt(segments).encode("utf-8"),
            kind="captions",
            license="source",
            source=backend,
            cache_key=key,
            metadata={"language": language, "style": style, "format": "srt"},
        ),
        storage.write_output(
            project_id,
            "captions.ass",
            data=segments_to_ass(segments, style=style).encode("utf-8"),
            kind="captions",
            license="source",
            source=backend,
            cache_key=key,
            metadata={"language": language, "style": style, "format": "ass"},
        ),
    ]
    payload = _assets_payload(tool, project_id, records, mode="local")
    payload["transcript"] = str(records[0].path)
    payload["language"] = language
    payload["style"] = style
    payload["segments"] = len(segments)
    return payload


def segments_to_srt(segments: Sequence[dict[str, Any]]) -> str:
    """Render normalized segments as SubRip."""

    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        start = _srt_time(float(segment.get("start", 0.0)))
        end = _srt_time(float(segment.get("end", segment.get("start", 0.0))))
        text = str(segment.get("text", "")).strip() or " "
        blocks.append(f"{index}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks)


def segments_to_ass(
    segments: Sequence[dict[str, Any]],
    *,
    style: str = "shorts_karaoke",
) -> str:
    """Render normalized segments as an ASS subtitle file."""

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Karaoke,Arial,72,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,4,2,2,60,60,180,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines: list[str] = []
    for segment in segments:
        start = _ass_time(float(segment.get("start", 0.0)))
        end = _ass_time(float(segment.get("end", segment.get("start", 0.0))))
        text = _ass_escape(str(segment.get("text", "")))
        lines.append(f"Dialogue: 0,{start},{end},Karaoke,,0,0,0,,{text}")
    return header + "\n".join(lines) + ("\n" if lines else "")


def _transcribe_with_whisper(binary: str, audio: Path, language: str) -> list[dict[str, Any]]:
    model = os.environ.get("VF_WHISPER_MODEL")
    if not model:
        raise MissingCommandError(
            "VF_WHISPER_MODEL must point at a whisper.cpp model",
            details={"env": ["VF_WHISPER_MODEL"], "capability": "asr"},
        )
    model_path = _ensure_input(model, "VF_WHISPER_MODEL")
    with tempfile.TemporaryDirectory(prefix="vf-whisper-") as raw:
        output_base = Path(raw) / "transcript"
        commands.run(
            [
                binary,
                "-m",
                str(model_path),
                "-f",
                str(audio),
                "-l",
                language,
                "-oj",
                "-of",
                str(output_base),
                "-np",
            ]
        )
        candidates = [Path(f"{output_base}.json"), output_base.with_suffix(".json")]
        json_path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if json_path is None:
            raise OutputNotProducedError(
                "whisper.cpp did not produce its JSON transcript",
                details={"output_base": str(output_base)},
            )
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    return _parse_transcript_payload(payload)


def _transcribe_with_stable_whisper(audio: Path, language: str) -> list[dict[str, Any]]:
    import stable_whisper

    model_name = os.environ.get("VF_STABLE_TS_MODEL", "base")
    model = stable_whisper.load_model(model_name)
    result = model.transcribe(str(audio), language=language, word_timestamps=True)
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    return _parse_transcript_payload(payload)


def _stable_whisper_available() -> bool:
    return importlib.util.find_spec("stable_whisper") is not None


def _transcribe_remote(source: Path, language: str) -> list[dict[str, Any]]:
    """Run ASR on the GPU worker and parse its JSON artifact."""

    result = common.ROUTER.submit(
        "asr",
        {
            "input": str(source),
            "language": language,
            "model": os.environ.get("VF_WHISPER_MODEL", "large-v3"),
            "output_name": "transcript.json",
        },
    )
    text = ""
    if isinstance(result, dict) and result.get("data") is not None:
        raw = result["data"]
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    else:
        path = _path_from_value(result)
        if path is not None and path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise RemoteResultError(
            "remote asr returned no transcript payload",
            details={"capability": "asr"},
        )
    segments = _parse_transcript_payload(json.loads(text))
    if not segments:
        raise RemoteResultError(
            "remote asr returned an empty transcript",
            details={"capability": "asr"},
        )
    return segments


def _parse_transcript_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw_segments = payload.get("transcription")
    if raw_segments is None:
        raw_segments = payload.get("segments")
    segments: list[dict[str, Any]] = []
    for item in raw_segments or []:
        if not isinstance(item, dict):
            continue
        start, end = _segment_bounds(item)
        words: list[dict[str, Any]] = []
        for key in ("words", "tokens"):
            for token in item.get(key) or []:
                if not isinstance(token, dict):
                    continue
                word = str(token.get("word") or token.get("text") or "").strip()
                if not word:
                    continue
                word_start, word_end = _segment_bounds(token)
                words.append({"word": word, "start": word_start, "end": word_end})
            if words:
                break
        segments.append(
            {
                "start": start,
                "end": end,
                "text": str(item.get("text", "")).strip(),
                "words": words,
            }
        )
    return segments


def _segment_bounds(item: dict[str, Any]) -> tuple[float, float]:
    offsets = item.get("offsets")
    if isinstance(offsets, dict):
        start = float(offsets.get("from", 0.0)) / 1000.0
        end = float(offsets.get("to", offsets.get("from", 0.0))) / 1000.0
        return start, end
    return float(item.get("start", 0.0)), float(item.get("end", item.get("start", 0.0)))


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def _srt_time(seconds: float) -> str:
    total = max(0, int(round(seconds * 1000.0)))
    milliseconds = total % 1000
    total //= 1000
    minute_total, second = divmod(total, 60)
    hour, minute = divmod(minute_total, 60)
    return f"{hour:02d}:{minute:02d}:{second:02d},{milliseconds:03d}"


def _ass_time(seconds: float) -> str:
    total = max(0, int(round(seconds * 100.0)))
    centiseconds = total % 100
    total //= 100
    minute_total, second = divmod(total, 60)
    hour, minute = divmod(minute_total, 60)
    return f"{hour}:{minute:02d}:{second:02d}.{centiseconds:02d}"
