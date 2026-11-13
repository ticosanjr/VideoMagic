import numpy as np

from videoflow.application.tracking import focus_x_from_frames


def test_motion_centroid_tracks_the_right_side() -> None:
    frames = np.zeros((2, 36, 64), dtype=np.uint8)
    frames[1, 10:20, 48:60] = 255
    focus = focus_x_from_frames(frames)
    assert focus > 0.6


def test_static_frames_fall_back_to_center() -> None:
    frames = np.zeros((3, 36, 64), dtype=np.uint8)
    assert focus_x_from_frames(frames) == 0.5


def test_empty_frames_fall_back_to_center() -> None:
    assert focus_x_from_frames(np.empty((0, 36, 64), dtype=np.uint8)) == 0.5


def test_keyframes_smooth_the_motion_path(monkeypatch) -> None:
    from videoflow.application import tracking

    frames = np.zeros((4, 36, 64), dtype=np.uint8)
    frames[:, 10:20, 48:60] = 255
    monkeypatch.setattr(tracking, "frames_from_pieces", lambda *a, **k: frames)
    keyframes, mode = tracking.track_focus_keyframes(
        __import__("pathlib").Path("source.mp4"),
        [(0, 48000)],
        48000,
        mode="motion_tracking",
        smoothing=0.5,
    )
    assert mode == "motion_tracking"
    assert len(keyframes) == 4
    assert all(0.05 <= item["focus_x"] <= 0.95 for item in keyframes)
    assert keyframes[0]["time_sec"] == 0.0


def test_keyframes_use_face_centers_when_available(monkeypatch) -> None:
    from videoflow.application import tracking

    monkeypatch.setattr(
        tracking, "frames_from_pieces", lambda *a, **k: np.zeros((3, 36, 64), dtype=np.uint8)
    )
    monkeypatch.setattr(tracking, "_face_centers", lambda frames: [0.2, 0.8, None])
    keyframes, mode = tracking.track_focus_keyframes(
        __import__("pathlib").Path("source.mp4"),
        [(0, 48000)],
        48000,
        mode="face_tracking",
        smoothing=0.0,
    )
    assert mode == "face_tracking"
    assert keyframes[0]["focus_x"] == 0.2
    assert keyframes[1]["focus_x"] == 0.8


def test_keyframes_fall_back_when_frames_are_empty(monkeypatch) -> None:
    from videoflow.application import tracking

    monkeypatch.setattr(
        tracking, "frames_from_pieces", lambda *a, **k: np.empty((0, 36, 64), dtype=np.uint8)
    )
    keyframes, mode = tracking.track_focus_keyframes(
        __import__("pathlib").Path("source.mp4"), [(0, 1)], 48000
    )
    assert mode == "motion_tracking"
    assert keyframes == [{"time_sec": 0.0, "focus_x": 0.5}]


def test_mediapipe_backend_falls_back_when_missing(monkeypatch) -> None:
    from videoflow.application import tracking

    monkeypatch.setattr(
        tracking, "frames_from_pieces", lambda *a, **k: np.zeros((2, 36, 64), dtype=np.uint8)
    )
    monkeypatch.setattr(
        tracking,
        "_face_centers_mediapipe",
        lambda frames: (_ for _ in ()).throw(ImportError("missing")),
    )
    monkeypatch.setattr(tracking, "_motion_centers", lambda frames: [0.3, 0.6])
    keyframes, mode = tracking.track_focus_keyframes(
        __import__("pathlib").Path("source.mp4"),
        [(0, 48000)],
        48000,
        backend="mediapipe",
    )
    assert mode == "motion_tracking"
    assert keyframes[-1]["focus_x"] > 0.3


def test_face_centers_with_fake_opencv(monkeypatch) -> None:
    import sys
    from types import ModuleType, SimpleNamespace

    from videoflow.application import tracking

    cv2 = ModuleType("cv2")
    cv2.data = SimpleNamespace(haarcascades="/tmp")
    cv2.CascadeClassifier = lambda path: SimpleNamespace(
        detectMultiScale=lambda frame, **kwargs: [
            [10, 0, 20, 20],
            [30, 0, 40, 20],
        ]
    )
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    frames = np.zeros((1, 36, 64), dtype=np.uint8)
    assert tracking._face_centers(frames) == [(30 + 20) / 64]


def test_mediapipe_face_centers(monkeypatch) -> None:
    import sys
    from types import ModuleType, SimpleNamespace

    from videoflow.application import tracking

    box = SimpleNamespace(xmin=0.2, width=0.4, height=0.4)
    detection = SimpleNamespace(location_data=SimpleNamespace(relative_bounding_box=box))

    class Detector:
        def process(self, rgb):
            return SimpleNamespace(detections=[detection])

        def close(self):
            return None

    mediapipe = ModuleType("mediapipe")
    mediapipe.solutions = SimpleNamespace(  # type: ignore[attr-defined]
        face_detection=SimpleNamespace(FaceDetection=lambda **kwargs: Detector())
    )
    monkeypatch.setitem(sys.modules, "mediapipe", mediapipe)
    centers = tracking._face_centers_mediapipe(np.zeros((1, 36, 64), dtype=np.uint8))
    assert centers == [0.4]


def test_yolo_face_centers(monkeypatch, tmp_path) -> None:
    import sys
    from types import ModuleType, SimpleNamespace

    from videoflow.application import tracking

    monkeypatch.delenv("VIDEOWFLOW_YOLO_MODEL", raising=False)
    with __import__("pytest").raises(ImportError):
        tracking._face_centers_yolo(np.zeros((1, 36, 64), dtype=np.uint8))

    model = tmp_path / "model.pt"
    model.write_bytes(b"model")
    monkeypatch.setenv("VIDEOWFLOW_YOLO_MODEL", str(model))

    class Box:
        cls = [0]
        xyxy = [[10, 0, 20, 20]]

    ultralytics = ModuleType("ultralytics")
    ultralytics.YOLO = lambda path: SimpleNamespace(  # type: ignore[attr-defined]
        predict=lambda image, verbose=False: [SimpleNamespace(boxes=[Box()])]
    )
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics)
    centers = tracking._face_centers_yolo(np.zeros((1, 36, 64), dtype=np.uint8))
    assert centers == [15 / 64]


def test_motion_centers_and_face_focus(monkeypatch) -> None:
    import sys
    from types import ModuleType, SimpleNamespace

    from videoflow.application import tracking

    assert tracking._motion_centers(np.zeros((1, 36, 64), dtype=np.uint8)) == [None]
    frames = np.zeros((2, 36, 64), dtype=np.uint8)
    frames[1, 10:20, 48:60] = 255
    assert tracking._motion_centers(frames)[1] > 0.6

    cv2 = ModuleType("cv2")
    cv2.data = SimpleNamespace(haarcascades="/tmp")
    cv2.CascadeClassifier = lambda path: SimpleNamespace(
        detectMultiScale=lambda frame, **kwargs: [[10, 0, 20, 20]]
    )
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    frames = np.zeros((2, 36, 64), dtype=np.uint8)
    assert tracking._face_focus(frames) == (10 + 10) / 64


def test_frames_from_pieces(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    import pytest

    from videoflow.application import tracking
    from videoflow.domain.errors import IngestError

    monkeypatch.setattr(tracking, "find_binary", lambda name: None)
    with pytest.raises(IngestError):
        tracking.frames_from_pieces(tmp_path / "source.mp4", [(0, 100)], 1000)

    monkeypatch.setattr(tracking, "find_binary", lambda name: "ffmpeg")
    raw = bytes([10] * (2 * 36 * 64))
    monkeypatch.setattr(
        tracking.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=raw),
    )
    frames = tracking.frames_from_pieces(tmp_path / "source.mp4", [(0, 100)], 1000)
    assert frames.shape == (2, 36, 64)

    monkeypatch.setattr(
        tracking.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=b""),
    )
    assert tracking.frames_from_pieces(tmp_path / "source.mp4", [(0, 100)], 1000).shape == (
        0,
        36,
        64,
    )
