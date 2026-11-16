"""Windowed visual QA at 10 FPS for cuts, overlays, and captions."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import VisualQaDefect, VisualQaReport
from videoflow.runtime import find_binary
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class VisualQaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fps: int = Field(default=10, ge=1, le=30)
    window_pad_sec: float = Field(default=0.5, ge=0.0, le=5.0)
    max_windows: int = Field(default=20, ge=1, le=200)
    checks: list[str] = Field(
        default_factory=lambda: [
            "flash",
            "duplicate_animation",
            "repeated_word",
            "text_late",
            "face_obstruction",
            "lip_sync",
        ]
    )
    fail_on_defects: bool = False


def extract_window(
    source: Path, destination: Path, start_sec: float, duration_sec: float, fps: int
) -> list[Path]:
    binary = find_binary("ffmpeg")
    if binary is None:
        return []
    destination.mkdir(parents=True, exist_ok=True)
    pattern = destination / "frame-%04d.jpg"
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{max(0.0, start_sec):.3f}",
        "-t",
        f"{max(0.1, duration_sec):.3f}",
        "-i",
        str(source),
        "-vf",
        f"fps={fps}",
        "-q:v",
        "2",
        str(pattern),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return []
    return sorted(destination.glob("frame-*.jpg"))


def windows_for(context: PipelineContext, pad: float, limit: int) -> list[tuple[float, float]]:
    timebase = context.media.timebase() if context.media is not None else None
    if timebase is None:
        return []
    points: list[float] = []
    if context.state is not None:
        for segment in context.state.video_segments:
            points.append(timebase.frames_to_seconds(segment.timeline_in_frame))
        for overlay in context.state.overlays:
            points.append(timebase.frames_to_seconds(overlay.start_frame))
    if not points:
        points = [0.0]
    result: list[tuple[float, float]] = []
    seen: set[float] = set()
    for point in sorted(points):
        if point in seen:
            continue
        seen.add(point)
        result.append((max(0.0, point - pad), pad * 2))
        if len(result) >= limit:
            break
    return result


def _audio_energy(pcm: Path | None, start_sec: float, duration_sec: float, rate: int) -> float:
    if pcm is None or not pcm.is_file() or rate <= 0:
        return 0.0
    try:
        import wave

        with wave.open(str(pcm), "rb") as handle:
            handle.setpos(max(0, int(start_sec * handle.getframerate())))
            frames = handle.readframes(max(1, int(duration_sec * handle.getframerate())))
    except (OSError, EOFError, ValueError):
        return 0.0
    if not frames:
        return 0.0
    values = [
        int.from_bytes(frames[index : index + 2], "little", signed=True) / 32768.0
        for index in range(0, len(frames), 2)
    ]
    return (sum(value * value for value in values) / max(1, len(values))) ** 0.5


def _motion_score(frames: list[Path]) -> float:
    try:
        from PIL import Image, ImageStat
    except ImportError:  # pragma: no cover
        return 0.0
    previous: float | None = None
    scores: list[float] = []
    for frame in frames:
        try:
            with Image.open(frame) as image:
                luma = ImageStat.Stat(image.convert("L")).mean[0] / 255
        except OSError:
            continue
        if previous is not None:
            scores.append(abs(luma - previous))
        previous = luma
    return sum(scores) / max(1, len(scores))


def _overlay_boxes(context: PipelineContext) -> list[tuple[float, float, float, float]]:
    if context.state is None:
        return []
    return [
        (
            max(0.0, overlay.position_x - overlay.width_ratio / 2),
            max(0.0, overlay.position_y - overlay.width_ratio / 2),
            min(1.0, overlay.position_x + overlay.width_ratio / 2),
            min(1.0, overlay.position_y + overlay.width_ratio / 2),
        )
        for overlay in context.state.overlays
    ]


def _face_obstruction(
    context: PipelineContext, frames: list[Path], start_sec: float, fps: int
) -> list[tuple[str, float]]:
    try:
        import cv2
    except ImportError:  # pragma: no cover
        return []
    cascade_class = getattr(cv2, "CascadeClassifier", None)
    data = getattr(cv2, "data", None)
    root = getattr(data, "haarcascades", "")
    if cascade_class is None or not root:
        return []
    cascade = cascade_class(root + "haarcascade_frontalface_default.xml")
    boxes = _overlay_boxes(context)
    if not boxes:
        return []
    defects: list[tuple[str, float]] = []
    for index, frame in enumerate(frames):
        image = cv2.imread(str(frame))
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.2, 4)
        height, width = gray.shape[:2]
        for x, y, w, h in faces:
            left, top = x / width, y / height
            right, bottom = (x + w) / width, (y + h) / height
            for box in boxes:
                overlap = max(0.0, min(right, box[2]) - max(left, box[0])) * max(
                    0.0, min(bottom, box[3]) - max(top, box[1])
                )
                if overlap > 0.15:
                    defects.append(("face_obstruction", start_sec + index / fps))
                    break
            else:
                continue
            break
    return defects


def _text_late(
    context: PipelineContext, frames: list[Path], start_sec: float, duration_sec: float, fps: int
) -> list[tuple[str, float]]:
    expectations = context.metadata.get("text_expectations")
    if not isinstance(expectations, list):
        return []
    try:
        import pytesseract
    except ImportError:  # pragma: no cover
        return []
    defects: list[tuple[str, float]] = []
    for item in expectations:
        if not isinstance(item, dict):
            continue
        expected = float(item.get("start_sec") or 0.0)
        text = str(item.get("text") or "").strip()
        if not text or not (start_sec <= expected <= start_sec + duration_sec):
            continue
        index = min(len(frames) - 1, max(0, int((expected - start_sec) * fps)))
        if index < 0:
            continue
        try:
            found = pytesseract.image_to_string(str(frames[index])).strip()
        except Exception:  # noqa: BLE001
            continue
        if text.casefold() not in found.casefold():
            defects.append(("text_late", expected))
    return defects


def analyze_frames(
    frames: list[Path], *, checks: list[str] | None = None, fps: int = 10
) -> list[tuple[str, float]]:
    try:
        from PIL import Image, ImageStat
    except ImportError:  # pragma: no cover - optional dependency
        return []
    defects: list[tuple[str, float]] = []
    previous_hash: tuple[int, ...] | None = None
    duplicate_run = 0
    previous_luma: float | None = None
    for index, frame in enumerate(frames):
        try:
            with Image.open(frame) as image:
                small = image.convert("L").resize((8, 8))
                pixels = list(small.getdata())
                average = sum(pixels) / len(pixels)
                current_hash = tuple(1 if value >= average else 0 for value in pixels)
                luma = ImageStat.Stat(image.convert("L")).mean[0] / 255
        except OSError:
            continue
        enabled = checks or ["flash", "duplicate_animation"]
        if previous_hash == current_hash:
            duplicate_run += 1
            if duplicate_run == 3 and "duplicate_animation" in enabled:
                defects.append(("duplicate_animation", index / fps))
        else:
            duplicate_run = 0
        previous_hash = current_hash
        if previous_luma is not None and abs(luma - previous_luma) > 0.32 and "flash" in enabled:
            defects.append(("flash", index / fps))
        previous_luma = luma
    return defects


@register_step
class VisualQaStep(BaseStep):
    type = "qa.visual_10fps"
    status = "partial"
    icon = "◉"
    color = "#ef4444"
    title = "Visual QA at 10 FPS"
    description = "Audit cut/overlay windows for flashes, duplicate animation, and repeated words."
    requires = ()
    produces = ("qa_report",)
    params_model = VisualQaParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VisualQaParams.model_validate(params)
        frames_dir = context.work / "qa" / "visual"
        defects: list[VisualQaDefect] = []
        windows = windows_for(context, options.window_pad_sec, options.max_windows)
        checked = 0
        for start, duration in windows:
            io.check_cancel()
            frames = extract_window(
                Path(context.source), frames_dir / f"w{checked:03d}", start, duration, options.fps
            )
            if not frames:
                continue
            checked += 1
            for kind, local in analyze_frames(frames, checks=options.checks, fps=options.fps):
                defects.append(
                    VisualQaDefect(
                        kind=kind,
                        start_sec=start + local,
                        end_sec=start + local + 1 / options.fps,
                        confidence=0.6,
                        message=kind.replace("_", " "),
                        frame_paths=[str(frames[min(len(frames) - 1, int(local * options.fps))])],
                    )
                )
            if "face_obstruction" in options.checks:
                for kind, local in _face_obstruction(context, frames, start, options.fps):
                    defects.append(
                        VisualQaDefect(
                            kind=kind,
                            start_sec=local,
                            end_sec=local + 1 / options.fps,
                            confidence=0.55,
                            message="overlay obscures a detected face",
                            frame_paths=[
                                str(
                                    frames[
                                        min(
                                            len(frames) - 1,
                                            max(0, int((local - start) * options.fps)),
                                        )
                                    ]
                                )
                            ],
                        )
                    )
            if "text_late" in options.checks:
                for kind, local in _text_late(context, frames, start, duration, options.fps):
                    defects.append(
                        VisualQaDefect(
                            kind=kind,
                            start_sec=local,
                            end_sec=local + 1 / options.fps,
                            confidence=0.6,
                            message="expected text was not detected in time",
                            frame_paths=[
                                str(
                                    frames[
                                        min(
                                            len(frames) - 1,
                                            max(0, int((local - start) * options.fps)),
                                        )
                                    ]
                                )
                            ],
                        )
                    )
            if "lip_sync" in options.checks and context.media is not None:
                energy = _audio_energy(
                    context.pcm_path,
                    start,
                    duration,
                    context.media.audio_sample_rate,
                )
                motion = _motion_score(frames)
                if (energy > 0.08 and motion < 0.01) or (energy < 0.005 and motion > 0.08):
                    defects.append(
                        VisualQaDefect(
                            kind="lip_sync",
                            start_sec=start,
                            end_sec=start + duration,
                            confidence=0.35,
                            message=(
                                f"audio/motion mismatch (energy={energy:.3f}, motion={motion:.3f})"
                            ),
                        )
                    )
            if "repeated_word" in options.checks:
                sentence = self._repeated_word(context, start, start + duration)
                if sentence is not None:
                    defects.append(
                        VisualQaDefect(
                            kind="repeated_word",
                            start_sec=start,
                            end_sec=start + duration,
                            confidence=0.8,
                            message=f"repeated word in sentence {sentence}",
                        )
                    )
            io.report(
                int((checked / max(1, len(windows))) * 100),
                f"QA window {checked}/{len(windows)}",
            )
        report = VisualQaReport(
            fps=options.fps,
            window_pad_sec=options.window_pad_sec,
            checked_windows=checked,
            defects=defects,
            frames_dir=str(frames_dir),
            passed=not defects,
        )
        path = context.work / "qa" / "qa_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        context.metadata["qa_report"] = report.model_dump(mode="json")
        context.artifacts["qa_report"] = str(path)
        context.hashes["qa_visual"] = str(len(defects))
        if options.fail_on_defects and defects:
            from videoflow.domain.errors import RecipeError

            raise RecipeError(f"Visual QA found {len(defects)} defect(s); see {path}")
        io.report(100, f"Visual QA: {len(defects)} defect(s) in {checked} window(s)")

    @staticmethod
    def _repeated_word(context: PipelineContext, start: float, end: float) -> int | None:
        if context.media is None:
            return None
        rate = context.media.audio_sample_rate
        for sentence in context.transcript:
            sentence_start = sentence.start_sample / rate
            if not (start <= sentence_start <= end):
                continue
            words = [word.word.casefold() for word in sentence.words]
            if any(left == right for left, right in zip(words, words[1:], strict=False)):
                return sentence.id
        return None
