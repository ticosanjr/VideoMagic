from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo
from videoflow.steps import face_contact
from videoflow.steps.base import StepIO
from videoflow.steps.face_contact import FaceContactParams, FaceContactStep


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir(parents=True)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    return PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=MediaInfo(
            source_path=str(source),
            duration_frames=30,
            fps_num=30,
            fps_den=1,
            width=1280,
            height=720,
            audio_sample_rate=48000,
        ),
    )


def test_optional_imports_return_none(monkeypatch) -> None:
    for name in ("cv2", "ultralytics", "mediapipe"):
        monkeypatch.setitem(sys.modules, name, None)
    assert face_contact._cv2() is None
    assert face_contact._yolo() is None
    assert face_contact._mediapipe() is None

    monkeypatch.setitem(sys.modules, "cv2", ModuleType("cv2"))
    ultralytics = ModuleType("ultralytics")
    ultralytics.YOLO = object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics)
    monkeypatch.setitem(sys.modules, "mediapipe", ModuleType("mediapipe"))
    assert face_contact._cv2() is not None
    assert face_contact._yolo() is not None
    assert face_contact._mediapipe() is not None


def test_unavailable_backends_write_a_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(face_contact, "_cv2", lambda: object())
    monkeypatch.setattr(face_contact, "_mediapipe", lambda: None)
    monkeypatch.setattr(face_contact, "_yolo", lambda: None)

    for backend, reason in (
        ("mediapipe", "MediaPipe"),
        ("yolo", "YOLO"),
    ):
        context = _context(tmp_path / backend)
        FaceContactStep().run(
            context,
            FaceContactParams(backend=backend, yolo_model="/model.pt"),
            StepIO(),
        )
        payload = context.metadata["eye_contact"]
        assert payload["available"] is False
        assert reason in payload["reason"]
        assert FaceContactStep().cache_outputs(context)

    context = _context(tmp_path / "none")
    FaceContactStep().run(context, FaceContactParams(backend="none"), StepIO())
    assert context.metadata["eye_contact"]["backend"] == "none"


def test_yolo_load_failure_and_missing_cascades(tmp_path: Path, monkeypatch) -> None:
    def yolo(path):
        raise RuntimeError("bad model")

    monkeypatch.setattr(face_contact, "_cv2", lambda: object())
    monkeypatch.setattr(face_contact, "_mediapipe", lambda: None)
    monkeypatch.setattr(face_contact, "_yolo", lambda: yolo)
    context = _context(tmp_path / "yolo")
    FaceContactStep().run(
        context,
        FaceContactParams(backend="yolo", yolo_model="/model.pt"),
        StepIO(),
    )
    assert "could not be loaded" in context.metadata["eye_contact"]["reason"]

    monkeypatch.setattr(face_contact, "_cascades", lambda cv2: None)
    context = _context(tmp_path / "cascades")
    FaceContactStep().run(
        context,
        FaceContactParams(backend="opencv"),
        StepIO(),
    )
    assert context.metadata["eye_contact"]["backend"] == "opencv"
    assert any("cascades missing" in item for item in context.warnings)


def test_frame_extraction_failure_is_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(face_contact, "_cv2", lambda: object())
    monkeypatch.setattr(face_contact, "_mediapipe", lambda: None)
    monkeypatch.setattr(face_contact, "_cascades", lambda cv2: (1, 1))

    class Adapter:
        def extract_frames(self, *args, **kwargs):
            raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(face_contact, "adapter_for", lambda *args: Adapter())
    context = _context(tmp_path)
    FaceContactStep().run(context, FaceContactParams(backend="opencv"), StepIO())
    assert "Frame extraction failed" in context.metadata["eye_contact"]["reason"]


def test_successful_opencv_analysis(tmp_path: Path, monkeypatch) -> None:
    frames = [tmp_path / "a.png", tmp_path / "b.png"]
    for frame in frames:
        frame.write_bytes(b"png")
    monkeypatch.setattr(face_contact, "_cv2", lambda: object())
    monkeypatch.setattr(face_contact, "_mediapipe", lambda: None)
    monkeypatch.setattr(face_contact, "_cascades", lambda cv2: (1, 1))

    class Adapter:
        def extract_frames(self, *args, **kwargs):
            return frames

    class Cv2:
        @staticmethod
        def imread(path):
            return None if str(path).endswith("b.png") else object()

    monkeypatch.setattr(face_contact, "adapter_for", lambda *args: Adapter())
    monkeypatch.setattr(
        face_contact,
        "_analyze_frame",
        lambda *args, **kwargs: (True, 0.9, 0.2),
    )
    monkeypatch.setattr(
        face_contact,
        "add_marker",
        lambda *args, **kwargs: None,
    )
    # _cv2() returns a plain object; the analysis is faked, so use a module-like value.
    monkeypatch.setattr(face_contact, "_cv2", lambda: Cv2())
    context = _context(tmp_path)
    FaceContactStep().run(context, FaceContactParams(backend="opencv"), StepIO())
    payload = context.metadata["eye_contact"]
    assert payload["available"] is True
    assert payload["frames_analyzed"] == 2
    assert payload["eye_contact_frames"] == 1
