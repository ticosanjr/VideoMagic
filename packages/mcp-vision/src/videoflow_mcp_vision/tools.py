"""VideoFlow 2.90 vision tools: captions, mattes, upscale, motion, and B-roll."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import commands, storage
from .errors import (
    InputNotFoundError,
    InvalidArgumentError,
    MissingCommandError,
    OutputNotProducedError,
    RemoteResultError,
)
from .router import RouterBridge

ROUTER = RouterBridge()
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MOTIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right"}


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

    binary = commands.resolve_binary(
        "whisper-cli",
        "whisper-cpp",
        "whisper",
        env="VF_WHISPER_BIN",
    )
    backend: str
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
            details={"env": ["VF_WHISPER_BIN", "VF_WHISPER_MODEL"], "capability": "asr"},
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


def remove_background(
    project_id: str,
    input_path: str,
    is_video: bool = False,
) -> dict[str, Any]:
    """Remove an image or video background with rembg."""

    tool = "remove_background"
    source = _ensure_input(input_path, "input_path")
    if not is_video and source.suffix.lower() in VIDEO_EXTENSIONS:
        is_video = True
    key = storage.cache_key(tool, storage.file_fingerprint(source), bool(is_video))
    if is_video:
        relative = f"assets/matte/{source.stem}_alpha.webm"
    else:
        relative = f"assets/matte/{source.stem}_alpha.png"

    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    if is_video:
        _matte_video(source, target)
    else:
        _run_rembg(source, target)

    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind=("broll" if is_video else "images"),
        license="source",
        source="local:rembg",
        cache_key=key,
        metadata={"is_video": bool(is_video), "input": str(source)},
    )
    return _payload(tool, project_id, record, mode="local")


def upscale_media(
    project_id: str,
    input_path: str,
    scale: int = 2,
) -> dict[str, Any]:
    """Upscale with remote compute, Real-ESRGAN, or an FFmpeg lanczos fallback."""

    tool = "upscale_media"
    source = _ensure_input(input_path, "input_path")
    try:
        factor = int(scale)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "scale must be an integer",
            details={"argument": "scale", "value": scale},
        ) from exc
    if not 1 <= factor <= 8:
        raise InvalidArgumentError(
            "scale must be between 1 and 8",
            details={"argument": "scale", "value": scale},
        )

    is_video = source.suffix.lower() in VIDEO_EXTENSIONS
    if is_video:
        relative = f"assets/upscaled/{source.stem}_x{factor}.mp4"
    else:
        suffix = source.suffix.lower() if source.suffix else ".png"
        relative = f"assets/upscaled/{source.stem}_x{factor}{suffix}"

    key = storage.cache_key(tool, storage.file_fingerprint(source), factor)
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    if ROUTER.health("upscale"):
        result = ROUTER.submit(
            "upscale",
            {"input": str(source), "scale": factor, "is_video": is_video},
        )
        record = _materialize_remote(
            project_id=project_id,
            relative_path=relative,
            result=result,
            capability="upscale",
            cache_key=key,
            kind=("broll" if is_video else "images"),
        )
        return _payload(tool, project_id, record, mode="remote", fallback=False)

    template = os.environ.get("VF_REALESRGAN_CMD")
    if template:
        commands.run(
            commands.expand_template(
                template,
                {"input": str(source), "output": str(target), "scale": str(factor)},
                name="Real-ESRGAN command",
            )
        )
        fallback = False
        source_name = "local:realesrgan-cmd"
    elif shutil.which("realesrgan-ncnn-vulkan"):
        commands.run(
            [
                shutil.which("realesrgan-ncnn-vulkan") or "realesrgan-ncnn-vulkan",
                "-i",
                str(source),
                "-o",
                str(target),
                "-s",
                str(factor),
            ]
        )
        fallback = False
        source_name = "local:realesrgan-ncnn-vulkan"
    else:
        ffmpeg = _ffmpeg()
        filter_chain = f"scale=iw*{factor}:ih*{factor}:flags=lanczos"
        argv = [ffmpeg, "-y", "-i", str(source), "-vf", filter_chain]
        if is_video:
            argv.extend(
                ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
            )
        else:
            argv.extend(["-frames:v", "1"])
        argv.append(str(target))
        commands.run(argv)
        fallback = True
        source_name = "ffmpeg:lanczos"

    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind=("broll" if is_video else "images"),
        license="source",
        source=source_name,
        cache_key=key,
        metadata={"scale": factor, "fallback": fallback, "is_video": is_video},
    )
    return _payload(tool, project_id, record, mode="local", fallback=fallback)


def render_motion_graphic(
    project_id: str,
    engine: str = "remotion",
    template_or_code: str = "",
    props_json: str = "{}",
    duration_sec: float = 5.0,
) -> dict[str, Any]:
    """Render a Remotion or Manim graphic through a configured command template."""

    tool = "render_motion_graphic"
    selected = str(engine or "").strip().lower()
    if selected not in {"remotion", "manim"}:
        raise InvalidArgumentError(
            "engine must be 'remotion' or 'manim'",
            details={"argument": "engine", "value": engine},
        )
    if not isinstance(template_or_code, str) or not template_or_code.strip():
        raise InvalidArgumentError(
            "template_or_code must not be empty",
            details={"argument": "template_or_code"},
        )
    try:
        duration = float(duration_sec)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "duration_sec must be a number",
            details={"argument": "duration_sec", "value": duration_sec},
        ) from exc
    if not 0.1 <= duration <= 600.0:
        raise InvalidArgumentError(
            "duration_sec must be between 0.1 and 600",
            details={"argument": "duration_sec", "value": duration_sec},
        )
    props = _parse_props(props_json)

    env_key = "VF_REMOTION_CMD" if selected == "remotion" else "VF_MANIM_CMD"
    template = os.environ.get(env_key)
    if not template:
        raise MissingCommandError(
            f"set {env_key} to render {selected} graphics",
            details={"env": [env_key], "engine": selected},
        )

    key = storage.cache_key(tool, selected, template_or_code, props, duration)
    slug = _slug(Path(template_or_code).stem or selected)
    relative = f"assets/graphics/{slug}_{key[:8]}.mp4"
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vf-motion-") as raw:
        workdir = Path(raw)
        props_file = workdir / "props.json"
        props_file.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
        argv = commands.expand_template(
            template,
            {
                "entry": template_or_code,
                "code": template_or_code,
                "props": str(props_file),
                "output": str(target),
                "duration": f"{duration:.3f}",
                "engine": selected,
            },
            name=env_key,
        )
        commands.run(argv, cwd=workdir)

    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="graphics",
        license="generated",
        source=f"local:{selected}",
        cache_key=key,
        metadata={
            "engine": selected,
            "duration_sec": duration,
            "props": props,
            "entry": template_or_code,
        },
    )
    return _payload(tool, project_id, record, mode="local")


def image_to_broll_motion(
    project_id: str,
    image_path: str,
    duration_sec: float = 4.0,
    motion: str = "zoom_in",
) -> dict[str, Any]:
    """Animate a still image into a zoom or pan B-roll clip with FFmpeg."""

    tool = "image_to_broll_motion"
    source = _ensure_input(image_path, "image_path")
    try:
        duration = float(duration_sec)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "duration_sec must be a number",
            details={"argument": "duration_sec", "value": duration_sec},
        ) from exc
    if not 0.1 <= duration <= 120.0:
        raise InvalidArgumentError(
            "duration_sec must be between 0.1 and 120",
            details={"argument": "duration_sec", "value": duration_sec},
        )
    if motion not in MOTIONS:
        raise InvalidArgumentError(
            f"motion must be one of: {', '.join(sorted(MOTIONS))}",
            details={"argument": "motion", "value": motion},
        )

    key = storage.cache_key(tool, storage.file_fingerprint(source), duration, motion)
    relative = f"assets/broll/{source.stem}_{motion}.mp4"
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    width, height = _broll_size()
    ffmpeg = _ffmpeg()
    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    filter_chain = build_broll_filter(
        motion=motion,
        duration=duration,
        width=width,
        height=height,
    )
    commands.run(
        [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-vf",
            filter_chain,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ]
    )
    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="broll",
        license="source",
        source="ffmpeg:broll",
        cache_key=key,
        metadata={
            "motion": motion,
            "duration_sec": duration,
            "width": width,
            "height": height,
            "input": str(source),
        },
    )
    return _payload(tool, project_id, record, mode="local")


def build_broll_filter(
    *,
    motion: str,
    duration: float,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> str:
    """Build the FFmpeg zoompan chain used for still-image B-roll."""

    if motion not in MOTIONS:
        raise InvalidArgumentError(
            f"motion must be one of: {', '.join(sorted(MOTIONS))}",
            details={"argument": "motion", "value": motion},
        )
    frames = max(1, int(round(duration * fps)))
    pre = (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2}"
    )
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    if motion == "zoom_in":
        zoom, x_expr, y_expr = "min(zoom+0.0020,1.25)", center_x, center_y
    elif motion == "zoom_out":
        zoom, x_expr, y_expr = "if(eq(on,1),1.25,max(zoom-0.0020,1.0))", center_x, center_y
    elif motion == "pan_left":
        zoom, x_expr, y_expr = "1.15", f"(iw-iw/zoom)*(1-on/{frames})", center_y
    else:
        zoom, x_expr, y_expr = "1.15", f"(iw-iw/zoom)*on/{frames}", center_y
    zoompan = f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps}"
    return f"{pre},{zoompan},format=yuv420p"


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


def _matte_video(source: Path, target: Path) -> None:
    ffmpeg = _ffmpeg()
    fps = os.environ.get("VF_MATTE_FPS", "30")
    _validate_fps(fps)
    with tempfile.TemporaryDirectory(prefix="vf-matte-") as raw:
        workdir = Path(raw)
        frames = workdir / "frames"
        mattes = workdir / "matte"
        frames.mkdir()
        mattes.mkdir()
        commands.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-vf",
                f"fps={fps}",
                str(frames / "%06d.png"),
            ]
        )
        extracted = sorted(frames.glob("*.png"))
        if not extracted:
            raise OutputNotProducedError(
                "FFmpeg extracted no frames for background removal",
                details={"input": str(source)},
            )
        for index, frame in enumerate(extracted, start=1):
            _run_rembg(frame, mattes / f"{index:06d}.png")
        commands.run(
            [
                ffmpeg,
                "-y",
                "-framerate",
                fps,
                "-i",
                str(mattes / "%06d.png"),
                "-c:v",
                "libvpx-vp9",
                "-pix_fmt",
                "yuva420p",
                "-b:v",
                "0",
                "-crf",
                "30",
                str(target),
            ]
        )


def _run_rembg(source: Path, target: Path) -> None:
    template = os.environ.get("VF_REMBG_CMD")
    if template:
        commands.run(
            commands.expand_template(
                template,
                {"input": str(source), "output": str(target)},
                name="rembg command",
            )
        )
        return
    binary = shutil.which("rembg")
    if binary:
        commands.run([binary, "i", str(source), str(target)])
        return
    if importlib.util.find_spec("rembg") is not None:
        commands.run([sys.executable, "-m", "rembg", "i", str(source), str(target)])
        return
    raise MissingCommandError(
        "rembg is not installed; set VF_REMBG_CMD or install rembg",
        details={"env": ["VF_REMBG_CMD"], "capability": "matte"},
    )


def _materialize_remote(
    *,
    project_id: str,
    relative_path: str,
    result: Any,
    capability: str,
    cache_key: str,
    kind: str,
) -> storage.AssetRecord:
    metadata: dict[str, Any] = {"capability": capability, "mode": "remote"}
    if isinstance(result, dict) and isinstance(result.get("metadata"), dict):
        metadata.update(result["metadata"])

    data: bytes | None = None
    if isinstance(result, dict) and result.get("data") is not None:
        raw = result["data"]
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    elif isinstance(result, (bytes, bytearray)):
        data = bytes(result)

    if data is not None:
        return storage.write_output(
            project_id,
            relative_path,
            data=data,
            kind=kind,
            license="generated",
            source=f"remote:{capability}",
            cache_key=cache_key,
            metadata=metadata,
            ai_generated=True,
        )

    source = _path_from_value(result)
    if source is None or not source.is_file():
        raise RemoteResultError(
            f"remote {capability!r} result has no readable file",
            details={"capability": capability, "result_type": type(result).__name__},
        )
    return storage.write_output(
        project_id,
        relative_path,
        source_path=source,
        kind=kind,
        license="generated",
        source=f"remote:{capability}",
        cache_key=cache_key,
        metadata=metadata,
        ai_generated=True,
    )


def _path_from_value(value: Any) -> Path | None:
    if isinstance(value, (str, Path)):
        return Path(str(value)).expanduser()
    if isinstance(value, dict):
        for key in ("path", "output", "asset_path", "file"):
            if value.get(key):
                return Path(str(value[key])).expanduser()
        return None
    for attribute in ("path", "output", "file"):
        raw = getattr(value, attribute, None)
        if raw:
            return Path(str(raw)).expanduser()
    return None


def _parse_props(props_json: Any) -> dict[str, Any]:
    if isinstance(props_json, dict):
        return dict(props_json)
    if props_json is None or props_json == "":
        return {}
    if not isinstance(props_json, str):
        raise InvalidArgumentError(
            "props_json must be a JSON object string",
            details={"argument": "props_json"},
        )
    try:
        parsed = json.loads(props_json)
    except json.JSONDecodeError as exc:
        raise InvalidArgumentError(
            f"props_json is not valid JSON: {exc.msg}",
            details={"argument": "props_json", "line": exc.lineno, "column": exc.colno},
        ) from exc
    if not isinstance(parsed, dict):
        raise InvalidArgumentError(
            "props_json must decode to an object",
            details={"argument": "props_json"},
        )
    return parsed


def _broll_size() -> tuple[int, int]:
    raw = os.environ.get("VF_BROLL_SIZE", "1080x1920")
    try:
        width_text, height_text = raw.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            f"VF_BROLL_SIZE must look like WIDTHxHEIGHT, got {raw!r}",
            details={"env": "VF_BROLL_SIZE", "value": raw},
        ) from exc
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise InvalidArgumentError(
            f"VF_BROLL_SIZE must use positive even dimensions, got {raw!r}",
            details={"env": "VF_BROLL_SIZE", "value": raw},
        )
    return width, height


def _validate_fps(value: str) -> None:
    try:
        fps = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            f"VF_MATTE_FPS must be a number, got {value!r}",
            details={"env": "VF_MATTE_FPS", "value": value},
        ) from exc
    if not 1.0 <= fps <= 240.0:
        raise InvalidArgumentError(
            f"VF_MATTE_FPS must be between 1 and 240, got {value!r}",
            details={"env": "VF_MATTE_FPS", "value": value},
        )


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


def _payload(
    tool: str,
    project_id: str,
    record: storage.AssetRecord,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "output": str(record.path),
        "relative_path": record.relative_path,
        "cache_key": record.cache_key,
        "cached": record.cached,
        "sidecar": str(record.sidecar),
        "license": record.license,
        "source": record.source,
        "sha256": record.sha256,
    }
    payload.update(extra)
    return payload


def _assets_payload(
    tool: str,
    project_id: str,
    records: Sequence[storage.AssetRecord],
    *,
    mode: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "mode": mode,
        "cached": all(record.cached for record in records),
        "assets": [_payload(tool, project_id, record, mode=mode) for record in records],
    }


def _ensure_input(value: str | Path | None, argument: str) -> Path:
    if value is None or str(value) == "":
        raise InvalidArgumentError(f"{argument} is required", details={"argument": argument})
    resolved = Path(value).expanduser()
    if not resolved.is_file():
        raise InputNotFoundError(
            f"{argument} not found: {resolved}",
            details={"argument": argument, "path": str(resolved)},
        )
    return resolved


def _require_output(path: Path) -> None:
    if not path.is_file():
        raise OutputNotProducedError(
            f"command did not produce {path}",
            details={"path": str(path)},
        )


def _ffmpeg() -> str:
    configured = os.environ.get("VF_FFMPEG")
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise MissingCommandError(
        "ffmpeg is required for this tool; install it or set VF_FFMPEG",
        details={"env": ["VF_FFMPEG"], "executable": "ffmpeg"},
    )


def _slug(value: str, *, limit: int = 40) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value.lower())
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return (collapsed or "asset")[:limit]
