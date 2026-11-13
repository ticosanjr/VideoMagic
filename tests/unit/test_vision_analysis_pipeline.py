from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from videoflow.application import vision_analysis
from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo
from videoflow.steps.base import StepIO
from videoflow.steps.vision_analysis import (
    VisionOcrParams,
    VisionOcrStep,
    VisionSegmentParams,
    VisionSegmentStep,
    VisionTrackParams,
    VisionTrackStep,
)


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
            duration_frames=120,
            fps_num=30,
            fps_den=1,
            width=1280,
            height=720,
            audio_sample_rate=48000,
        ),
    )


class FakeImage:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_extract_frames_runs_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(vision_analysis, "find_binary", lambda name: "ffmpeg")

    def fake_run(command, **kwargs):
        pattern = Path(command[-1])
        pattern.parent.mkdir(parents=True, exist_ok=True)
        (pattern.parent / "frame-00001.png").write_bytes(b"png")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(vision_analysis.subprocess, "run", fake_run)
    frames = vision_analysis.extract_frames(
        tmp_path / "source.mp4", tmp_path / "frames", fps=1, max_frames=1
    )
    assert frames and frames[0].is_file()


def test_ocr_boxes_reads_pytesseract(monkeypatch) -> None:
    pytesseract = ModuleType("pytesseract")
    pytesseract.Output = SimpleNamespace(DICT="dict")  # type: ignore[attr-defined]
    pytesseract.image_to_data = lambda *args, **kwargs: {  # type: ignore[attr-defined]
        "text": ["Hello", "", "World"],
        "conf": [90, 50, 0],
        "left": [1, 2, 3],
        "top": [4, 5, 6],
        "width": [10, 11, 12],
        "height": [5, 6, 7],
    }
    pil = ModuleType("PIL")
    pil.Image = SimpleNamespace(open=lambda path: FakeImage())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract)
    monkeypatch.setitem(sys.modules, "PIL", pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", pil.Image)

    boxes = vision_analysis.ocr_boxes(Path("frame.png"), min_confidence=0.5)
    assert [item["text"] for item in boxes] == ["Hello"]
    assert boxes[0]["confidence"] == 0.9


def test_ocr_boxes_returns_empty_without_backend(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pytesseract", None)
    assert vision_analysis.ocr_boxes(Path("frame.png")) == []


def test_segmentation_mask_uses_mediapipe(tmp_path: Path, monkeypatch) -> None:
    mediapipe = ModuleType("mediapipe")
    result = SimpleNamespace(segmentation_mask=np.ones((64, 64), dtype=np.float32))
    class Segmenter:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def process(self, image):
            return result

    segmenter = Segmenter()
    mediapipe.solutions = SimpleNamespace(  # type: ignore[attr-defined]
        selfie_segmentation=SimpleNamespace(SelfieSegmentation=lambda **kwargs: segmenter)
    )
    cv2 = ModuleType("cv2")
    cv2.COLOR_BGR2RGB = 1
    cv2.COLOR_BGR2GRAY = 2
    cv2.imread = lambda path: np.zeros((64, 64, 3), dtype=np.uint8)
    cv2.cvtColor = lambda image, code: image
    cv2.imwrite = lambda path, mask: Path(path).write_bytes(mask.tobytes())
    monkeypatch.setitem(sys.modules, "mediapipe", mediapipe)
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    target = tmp_path / "mask.png"
    path, backend = vision_analysis.segmentation_mask(
        Path("frame.png"), target, backend="mediapipe"
    )
    assert path == target
    assert backend == "mediapipe"


def test_segmentation_mask_uses_grabcut(tmp_path: Path, monkeypatch) -> None:
    cv2 = ModuleType("cv2")
    cv2.GC_INIT_WITH_RECT = 0
    cv2.GC_FGD = 1
    cv2.GC_PR_FGD = 3
    cv2.imread = lambda path: np.zeros((64, 64, 3), dtype=np.uint8)
    cv2.grabCut = lambda *args: None
    cv2.imwrite = lambda path, mask: Path(path).write_bytes(b"mask")
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "mediapipe", None)
    target = tmp_path / "mask.png"
    path, backend = vision_analysis.segmentation_mask(
        Path("frame.png"), target, backend="grabcut"
    )
    assert path == target
    assert backend == "grabcut"


def test_segmentation_mask_without_cv2(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "cv2", None)
    assert vision_analysis.segmentation_mask(Path("x"), tmp_path / "m.png") == (None, "none")


def test_track_box_reads_optical_flow(tmp_path: Path, monkeypatch) -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    class Capture:
        def __init__(self):
            self.t = 0.0

        def isOpened(self):
            return True

        def get(self, prop):
            return 30.0 if prop == 5 else self.t

        def set(self, prop, value):
            return True

        def read(self):
            self.t += 0.02
            return True, frame

        def release(self):
            return None

    cv2 = ModuleType("cv2")
    cv2.CAP_PROP_FPS = 5
    cv2.CAP_PROP_POS_MSEC = 0
    cv2.COLOR_BGR2GRAY = 2
    cv2.VideoCapture = lambda path: Capture()
    cv2.cvtColor = lambda image, code: image
    cv2.goodFeaturesToTrack = lambda *args, **kwargs: np.array(
        [[[10.0, 10.0]], [[20.0, 20.0]]], dtype=np.float32
    )
    cv2.calcOpticalFlowPyrLK = lambda *args, **kwargs: (
        np.array([[[11.0, 11.0]], [[21.0, 21.0]]], dtype=np.float32),
        np.array([[1], [1]], dtype=np.uint8),
        None,
    )
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setattr(vision_analysis, "find_binary", lambda name: "ffmpeg")
    points = vision_analysis.track_box(
        tmp_path / "source.mp4", (0, 0, 40, 40), start_sec=0, end_sec=0.1, fps=2
    )
    assert points
    assert points[0]["x"] > 0


def test_vision_ocr_step_records_boxes(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(
        "videoflow.steps.vision_analysis.extract_frames",
        lambda *args, **kwargs: [context.source],
    )
    monkeypatch.setattr(
        "videoflow.steps.vision_analysis.ocr_boxes",
        lambda *args, **kwargs: [
            {
                "text": "Hello",
                "confidence": 0.9,
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
            }
        ],
    )
    monkeypatch.setattr(
        "videoflow.steps.vision_analysis._frame_size", lambda path: (1280, 720)
    )
    VisionOcrStep().run(context, VisionOcrParams(), StepIO())
    payload = json.loads((context.output / "vision" / "ocr.json").read_text())
    assert payload["frames"][0]["boxes"][0]["text"] == "Hello"


def test_vision_segment_step_records_masks(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(
        "videoflow.steps.vision_analysis.extract_frames",
        lambda *args, **kwargs: [context.source],
    )
    monkeypatch.setattr(
        "videoflow.steps.vision_analysis.segmentation_mask",
        lambda image, target, backend: (Path(target), "grabcut"),
    )
    VisionSegmentStep().run(context, VisionSegmentParams(), StepIO())
    payload = json.loads((context.output / "vision" / "segments.json").read_text())
    assert payload["masks"][0]["backend"] == "grabcut"


def test_vision_track_step_tracks_ocr_boxes(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    (context.output / "vision").mkdir(parents=True)
    (context.output / "vision" / "ocr.json").write_text(
        json.dumps(
            {
                "frames": [
                    {
                        "time_sec": 0,
                        "width": 1280,
                        "height": 720,
                        "boxes": [{"text": "Hello", "x": 10, "y": 10, "width": 20, "height": 10}],
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(
        "videoflow.steps.vision_analysis.track_box",
        lambda *args, **kwargs: [{"time": 0, "x": 15, "y": 15}],
    )
    VisionTrackStep().run(context, VisionTrackParams(), StepIO())
    payload = json.loads((context.output / "vision" / "tracks.json").read_text())
    assert payload["tracks"][0]["text"] == "Hello"
    assert payload["tracks"][0]["points"]


def test_extract_frames_errors(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import vision_analysis as module

    monkeypatch.setattr(module, "find_binary", lambda name: None)
    with pytest.raises(RuntimeError, match="FFmpeg"):
        module.extract_frames(tmp_path / "v.mp4", tmp_path / "frames")
    monkeypatch.setattr(module, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(RuntimeError, match="extract"):
        module.extract_frames(tmp_path / "v.mp4", tmp_path / "frames")


def test_ocr_and_segmentation_defensive_branches(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import vision_analysis as module

    pytesseract = ModuleType("pytesseract")
    pytesseract.Output = SimpleNamespace(DICT="dict")  # type: ignore[attr-defined]
    pytesseract.image_to_data = lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[attr-defined]
        RuntimeError("ocr failed")
    )
    pil = ModuleType("PIL")
    pil.Image = SimpleNamespace(open=lambda path: FakeImage())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract)
    monkeypatch.setitem(sys.modules, "PIL", pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", pil.Image)
    assert module.ocr_boxes(Path("frame.png")) == []

    pytesseract.image_to_data = lambda *args, **kwargs: {  # type: ignore[attr-defined]
        "text": ["Hello"],
        "conf": ["bad"],
        "left": [1],
        "top": [2],
        "width": [3],
        "height": [4],
    }
    assert module.ocr_boxes(Path("frame.png")) == []

    cv2 = ModuleType("cv2")
    cv2.imread = lambda path: None
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "mediapipe", None)
    assert module.segmentation_mask(Path("x"), tmp_path / "m.png") == (None, "none")

    cv2.imread = lambda path: np.zeros((10, 10, 3), dtype=np.uint8)
    cv2.GC_INIT_WITH_RECT = 0
    cv2.GC_FGD = 1
    cv2.GC_PR_FGD = 3
    cv2.COLOR_BGR2RGB = 1
    cv2.grabCut = lambda *args: (_ for _ in ()).throw(RuntimeError("bad"))
    monkeypatch.setitem(sys.modules, "mediapipe", ModuleType("mediapipe"))
    assert module.segmentation_mask(Path("x"), tmp_path / "m.png") == (None, "none")


def test_track_box_early_returns(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import vision_analysis as module

    cv2 = ModuleType("cv2")
    cv2.CAP_PROP_FPS = 5
    cv2.CAP_PROP_POS_MSEC = 0
    cv2.COLOR_BGR2GRAY = 2
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setattr(module, "find_binary", lambda name: None)
    assert module.track_box(Path("v.mp4"), (0, 0, 10, 10)) == []

    monkeypatch.setattr(module, "find_binary", lambda name: "ffmpeg")
    cv2.VideoCapture = lambda path: SimpleNamespace(isOpened=lambda: False)
    assert module.track_box(Path("v.mp4"), (0, 0, 10, 10)) == []

    class Capture:
        def isOpened(self):
            return True

        def get(self, prop):
            return 0

        def set(self, prop, value):
            return True

        def read(self):
            return False, None

        def release(self):
            return None

    cv2.VideoCapture = lambda path: Capture()
    assert module.track_box(Path("v.mp4"), (0, 0, 10, 10)) == []


def test_vision_steps_warn_and_cache(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps import vision_analysis as steps

    context = _context(tmp_path)
    monkeypatch.setattr(
        steps, "extract_frames", lambda *args, **kwargs: [context.source]
    )
    monkeypatch.setattr(steps, "ocr_boxes", lambda *args, **kwargs: [])
    monkeypatch.setattr(steps, "_frame_size", lambda path: (1, 1))
    VisionOcrStep().run(context, VisionOcrParams(), StepIO())
    assert any("OCR found no text" in item for item in context.warnings)
    assert VisionOcrStep().cache_outputs(context)

    context = _context(tmp_path / "seg")
    monkeypatch.setattr(
        steps, "segmentation_mask", lambda *args, **kwargs: (None, "none")
    )
    VisionSegmentStep().run(context, VisionSegmentParams(), StepIO())
    assert any("Subject segmentation unavailable" in item for item in context.warnings)
    assert VisionSegmentStep().cache_outputs(context)

    context = _context(tmp_path / "track")
    VisionTrackStep().run(context, VisionTrackParams(), StepIO())
    assert any("No tracking boxes" in item for item in context.warnings)
    assert VisionTrackStep().cache_outputs(context)

    assert VisionOcrStep().cache_outputs(_context(tmp_path / "empty")) == ()
    assert VisionSegmentStep().cache_outputs(_context(tmp_path / "empty2")) == ()
    assert VisionTrackStep().cache_outputs(_context(tmp_path / "empty3")) == ()
