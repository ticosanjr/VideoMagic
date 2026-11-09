from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from videoflow.application.timeline_meta import load_meta
from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.face_contact import (
    FaceContactParams,
    FaceContactStep,
    _analyze_frame,
    _merge_intervals,
)


class FakeFace:
    def detectMultiScale(self, image, **kwargs):
        return [(30, 20, 40, 40)]


class FakeEyes:
    def detectMultiScale(self, image, **kwargs):
        return [(5, 5, 8, 8), (20, 5, 8, 8)]


class FakeCv2:
    COLOR_BGR2GRAY = 0

    def cvtColor(self, image, code):
        return image

    def imread(self, path):
        return np.zeros((100, 100, 3), dtype=np.uint8)


class FakeAdapter:
    def extract_frames(self, source, directory, *, fps=1.0, width=640, **kwargs):
        return [Path(directory) / "frame-000001.jpg", Path(directory) / "frame-000002.jpg"]


def test_analyze_frame_labels_centered_face_with_eyes() -> None:
    result = _analyze_frame(
        FakeCv2(),
        np.zeros((100, 100, 3), dtype=np.uint8),
        FakeFace(),
        FakeEyes(),
        min_face_ratio=0.1,
        center_tolerance=0.3,
        min_eyes=1,
    )
    assert result[0] is True
    assert result[1] > 0.5
    assert result[2] == 0.4


def test_merge_intervals_keeps_nearby_frames() -> None:
    spans = _merge_intervals([(1, 0.8), (2, 0.9), (10, 0.7)], fps=1.0)
    assert len(spans) == 2
    assert spans[0]["start_sec"] == 1.0
    assert spans[1]["start_sec"] == 10.0


def test_face_contact_fallback_and_markers(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "out"
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )
    monkeypatch.setattr("videoflow.steps.face_contact._cv2", lambda: None)
    FaceContactStep().run(context, FaceContactParams(), StepIO())
    payload = json.loads((output / "vision" / "face-contact.json").read_text())
    assert payload["available"] is False
    assert context.warnings

    monkeypatch.setattr("videoflow.steps.face_contact._cv2", lambda: FakeCv2())
    monkeypatch.setattr(
        "videoflow.steps.face_contact._cascades", lambda cv2: (FakeFace(), FakeEyes())
    )
    context2 = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out2",
        work=tmp_path / "out2" / "work",
        exports=tmp_path / "out2" / "exports",
    )
    FaceContactStep().run(
        context2,
        FaceContactParams(),
        StepIO(adapter=FakeAdapter()),
    )
    payload = json.loads(
        (tmp_path / "out2" / "vision" / "face-contact.json").read_text()
    )
    assert payload["available"] is True
    assert payload["green_label_count"] == 1
    meta = load_meta(tmp_path / "out2")
    assert meta.markers[0].color == "#00FF66"
    assert meta.markers[0].end_sec >= meta.markers[0].time_sec
