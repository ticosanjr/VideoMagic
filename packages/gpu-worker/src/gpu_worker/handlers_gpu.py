"""Built-in Python GPU handlers for ASR, NVENC, matte, and face tracking.

These handlers are opt-in through ``VF_GPU_BUILTIN_HANDLERS=1``. Optional
dependencies are checked at startup; when one is missing the capability is
marked unavailable with an actionable reason instead of failing at job time.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scene_rules import classify_layout as _classify_layout
from scene_rules import editing_hints as _editing_hints
from scene_rules import median as _rules_median
from scene_rules import sample_times as _rules_sample_times

from gpu_worker.handlers import Handler, HandlerError, HandlerRegistry
from gpu_worker.progress import report

if TYPE_CHECKING:
    from gpu_worker.settings import Settings

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_ASR_MODELS: dict[tuple[str, str, str], Any] = {}
_ASR_LOCK = threading.RLock()
_MATTE_SESSIONS: dict[str, Any] = {}
_MATTE_LOCK = threading.RLock()
_NVENC_CACHE: dict[str, bool] = {}
_NVENC_REASONS: dict[str, str] = {}


def _matte_session(
    name: str,
    registry: HandlerRegistry | None = None,
) -> Any:
    """Return a cached rembg session instead of reloading the model per job."""

    key = str(name or "u2net")
    with _MATTE_LOCK:
        session = _MATTE_SESSIONS.get(key)
        if session is not None:
            if registry is not None:
                registry.touch(f"rembg:{key}")
            return session
        try:
            from rembg import new_session
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise HandlerError(f"rembg is not installed: {exc}") from exc
        session = new_session(key)
        _MATTE_SESSIONS[key] = session
        if registry is not None:

            def unload() -> None:
                _MATTE_SESSIONS.pop(key, None)

            registry.register(
                f"rembg:{key}",
                capability="segment_matte",
                unload=unload,
                metadata={"model": key},
            )
        return session


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
        if completed.returncode != 0 or "h264_nvenc" not in completed.stdout:
            _NVENC_CACHE[key] = False
            return False
        probe = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=128x72:d=0.1",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        _NVENC_CACHE[key] = False
        _NVENC_REASONS[key] = str(exc)[-500:]
        return False
    available = probe.returncode == 0
    _NVENC_CACHE[key] = available
    _NVENC_REASONS[key] = "" if available else (
        (probe.stderr or probe.stdout or "h264_nvenc probe failed").strip()[-500:]
    )
    return available


def nvenc_error(ffmpeg: str = "ffmpeg") -> str:
    nvenc_available(ffmpeg)
    return _NVENC_REASONS.get(str(ffmpeg), "")


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


def make_vision_blur_handler(settings: Settings) -> Handler:
    """Sample frames and report Laplacian-variance blur scores."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("vision_blur requires a video artifact")
        try:
            import cv2
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise HandlerError(f"OpenCV is not installed: {exc}") from exc
        capture = cv2.VideoCapture(str(input_paths[0]))
        if not capture.isOpened():
            raise HandlerError(f"cannot open video: {input_paths[0]}")
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
        sample = max(1, round(fps / max(0.2, float(params.get("fps") or 1.0))))
        frames: list[dict[str, Any]] = []
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
                score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                frames.append(
                    {
                        "frame": index,
                        "time": round(index / fps, 4),
                        "score": round(score, 3),
                        "blurry": score < float(params.get("threshold") or 80.0),
                    }
                )
                index += 1
        finally:
            capture.release()
        payload = {
            "schema_version": 1,
            "fps": round(fps, 3),
            "sampled": len(frames),
            "frames": frames,
        }
        target = work_dir / "blur.json"
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
        report("encoding with NVENC", 20)
        _run(command)
        report("finalizing", 95)
        if not output.is_file():
            raise HandlerError("render_nvenc did not create the output video")
        return [output]

    return handler


def make_segment_matte_handler(
    settings: Settings,
    registry: HandlerRegistry | None = None,
) -> Handler:
    """Remove the background from an image or a short video clip."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("segment_matte requires an input artifact")
        try:
            from rembg import remove
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise HandlerError(f"rembg is not installed: {exc}") from exc
        report("loading matte model", 10)
        session = _matte_session(str(params.get("model") or "u2net"), registry)
        source = input_paths[0]
        if source.suffix.casefold() in IMAGE_SUFFIXES:
            target = work_dir / "matte.png"
            report("removing background", 40)
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
            total = len(frames)
            for index, frame in enumerate(frames, start=1):
                (matte_dir / f"{index:06d}.png").write_bytes(
                    remove(frame.read_bytes(), session=session)
                )
                if index == 1 or index % 10 == 0 or index == total:
                    report("removing background", 15 + round(75 * index / total))
            report("encoding matte", 95)
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
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
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
                if total_frames and index % 60 == 0:
                    report(
                        "tracking faces",
                        10 + round(80 * min(1.0, index / total_frames)),
                    )
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


def _scene_median(values: list[float], default: float = 0.0) -> float:
    return _rules_median(values, default)


def _scene_sample_times(
    start: float,
    end: float,
    *,
    max_frames: int = 20,
    interval: float = 0.5,
) -> list[float]:
    return _rules_sample_times(
        start,
        end,
        max_frames=max_frames,
        interval=interval,
    )


def _scene_ffmpeg_times(
    source: Path,
    *,
    ffmpeg: str,
    threshold: float,
) -> list[float]:
    import re

    mapped = max(0.05, min(0.95, float(threshold) / 8.0))
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(source),
            "-vf",
            f"select='gt(scene,{mapped})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip().splitlines()
        raise HandlerError(
            f"ffmpeg scene detection failed: {tail[-1][:300] if tail else 'no stderr'}"
        )
    pattern = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
    return sorted({float(match.group(1)) for match in pattern.finditer(completed.stderr)})


def _scene_detect_times(
    proxy: Path,
    *,
    ffmpeg: str,
    fps: float,
    threshold: float,
    min_scene_len_sec: float,
    analyze_fps: float = 10.0,
) -> list[float]:
    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import AdaptiveDetector

        video = open_video(str(proxy))
        manager = SceneManager()
        manager.add_detector(
            AdaptiveDetector(
                adaptive_threshold=max(0.1, float(threshold)),
                min_scene_len=max(1, round(fps * max(0.1, min_scene_len_sec))),
                window_width=2,
            )
        )
        manager.detect_scenes(
            video,
            show_progress=False,
            frame_skip=max(0, round(analyze_fps / 10) - 1),
        )
        return [
            float(getattr(scene[0], "seconds", 0.0))
            if hasattr(scene[0], "seconds")
            else scene[0].get_seconds()
            for scene in manager.get_scene_list()
        ]
    except Exception:  # noqa: BLE001 - optional dependency
        return _scene_ffmpeg_times(proxy, ffmpeg=ffmpeg, threshold=threshold)


def _scene_face_backend(cv2: Any) -> Any:
    try:
        import mediapipe as mp  # type: ignore[import-not-found]

        detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.60,
        )

        def detect(frame: Any) -> tuple[int, float, float, float, float] | None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = detector.process(rgb)
            if not result.detections:
                return None
            detection = max(
                result.detections,
                key=lambda item: item.location_data.relative_bounding_box.width
                * item.location_data.relative_bounding_box.height,
            )
            box = detection.location_data.relative_bounding_box
            return (
                1,
                float(box.xmin + box.width / 2),
                float(box.ymin + box.height / 2),
                float(box.width),
                float(box.height),
            )

        return detect
    except Exception:  # noqa: BLE001 - Haar fallback
        try:
            cascade = cv2.CascadeClassifier(
                str(
                    Path(cv2.data.haarcascades)
                    / "haarcascade_frontalface_default.xml"
                )
            )
        except Exception:  # noqa: BLE001 - OpenCV build without Haar support
            return lambda frame: None
        if cascade.empty():
            return lambda frame: None

        def detect_haar(frame: Any) -> tuple[int, float, float, float, float] | None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            if not len(faces):
                return None
            height, width = gray.shape[:2]
            x, y, w, h = max(faces, key=lambda item: int(item[2]) * int(item[3]))
            return (
                len(faces),
                (float(x) + float(w) / 2) / max(1, width),
                (float(y) + float(h) / 2) / max(1, height),
                float(w) / max(1, width),
                float(h) / max(1, height),
            )

        return detect_haar


def _scene_visuals(
    proxy: Path,
    spans: list[tuple[float, float]],
    *,
    topology: str,
    max_frames: int = 10,
) -> list[dict[str, Any]]:
    """Sample every scene with one sequential decode pass.

    Random ``CAP_PROP_POS_MSEC`` seeks force the decoder to restart at each
    keyframe, which dominated the full scene pipeline. Walking the 10 fps proxy
    once and analyzing only the selected frames keeps the same measurements
    while removing the seek cost.
    """

    import cv2

    capture = cv2.VideoCapture(str(proxy))
    if not capture.isOpened():
        raise HandlerError(f"cannot open scene proxy: {proxy}")
    detect = _scene_face_backend(cv2)
    faces: list[list[tuple[int, float, float, float, float]]] = [[] for _ in spans]
    edges: list[list[float]] = [[] for _ in spans]
    sharp: list[list[float]] = [[] for _ in spans]
    targets: list[tuple[float, int]] = []
    for index, (start, end) in enumerate(spans):
        for timestamp in _scene_sample_times(start, end, max_frames=max_frames):
            targets.append((timestamp, index))
    targets.sort()

    def measure(frame: Any, index: int) -> None:
        if topology == "dual_canvas":
            half = frame.shape[1] // 2
            cam, screen = frame[:, half:], frame[:, :half]
        else:
            cam = screen = frame
        face = detect(cam)
        if face is not None:
            faces[index].append(face)
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        edges[index].append(float(cv2.Canny(gray, 80, 180).mean()) / 255.0)
        crop = gray
        if face is not None:
            _count, cx, cy, fw, fh = face
            height, width = gray.shape[:2]
            x0 = max(0, int((cx - fw / 2) * width))
            x1 = min(width, int((cx + fw / 2) * width))
            y0 = max(0, int((cy - fh / 2) * height))
            y1 = min(height, int((cy + fh / 2) * height))
            if x1 > x0 and y1 > y0:
                crop = gray[y0:y1, x0:x1]
        sharp[index].append(float(cv2.Laplacian(crop, cv2.CV_64F).var()))

    cursor = 0
    try:
        while cursor < len(targets):
            ok, frame = capture.read()
            if not ok:
                break
            position = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
            while cursor < len(targets) and targets[cursor][0] <= position + 0.05:
                measure(frame, targets[cursor][1])
                cursor += 1
    finally:
        capture.release()

    results: list[dict[str, Any]] = []
    for index in range(len(spans)):
        scene_faces = faces[index]
        if scene_faces:
            count = max(item[0] for item in scene_faces)
            cx = _scene_median([item[1] for item in scene_faces])
            cy = _scene_median([item[2] for item in scene_faces])
            fw = _scene_median([item[3] for item in scene_faces])
            fh = _scene_median([item[4] for item in scene_faces])
            area = fw * fh
        else:
            count = 0
            cx = cy = fw = fh = area = 0.0
        results.append(
            {
                "face_count": count,
                "face_cx": cx if count else None,
                "face_cy": cy if count else None,
                "face_w": fw if count else None,
                "face_h": fh if count else None,
                "face_area_ratio": round(area, 6),
                "edge_density": _scene_median(edges[index]),
                "sharpness_laplacian": _scene_median(sharp[index]),
            }
        )
    return results


def _scene_layout(visual: dict[str, Any], width: int, height: int, topology: str) -> str:
    return _classify_layout(
        face_count=int(visual["face_count"]),
        face_area_ratio=float(visual["face_area_ratio"]),
        edge_density=float(visual["edge_density"]),
        width=width,
        height=height,
        topology=topology,
    )


def _scene_hints(
    layout: str,
    duration: float,
    visual: dict[str, Any],
    previous: str | None,
) -> list[str]:
    return _editing_hints(
        layout=layout,
        duration_sec=duration,
        edge_density=float(visual["edge_density"]),
        sharpness_laplacian=float(visual["sharpness_laplacian"]),
        previous_layout=previous,
    )


def _scene_keyframes(
    source: Path,
    spans: list[tuple[float, float]],
    directory: Path,
    *,
    size: int,
) -> list[str]:
    from concurrent.futures import ThreadPoolExecutor

    import cv2

    directory.mkdir(parents=True, exist_ok=True)

    def one(index: int, start: float, end: float) -> str:
        scene_id = f"SC_{index + 1:04d}"
        target = directory / f"{scene_id}.jpg"
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            capture.release()
            return ""
        try:
            capture.set(
                cv2.CAP_PROP_POS_MSEC,
                (start + max(0.0, end - start) / 2.0) * 1000.0,
            )
            ok, frame = capture.read()
        finally:
            capture.release()
        if not ok:
            return ""
        height, width = frame.shape[:2]
        scale = min(1.0, float(size) / max(1, max(width, height)))
        if scale < 1.0:
            frame = cv2.resize(
                frame,
                (max(1, round(width * scale)), max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        cv2.imwrite(str(target), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
        return f"keyframes/{scene_id}.jpg"

    workers = min(8, max(1, len(spans)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(
            pool.map(
                lambda item: one(item[0], item[1][0], item[1][1]),
                enumerate(spans),
            )
        )


def make_scene_analyze_handler(settings: Settings) -> Handler:
    """Detect scenes, classify layouts, and return keyframes as a zip."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        import shutil
        import zipfile

        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("scene_analyze requires a video artifact")
        if not _available("cv2"):
            raise HandlerError("OpenCV is not installed on the worker")
        source = input_paths[0]
        width = max(1, int(params.get("width") or 1920))
        height = max(1, int(params.get("height") or 1080))
        fps = max(1.0, float(params.get("fps") or 30.0))
        sample_rate = max(1, int(params.get("sample_rate") or 48_000))
        duration = max(0.001, float(params.get("duration_sec") or 0.0))
        threshold = float(params.get("threshold") or 3.0)
        min_scene_len_sec = float(params.get("min_scene_len_sec") or 1.5)
        topology = str(params.get("source_topology") or "single_16x9")
        keyframe_size = max(128, min(1080, int(params.get("keyframe_size") or 544)))
        visual_max_frames = max(3, min(20, int(params.get("visual_max_frames") or 10)))
        if topology == "auto":
            ratio = width / max(1, height)
            topology = "dual_canvas" if abs(ratio - 3.55) < 0.15 else "single_16x9"
        ffmpeg = _ffmpeg(settings)
        proxy = work_dir / "proxy_360.mp4"
        analyze_fps = 10.0
        report("building scene proxy", 8)
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
                "scale=-2:360",
                "-r",
                str(int(analyze_fps)),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                str(proxy),
            ]
        )
        report("detecting cuts", 30)
        times = _scene_detect_times(
            proxy,
            ffmpeg=ffmpeg,
            fps=analyze_fps,
            threshold=threshold,
            min_scene_len_sec=min_scene_len_sec,
            analyze_fps=analyze_fps,
        )
        boundaries = sorted(
            {
                0.0,
                *[t for t in times if 0 < t < duration],
                *[
                    float(item)
                    for item in params.get("decupage_boundaries") or []
                    if 0 < float(item) < duration
                ],
                round(duration, 6),
            }
        )
        jumps = {
            round(float(item), 6)
            for item in params.get("decupage_jumps") or []
            if 0 < float(item) < duration
        }
        minimum = max(0.1, min_scene_len_sec)
        merged = [0.0]
        for value in boundaries:
            if value <= 0 or value >= duration:
                continue
            if value - merged[-1] >= minimum:
                merged.append(value)
        if duration - merged[-1] < minimum and len(merged) > 1:
            merged.pop()
        merged.append(duration)
        spans = [
            (merged[index], merged[index + 1])
            for index in range(len(merged) - 1)
        ]
        if not spans:
            spans = [(0.0, duration)]
        report("sampling scenes", 45)
        visuals = _scene_visuals(
            proxy,
            spans,
            topology=topology,
            max_frames=visual_max_frames,
        )
        report("extracting keyframes", 70)
        paths = _scene_keyframes(source, spans, work_dir / "keyframes", size=keyframe_size)
        report("writing manifest", 90)
        scenes: list[dict[str, Any]] = []
        previous: str | None = None
        for index, ((start, end), visual) in enumerate(zip(spans, visuals, strict=False)):
            layout = _scene_layout(visual, width, height, topology)
            face = None
            if visual["face_count"] >= 1 and None not in (
                visual["face_cx"],
                visual["face_cy"],
                visual["face_w"],
                visual["face_h"],
            ):
                face = {
                    "cx": min(1.0, max(0.0, float(visual["face_cx"]))),
                    "cy": min(1.0, max(0.0, float(visual["face_cy"]))),
                    "w": min(1.0, max(0.001, float(visual["face_w"]))),
                    "h": min(1.0, max(0.001, float(visual["face_h"]))),
                }
            scenes.append(
                {
                    "scene_id": f"SC_{index + 1:04d}",
                    "start_sample": max(0, round(start * sample_rate)),
                    "end_sample": max(1, round(min(end, duration) * sample_rate)),
                    "start_sec": round(start, 6),
                    "end_sec": round(end, 6),
                    "transition_source": "DECUPAGEM_JUMP"
                    if round(start, 6) in jumps
                    else "VISUAL_CUT",
                    "layout_type": layout,
                    "face_count": int(visual["face_count"]),
                    "face_bbox_norm": face,
                    "face_area_ratio": min(1.0, max(0.0, visual["face_area_ratio"])),
                    "edge_density": min(1.0, max(0.0, visual["edge_density"])),
                    "sharpness_laplacian": max(0.0, visual["sharpness_laplacian"]),
                    "keyframe_path": paths[index] if index < len(paths) else "",
                    "editing_hints": _scene_hints(
                        layout, end - start, visual, previous
                    ),
                }
            )
            previous = layout
        manifest = {
            "schema_version": 1,
            "video_id": str(params.get("video_id") or ""),
            "source_topology": topology,
            "resolution": {"w": width, "h": height},
            "fps_num": int(params.get("fps_num") or round(fps)),
            "fps_den": int(params.get("fps_den") or 1),
            "scenes": scenes,
        }
        target = work_dir / "scenes_manifest.json"
        target.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        archive = work_dir / "scene_keyframes.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for directory, _dirs, files in os.walk(work_dir / "keyframes"):
                for name in files:
                    path = Path(directory) / name
                    bundle.write(path, path.relative_to(work_dir).as_posix())
        shutil.rmtree(work_dir / "keyframes", ignore_errors=True)
        proxy.unlink(missing_ok=True)
        return [target, archive]

    return handler


def _binary_available(binary: str) -> bool:
    candidate = shutil.which(binary)
    if candidate:
        return True
    return Path(binary).expanduser().is_file()


def make_short_render_handler(settings: Settings) -> Handler:
    """Execute tokenised micro-clip/concat/final FFmpeg commands."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("short_render requires input artifacts")
        tokens = {
            f"__IN{index}__": str(path) for index, path in enumerate(input_paths)
        }

        def replace(value: str) -> str:
            for token, path in tokens.items():
                value = value.replace(token, path)
            return value

        def replace_filter(value: str) -> str:
            for token, path in tokens.items():
                value = value.replace(token, _escape_filter_path(Path(path)))
            return value

        ffmpeg = _ffmpeg(settings)
        cache_root = work_dir.parent.parent / "short_segment_cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        raw_segments = params.get("segments") or []
        total_segments = max(1, len(raw_segments))
        for index, segment in enumerate(raw_segments, start=1):
            report(
                f"rendering segment {index}/{total_segments}",
                5 + round(80 * (index - 1) / total_segments),
            )
            if not isinstance(segment, dict):
                raise HandlerError("short_render segment must be an object")
            output_name = str(segment.get("output") or f"seg_{index:04d}.mp4")
            cached = cache_root / f"{segment.get('cache_key') or index}.mp4"
            if cached.is_file() and cached.stat().st_size > 0:
                target = work_dir / output_name
                try:
                    os.link(cached, target)
                except OSError:
                    shutil.copy2(cached, target)
                continue
            script = work_dir / f"segment_{index:04d}.ffscript"
            script.write_text(
                replace_filter(str(segment.get("filter") or "")), encoding="utf-8"
            )
            argv = [str(item) for item in segment.get("argv") or []]
            if not argv:
                raise HandlerError("short_render segment has no command")
            argv[0] = ffmpeg
            argv = [
                replace(item).replace(f"__SCRIPT_{index}__", str(script))
                for item in argv
            ]
            if any("__IN" in item or "__SCRIPT" in item for item in argv):
                raise HandlerError("short_render left an unresolved placeholder")
            _run_in(argv, work_dir)
            segment_output = work_dir / output_name
            if not segment_output.is_file() or segment_output.stat().st_size == 0:
                raise HandlerError(
                    f"short_render segment {index} produced no output"
                )
            if not cached.is_file():
                try:
                    os.link(segment_output, cached)
                except OSError:
                    shutil.copy2(segment_output, cached)
        report("concatenating and encoding", 92)
        names = [str(item) for item in params.get("concat_names") or []]
        if not names:
            raise HandlerError("short_render produced no micro-clips")
        concat = work_dir / "concat.txt"
        concat.write_text(
            "\n".join(f"file '{name}'" for name in names) + "\n",
            encoding="utf-8",
        )
        final_script = work_dir / "final.ffscript"
        final_script.write_text(
            replace_filter(str(params.get("final_filter") or "")), encoding="utf-8"
        )
        final_argv = [str(item) for item in params.get("final_argv") or []]
        if not final_argv:
            raise HandlerError("short_render has no final command")
        final_argv[0] = ffmpeg
        final_argv = [
            replace(item)
            .replace("__CONCAT__", str(concat))
            .replace("__SCRIPT_FINAL__", str(final_script))
            for item in final_argv
        ]
        if any("__IN" in item or "__SCRIPT" in item or "__CONCAT__" in item for item in final_argv):
            raise HandlerError("short_render left an unresolved placeholder")
        _run_in(final_argv, work_dir)
        output = work_dir / str(params.get("output_name") or "short.mp4")
        if not output.is_file():
            raise HandlerError("short_render finished without an output file")
        return [output]

    return handler


def _run_in(tokens: list[str], cwd: Path, *, timeout: float = 3600.0) -> None:
    try:
        completed = subprocess.run(
            tokens,
            cwd=str(cwd),
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


def warmup_models(
    settings: Settings,
    registry: HandlerRegistry | None = None,
) -> dict[str, Any]:
    """Preload expensive models so the first job does not pay cold start.

    Failures are reported, never raised: a missing optional dependency or an
    offline model download must not stop the worker from serving the
    capabilities it does have.
    """

    loaded: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    model_name = settings.asr_model or "large-v3-turbo"
    key = (model_name, settings.asr_device or "cuda", settings.asr_compute_type or "float16")
    if not _available("faster_whisper"):
        skipped.append("asr: faster-whisper is not installed")
    else:
        try:
            from faster_whisper import WhisperModel

            with _ASR_LOCK:
                if key not in _ASR_MODELS:
                    _ASR_MODELS[key] = WhisperModel(
                        key[0],
                        device=key[1],
                        compute_type=key[2],
                        cpu_threads=int(settings.asr_cpu_threads or 0),
                        num_workers=int(settings.asr_num_workers or 1),
                    )
                    if registry is not None:
                        model_key = f"faster-whisper:{key[0]}:{key[1]}:{key[2]}"

                        def unload_asr() -> None:
                            _ASR_MODELS.pop(key, None)

                        registry.register(
                            model_key,
                            capability="asr",
                            unload=unload_asr,
                            vram_mb=3277,
                            metadata={"model": key[0], "device": key[1]},
                        )
            loaded.append(f"faster-whisper:{key[0]}")
        except Exception as exc:  # noqa: BLE001 - warmup is best-effort
            errors.append(f"asr: {exc}")
    if not _available("rembg"):
        skipped.append("matte: rembg is not installed")
    else:
        try:
            _matte_session("u2net", registry)
            loaded.append("rembg:u2net")
        except Exception as exc:  # noqa: BLE001 - warmup is best-effort
            errors.append(f"matte: {exc}")
    return {
        "ok": not errors,
        "loaded": loaded,
        "skipped": skipped,
        "errors": errors,
    }


def register_builtin_handlers(registry: HandlerRegistry, settings: Settings) -> None:
    """Register optional Python handlers, marking missing dependencies."""

    if _available("faster_whisper"):
        registry.register_handler("asr", make_asr_handler(settings, registry))
        registry.register_handler(
            "forced_align", make_forced_align_handler(settings)
        )
    else:
        registry.mark_unavailable("asr", "faster-whisper is not installed")
        registry.mark_unavailable(
            "forced_align", "faster-whisper is not installed"
        )
    if nvenc_available(_ffmpeg(settings)):
        registry.register_handler("render_nvenc", make_render_nvenc_handler(settings))
    else:
        registry.mark_unavailable(
            "render_nvenc", "FFmpeg does not expose h264_nvenc"
        )
    if _available("rembg"):
        registry.register_handler(
            "segment_matte", make_segment_matte_handler(settings, registry)
        )
    else:
        registry.mark_unavailable("segment_matte", "rembg is not installed")
    if _available("cv2"):
        registry.register_handler("face_track", make_face_track_handler(settings))
        registry.register_handler(
            "vision_blur", make_vision_blur_handler(settings)
        )
        registry.register_handler(
            "scene_analyze", make_scene_analyze_handler(settings)
        )
    else:
        registry.mark_unavailable("face_track", "OpenCV is not installed")
        registry.mark_unavailable("vision_blur", "OpenCV is not installed")
        registry.mark_unavailable("scene_analyze", "OpenCV is not installed")
    if _binary_available(_ffmpeg(settings)):
        registry.register_handler(
            "short_render", make_short_render_handler(settings)
        )
    else:
        registry.mark_unavailable("short_render", "FFmpeg is not available")
    registry.mark_unavailable(
        "audio_events", "YAMNet ONNX model is not configured on the worker"
    )


__all__ = [
    "make_asr_handler",
    "make_face_track_handler",
    "make_forced_align_handler",
    "make_render_nvenc_handler",
    "make_scene_analyze_handler",
    "make_short_render_handler",
    "make_segment_matte_handler",
    "make_vision_blur_handler",
    "nvenc_available",
    "nvenc_error",
    "register_builtin_handlers",
    "warmup_models",
]
