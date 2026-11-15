"""Basic gaze/teleprompter classification for decoupage."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import GazeSpan
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class GazeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str = Field(default="auto", pattern="^(auto|opencv|mediapipe)$")
    sample_fps: float = Field(default=1.0, gt=0.0, le=10.0)
    min_span_sec: float = Field(default=1.0, gt=0.0, le=30.0)


@register_step
class GazeStep(BaseStep):
    type = "vision.gaze"
    status = "partial"
    icon = "◉"
    color = "#06b6d4"
    title = "Gaze / teleprompter"
    description = "Classify camera-facing versus teleprompter/reading spans."
    requires = ()
    produces = ("gaze_spans",)
    params_model = GazeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = GazeParams.model_validate(params)
        spans: list[GazeSpan] = []
        try:
            import cv2
        except ImportError:  # pragma: no cover - optional dependency
            cv2 = None
        source = Path(context.source)
        cascade_class = getattr(cv2, "CascadeClassifier", None)
        haar_data = getattr(cv2, "data", None)
        haar_root = getattr(haar_data, "haarcascades", "")
        if (  # pragma: no cover - optional OpenCV/MediaPipe backend
            cv2 is not None
            and cascade_class is not None
            and haar_root
            and source.is_file()
            and context.media is not None
        ):
            capture = cv2.VideoCapture(str(source))
            cascade = cascade_class(
                haar_root + "haarcascade_frontalface_default.xml"
            )
            rate = max(0.1, options.sample_fps)
            step = max(1, int(round((context.media.fps_num / context.media.fps_den) / rate)))
            index = 0
            samples: list[tuple[float, str]] = []
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if index % step == 0 and frame is not None:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = cascade.detectMultiScale(gray, 1.2, 4)
                    height, width = gray.shape[:2]
                    state = "unknown"
                    if len(faces):
                        x, _, w, _ = max(faces, key=lambda item: item[2] * item[3])
                        center = (x + w / 2) / max(1, width)
                        state = "camera" if 0.32 <= center <= 0.68 else "teleprompter"
                    samples.append(
                        (index / max(1, (context.media.fps_num / context.media.fps_den)), state)
                    )
                index += 1
            capture.release()
            spans = self._spans(samples, options.min_span_sec)
        if not spans:
            duration = (
                context.media.duration_frames * context.media.fps_den / context.media.fps_num
                if context.media is not None
                else 0.0
            )
            spans = [
                GazeSpan(
                    start_sec=0.0,
                    end_sec=duration,
                    state="unknown",
                    confidence=0.0,
                )
            ]
            context.warnings.append("Gaze backend unavailable; marked unknown")
        context.metadata["gaze_spans"] = [span.model_dump(mode="json") for span in spans]
        path = context.work / "gaze_spans.json"
        path.write_text(
            __import__("json").dumps([span.model_dump(mode="json") for span in spans], indent=2)
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["gaze_spans"] = str(path)
        io.report(100, f"{len(spans)} gaze span(s)")

    @staticmethod
    def _spans(samples: list[tuple[float, str]], min_span: float) -> list[GazeSpan]:
        spans: list[GazeSpan] = []
        start = 0.0
        state = ""
        last = 0.0
        for time_sec, current in samples:
            if current != state:
                if state and time_sec - start >= min_span:
                    spans.append(
                        GazeSpan(start_sec=start, end_sec=time_sec, state=state, confidence=0.5)
                    )
                start = time_sec
                state = current
            last = time_sec
        if state and last - start >= min_span:
            spans.append(GazeSpan(start_sec=start, end_sec=last, state=state, confidence=0.5))
        return spans
