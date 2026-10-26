"""Multimodal analysis heuristics, persistence, and decoder errors."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from videoflow.application import multimodal
from videoflow.domain.errors import IngestError, ShortEditError, StateNotReadyError


def test_audio_features_handle_empty_and_short_inputs() -> None:
    assert multimodal.audio_features(np.array([], dtype=np.int16), 16000)["label"] == "unknown"
    assert multimodal.audio_features(np.zeros(10), 0)["label"] == "unknown"
    assert multimodal.audio_features(np.zeros(100, dtype=np.int16), 16000)["label"] == "unknown"


def test_audio_features_classify_signal_shape() -> None:
    calm = np.zeros(16000, dtype=np.int16)
    energetic = np.full(16000, 20000, dtype=np.int16)
    alternating = np.tile(np.array([3000, -3000], dtype=np.int16), 8000)

    assert multimodal.audio_features(calm, 16000)["label"] == "calm"
    assert multimodal.audio_features(energetic, 16000)["label"] == "energetic"
    assert multimodal.audio_features(alternating, 16000)["label"] != "unknown"

    rows = []
    for level in (100, 4000, 12000):
        rows.append(np.tile(np.array([level, -level], dtype=np.int16), 800))
    expressive = np.concatenate(rows)
    assert multimodal.audio_features(expressive, 16000)["label"] == "expressive"


def test_motion_region_rejects_empty_or_static_frames() -> None:
    assert multimodal.motion_region(np.zeros((1, 10, 10), dtype=np.uint8)) is None
    assert multimodal.motion_region(np.zeros((5, 10, 10), dtype=np.uint8)) is None


def test_motion_region_reports_the_moving_area() -> None:
    frames = np.zeros((3, 10, 20), dtype=np.uint8)
    frames[0, 2:5, 12:16] = 255

    region = multimodal.motion_region(frames)

    assert region is not None
    assert 0.0 <= region["x"] <= 1.0
    assert 0.0 <= region["y"] <= 1.0
    assert region["coverage"] > 0


def test_analyze_short_missing_file(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="does not exist"):
        multimodal.analyze_short(tmp_path / "missing.mp4")


def test_analyze_short_without_opencv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "short.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(multimodal, "_duration_samples", lambda *_a, **_k: 8000)
    monkeypatch.setattr(multimodal, "frames_from_pieces", lambda *_a, **_k: np.zeros((0, 10, 10)))
    monkeypatch.setattr(multimodal, "_audio_samples", lambda _path: np.zeros(16000))
    monkeypatch.setitem(sys.modules, "cv2", None)

    result = multimodal.analyze_short(source)

    assert result["visual"]["provider"] == "motion"  # type: ignore[index]
    assert result["audio"]["label"] == "calm"  # type: ignore[index]
    assert len(result["caveats"]) == 2  # type: ignore[arg-type]


def test_analyze_short_with_face_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "short.mp4"
    source.write_bytes(b"video")
    frames = np.zeros((3, 20, 20), dtype=np.uint8)
    monkeypatch.setattr(multimodal, "_duration_samples", lambda *_a, **_k: 8000)
    monkeypatch.setattr(multimodal, "frames_from_pieces", lambda *_a, **_k: frames)
    monkeypatch.setattr(multimodal, "_audio_samples", lambda _path: np.zeros(16000))

    class Detector:
        def detectMultiScale(
            self, *_args: object, **_kwargs: object
        ) -> list[tuple[int, int, int, int]]:
            return [(2, 2, 4, 4), (8, 2, 4, 4)]

    fake = SimpleNamespace(
        data=SimpleNamespace(haarcascades="/tmp/cascades"),
        CascadeClassifier=lambda _path: Detector(),
    )
    monkeypatch.setitem(sys.modules, "cv2", fake)

    result = multimodal.analyze_short(source)

    visual = result["visual"]
    assert visual["provider"] == "opencv_face"  # type: ignore[index]
    assert visual["face_count"] == 6  # type: ignore[index]
    assert 0.05 <= visual["face_focus_x"] <= 0.95  # type: ignore[index]


def test_analyze_short_entry_validates_the_selection(tmp_path: Path) -> None:
    with pytest.raises(ShortEditError, match="out of range"):
        multimodal.analyze_short_entry(output=tmp_path, index=0, result={})
    with pytest.raises(ShortEditError, match="out of range"):
        multimodal.analyze_short_entry(
            output=tmp_path, index=-1, result={"shorts": [{"path": "x"}]}
        )
    with pytest.raises(ShortEditError, match="asset is missing"):
        multimodal.analyze_short_entry(
            output=tmp_path, index=0, result={"shorts": [{}]}
        )


def test_analyze_short_entry_persists_the_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    short = tmp_path / "short.mp4"
    short.write_bytes(b"video")
    (tmp_path / "shorts.json").write_text(
        json.dumps({"clips": [{"title": "before"}]}), encoding="utf-8"
    )
    monkeypatch.setattr(
        multimodal, "analyze_short", lambda _path: {"label": "calm"}
    )
    result = {"shorts": [{"path": str(short), "title": "after"}]}

    analysis = multimodal.analyze_short_entry(output=tmp_path, index=0, result=result)

    assert analysis == {"label": "calm"}
    report = json.loads((tmp_path / "shorts.json").read_text(encoding="utf-8"))
    assert report["clips"][0]["analysis"] == {"label": "calm"}


def test_analyze_short_entry_requires_a_readable_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    short = tmp_path / "short.mp4"
    short.write_bytes(b"video")
    monkeypatch.setattr(multimodal, "analyze_short", lambda _path: {})

    with pytest.raises(StateNotReadyError, match="Cannot read"):
        multimodal.analyze_short_entry(
            output=tmp_path, index=0, result={"shorts": [{"path": str(short)}]}
        )


def test_analyze_short_entry_falls_back_to_the_result_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    short = tmp_path / "short.mp4"
    short.write_bytes(b"video")
    (tmp_path / "shorts.json").write_text(json.dumps({"clips": "nope"}), encoding="utf-8")
    monkeypatch.setattr(multimodal, "analyze_short", lambda _path: {})

    multimodal.analyze_short_entry(
        output=tmp_path, index=0, result={"shorts": [{"path": str(short)}]}
    )

    report = json.loads((tmp_path / "shorts.json").read_text(encoding="utf-8"))
    assert report["clips"] == [{"path": str(short), "analysis": {}}]


def test_duration_requires_ffprobe_and_parses_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(multimodal, "find_binary", lambda _name: None)
    with pytest.raises(IngestError, match="FFprobe is not available"):
        multimodal._duration_samples(tmp_path / "short.mp4", 8000)

    class Result:
        stdout = "2.5\n"

    monkeypatch.setattr(multimodal, "find_binary", lambda _name: "/usr/bin/ffprobe")
    monkeypatch.setattr(multimodal.subprocess, "run", lambda *a, **k: Result())
    assert multimodal._duration_samples(tmp_path / "short.mp4", 8000) == 20000

    class Bad:
        stdout = "not a number"

    monkeypatch.setattr(multimodal.subprocess, "run", lambda *a, **k: Bad())
    with pytest.raises(IngestError, match="Cannot determine"):
        multimodal._duration_samples(tmp_path / "short.mp4", 8000)


def test_audio_samples_decode_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(multimodal, "find_binary", lambda _name: None)
    with pytest.raises(IngestError, match="FFmpeg is not available"):
        multimodal._audio_samples(tmp_path / "short.mp4")

    class Failed:
        returncode = 1
        stdout = b""

    monkeypatch.setattr(multimodal, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(multimodal.subprocess, "run", lambda *a, **k: Failed())
    with pytest.raises(IngestError, match="Cannot decode"):
        multimodal._audio_samples(tmp_path / "short.mp4")

    class Valid:
        returncode = 0
        stdout = np.zeros(8, dtype=np.int16).tobytes()

    monkeypatch.setattr(multimodal.subprocess, "run", lambda *a, **k: Valid())
    samples = multimodal._audio_samples(tmp_path / "short.mp4")
    assert samples.dtype == np.int16
    assert len(samples) == 8
