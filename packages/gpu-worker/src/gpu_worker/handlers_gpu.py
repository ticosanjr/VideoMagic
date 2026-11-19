"""Built-in Python GPU handlers for ASR, NVENC, matte, and face tracking.

These handlers are opt-in through ``VF_GPU_BUILTIN_HANDLERS=1``. Optional
dependencies are checked at startup; when one is missing the capability is
marked unavailable with an actionable reason instead of failing at job time.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gpu_worker.handlers import Handler, HandlerError, HandlerRegistry

if TYPE_CHECKING:
    from gpu_worker.settings import Settings

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_ASR_MODELS: dict[tuple[str, str, str], Any] = {}
_ASR_LOCK = threading.RLock()
_NVENC_CACHE: dict[str, bool] = {}


def _available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _ffmpeg(settings: Settings) -> str:
    return settings.ffmpeg_cmd or os.environ.get("VF_GPU_FFMPEG") or "ffmpeg"


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _run(tokens: list[str], *, timeout: float = 3600.0) -> None:
    try:
        completed = subprocess.run(
            tokens,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise HandlerError(f"command not found: {tokens[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HandlerError(f"command timed out after {timeout:.0f}s") from exc
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise HandlerError(
            f"command exited with status {completed.returncode}: "
            f"{tail[-1][:300] if tail else 'no stderr'}"
        )


def nvenc_available(ffmpeg: str = "ffmpeg") -> bool:
    """Return whether FFmpeg exposes ``h264_nvenc``."""

    key = str(ffmpeg)
    cached = _NVENC_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        _NVENC_CACHE[key] = False
        return False
    available = completed.returncode == 0 and "h264_nvenc" in completed.stdout
    _NVENC_CACHE[key] = available
    return available


def make_asr_handler(
    settings: Settings,
    registry: HandlerRegistry | None = None,
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
                )
                _ASR_MODELS[key] = model

                def unload() -> None:
                    _ASR_MODELS.pop(key, None)

                if registry is not None:
                    registry.register(
                        model_key,
                        capability="asr",
                        unload=unload,
                        vram_mb=3277,
                        metadata={"model": model_name, "device": device},
                    )
            elif registry is not None:
                registry.touch(model_key)
        language = str(params.get("language") or "pt")
        beam_size = int(params.get("beam_size") or 5)
        word_timestamps = bool(params.get("word_timestamps", True))
        try:
            segments, info = model.transcribe(
                str(input_paths[0]),
                language=language,
                beam_size=beam_size,
                word_timestamps=word_timestamps,
                vad_filter=bool(params.get("vad_filter", True)),
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
            for segment in segments:
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
        target = work_dir / "transcript.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return [target]

    return handler


def make_render_nvenc_handler(settings: Settings) -> Handler:
    """Encode one assembled video with NVENC, optionally burning ASS subtitles."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("render_nvenc requires a base video artifact")
        ffmpeg = _ffmpeg(settings)
        if not nvenc_available(ffmpeg):
            raise HandlerError("FFmpeg does not expose h264_nvenc")
        base = input_paths[0]
        ass_path = Path(str(params.get("ass_path") or "")).expanduser()
        if not ass_path.is_file():
            ass_path = next(
                (path for path in input_paths[1:] if path.suffix.casefold() == ".ass"),
                Path(),
            )
        output = work_dir / str(params.get("output_name") or "render.mp4")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(base)]
        filters: list[str] = []
        width = int(params.get("width") or 0)
        height = int(params.get("height") or 0)
        fps = int(params.get("fps") or 0)
        if width and height:
            filters.append(
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
            )
        if fps:
            filters.append(f"fps={fps}")
        if ass_path.is_file():
            filters.append(f"ass='{_escape_filter_path(ass_path)}'")
        if filters:
            command.extend(["-vf", ",".join(filters)])
        command.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "h264_nvenc",
                "-preset",
                str(params.get("preset") or "p4"),
                "-tune",
                str(params.get("tune") or "hq"),
                "-rc",
                "vbr",
                "-cq",
                str(int(params.get("cq") or 20)),
                "-b:v",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                str(params.get("audio_bitrate") or "192k"),
                "-movflags",
                "+faststart",
            ]
        )
        if params.get("duration"):
            command.extend(["-t", f"{float(params['duration']):.3f}"])
        command.append(str(output))
        _run(command)
        if not output.is_file():
            raise HandlerError("render_nvenc did not create the output video")
        return [output]

    return handler


def make_segment_matte_handler(settings: Settings) -> Handler:
    """Remove the background from an image or a short video clip."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("segment_matte requires an input artifact")
        try:
            from rembg import new_session, remove
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise HandlerError(f"rembg is not installed: {exc}") from exc
        session = new_session(str(params.get("model") or "u2net"))
        source = input_paths[0]
        if source.suffix.casefold() in IMAGE_SUFFIXES:
            target = work_dir / "matte.png"
            target.write_bytes(remove(source.read_bytes(), session=session))
            return [target]
        ffmpeg = _ffmpeg(settings)
        fps = int(params.get("fps") or 30)
        with tempfile.TemporaryDirectory(prefix="vf-matte-", dir=work_dir) as raw:
            frames_dir = Path(raw) / "frames"
            matte_dir = Path(raw) / "matte"
            frames_dir.mkdir()
            matte_dir.mkdir()
            _run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-vf",
                    f"fps={fps}",
                    str(frames_dir / "%06d.png"),
                ]
            )
            frames = sorted(frames_dir.glob("*.png"))
            if not frames:
                raise HandlerError("segment_matte extracted no frames")
            for index, frame in enumerate(frames, start=1):
                (matte_dir / f"{index:06d}.png").write_bytes(
                    remove(frame.read_bytes(), session=session)
                )
            target = work_dir / "matte.webm"
            _run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-framerate",
                    str(fps),
                    "-i",
                    str(matte_dir / "%06d.png"),
                    "-c:v",
                    "libvpx-vp9",
                    "-pix_fmt",
                    "yuva420p",
                    "-b:v",
                    "0",
                    "-crf",
                    "24",
                    str(target),
                ]
            )
        if not target.is_file():
            raise HandlerError("segment_matte did not create the output")
        return [target]

    return handler


def make_face_track_handler(settings: Settings) -> Handler:
    """Track the largest face with OpenCV and write normalized keyframes."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("face_track requires an input video artifact")
        try:
            import cv2
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise HandlerError(f"OpenCV is not installed: {exc}") from exc
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(str(cascade_path))
        if cascade.empty():
            raise HandlerError("OpenCV face cascade is unavailable")
        capture = cv2.VideoCapture(str(input_paths[0]))
        if not capture.isOpened():
            raise HandlerError(f"cannot open video: {input_paths[0]}")
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
        sample = max(1, round(fps / max(1.0, float(params.get("fps") or 5.0))))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        keyframes: list[dict[str, Any]] = []
        index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if index % sample:
                    index += 1
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
                if len(faces):
                    x, y, w, h = max(faces, key=lambda item: int(item[2]) * int(item[3]))
                    keyframes.append(
                        {
                            "frame": index,
                            "time": round(index / fps, 4),
                            "bbox": [
                                round(float(x) / max(1, width), 6),
                                round(float(y) / max(1, height), 6),
                                round(float(w) / max(1, width), 6),
                                round(float(h) / max(1, height), 6),
                            ],
                        }
                    )
                index += 1
        finally:
            capture.release()
        payload = {
            "schema_version": 1,
            "mode": "opencv_haar",
            "fps": round(fps, 3),
            "width": width,
            "height": height,
            "keyframes": keyframes,
        }
        target = work_dir / "tracking.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return [target]

    return handler


def register_builtin_handlers(registry: HandlerRegistry, settings: Settings) -> None:
    """Register optional Python handlers, marking missing dependencies."""

    if _available("faster_whisper"):
        registry.register_handler("asr", make_asr_handler(settings, registry))
    else:
        registry.mark_unavailable("asr", "faster-whisper is not installed")
    if nvenc_available(_ffmpeg(settings)):
        registry.register_handler("render_nvenc", make_render_nvenc_handler(settings))
    else:
        registry.mark_unavailable(
            "render_nvenc", "FFmpeg does not expose h264_nvenc"
        )
    if _available("rembg"):
        registry.register_handler("segment_matte", make_segment_matte_handler(settings))
    else:
        registry.mark_unavailable("segment_matte", "rembg is not installed")
    if _available("cv2"):
        registry.register_handler("face_track", make_face_track_handler(settings))
    else:
        registry.mark_unavailable("face_track", "OpenCV is not installed")


__all__ = [
    "make_asr_handler",
    "make_face_track_handler",
    "make_render_nvenc_handler",
    "make_segment_matte_handler",
    "nvenc_available",
    "register_builtin_handlers",
]
