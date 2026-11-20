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
        backend="opencv_haar",
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
        predict=lambda image, **kwargs: [SimpleNamespace(boxes=[Box()])]
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


def test_resolve_tracking_backend_prefers_mediapipe_then_yolo_then_opencv(monkeypatch) -> None:
    from types import SimpleNamespace

    from videoflow.application import vision_backends

    settings = SimpleNamespace(vision=SimpleNamespace(tracking_backend="auto", yolo_model=""))
    monkeypatch.setattr(vision_backends, "mediapipe_ready", lambda model="": True)
    assert (
        vision_backends.resolve_tracking_backend("auto", "face_tracking", settings=settings)[0]
        == "mediapipe"
    )

    monkeypatch.setattr(vision_backends, "mediapipe_ready", lambda model="": False)
    monkeypatch.setattr(vision_backends, "mediapipe_available", lambda: False)
    monkeypatch.setattr(vision_backends, "yolo_available", lambda model="": True)
    assert (
        vision_backends.resolve_tracking_backend("auto", "face_tracking", settings=settings)[0]
        == "yolo"
    )

    monkeypatch.setattr(vision_backends, "yolo_available", lambda model="": False)
    monkeypatch.setattr(vision_backends, "opencv_available", lambda: True)
    assert (
        vision_backends.resolve_tracking_backend("auto", "face_tracking", settings=settings)[0]
        == "opencv_haar"
    )

    monkeypatch.setattr(vision_backends, "opencv_available", lambda: False)
    backend, reason = vision_backends.resolve_tracking_backend(
        "auto", "face_tracking", settings=settings
    )
    assert backend == "motion_tracking"
    assert "no face backend" in reason


def test_fill_gaps_interpolates_and_clamps() -> None:
    from videoflow.application.tracking import _fill_gaps

    assert _fill_gaps([0.2, None, 0.8, None]) == [0.2, 0.5, 0.8, 0.8]
    assert _fill_gaps([None, None]) == [0.5, 0.5]


def test_track_focus_reports_mediapipe_backend(monkeypatch) -> None:
    from pathlib import Path

    from videoflow.application import tracking

    monkeypatch.setattr(
        tracking, "frames_from_pieces", lambda *a, **k: np.zeros((2, 144, 256), dtype=np.uint8)
    )
    monkeypatch.setattr(tracking, "resolve_tracking_backend", lambda *a, **k: ("mediapipe", "ok"))
    monkeypatch.setattr(tracking, "_face_centers_mediapipe", lambda frames, **kwargs: [0.2, 0.8])
    result = tracking.track_focus(
        Path("source.mp4"), [(0, 48000)], 48000, mode="face_tracking", smoothing=0.0
    )
    assert result.backend == "mediapipe"
    assert result.requested == "auto"
    assert result.detections == 2
    assert result.keyframes[0]["focus_x"] == 0.2


def test_vision_backend_model_and_explicit_fallbacks(monkeypatch, tmp_path) -> None:
    from videoflow.application import vision_backends

    model = tmp_path / "face.pt"
    model.write_bytes(b"model")
    monkeypatch.setenv("VIDEOWFLOW_YOLO_MODEL", str(model))
    assert vision_backends.yolo_model_path() == str(model)
    assert vision_backends.mediapipe_model_selection(0) == 0
    assert vision_backends.mediapipe_model_selection(1) == 1

    monkeypatch.setattr(vision_backends, "mediapipe_available", lambda: False)
    assert vision_backends.resolve_tracking_backend("mediapipe", "face_tracking")[0] == (
        "motion_tracking"
    )
    monkeypatch.setattr(vision_backends, "yolo_available", lambda model="": False)
    assert vision_backends.resolve_tracking_backend("yolo", "face_tracking")[0] == (
        "motion_tracking"
    )
    monkeypatch.setattr(vision_backends, "opencv_available", lambda: False)
    assert vision_backends.resolve_tracking_backend("opencv_haar", "face_tracking")[0] == (
        "motion_tracking"
    )
    assert vision_backends.resolve_tracking_backend("motion", "face_tracking")[0] == (
        "motion_tracking"
    )
    assert vision_backends.resolve_tracking_backend("weird", "face_tracking")[0] == (
        "motion_tracking"
    )


def test_tracking_face_backends_skip_empty_detections(monkeypatch) -> None:
    from videoflow.application import tracking

    monkeypatch.setattr(tracking, "resolve_tracking_backend", lambda *a, **k: ("mediapipe", "ok"))
    monkeypatch.setattr(
        tracking, "frames_from_pieces", lambda *a, **k: np.zeros((2, 36, 64), dtype=np.uint8)
    )
    monkeypatch.setattr(tracking, "_face_centers_mediapipe", lambda *a, **k: [None, None])
    monkeypatch.setattr(tracking, "_motion_centers", lambda frames: [0.2, 0.8])
    result = tracking.track_focus(__import__("pathlib").Path("x"), [(0, 1)], 1)
    assert result.backend == "motion_tracking"
    assert result.detections == 2

    monkeypatch.setattr(tracking, "resolve_tracking_backend", lambda *a, **k: ("yolo", "ok"))
    monkeypatch.setattr(
        tracking,
        "_face_centers_yolo",
        lambda *a, **k: (_ for _ in ()).throw(ImportError("missing")),
    )
    result = tracking.track_focus(__import__("pathlib").Path("x"), [(0, 1)], 1)
    assert result.backend == "motion_tracking"
    assert "yolo failed" in result.reason


def test_face_center_helpers_handle_empty_frames(monkeypatch) -> None:
    from videoflow.application import tracking

    assert tracking._face_centers(np.empty((0, 36, 64), dtype=np.uint8)) == []


def test_mediapipe_model_path_from_env_and_availability(monkeypatch, tmp_path) -> None:
    from videoflow.application import vision_backends

    model = tmp_path / "face.tflite"
    model.write_bytes(b"model")
    monkeypatch.setenv("VIDEOWFLOW_MEDIAPIPE_MODEL", str(model))
    assert vision_backends.mediapipe_model_path() == str(model)

    monkeypatch.setattr(vision_backends, "mediapipe_available", lambda: True)
    monkeypatch.setattr(vision_backends, "mediapipe_legacy_available", lambda: False)
    assert vision_backends.mediapipe_ready() is True
    backend, reason = vision_backends.resolve_tracking_backend("mediapipe", "face_tracking")
    assert backend == "mediapipe" and reason == "requested mediapipe"

    monkeypatch.delenv("VIDEOWFLOW_MEDIAPIPE_MODEL")
    monkeypatch.setattr(
        vision_backends,
        "mediapipe_model_path",
        lambda explicit="": "",
    )
    assert vision_backends.mediapipe_ready() is False
    backend, reason = vision_backends.resolve_tracking_backend("mediapipe", "face_tracking")
    assert backend == "motion_tracking"
    assert "Tasks face model" in reason


def test_mediapipe_tasks_backend_with_fake_module(monkeypatch, tmp_path) -> None:
    import sys
    from types import ModuleType, SimpleNamespace

    from videoflow.application import tracking

    model = tmp_path / "face.tflite"
    model.write_bytes(b"model")

    class FakeImage:
        def __init__(self, image_format=None, data=None) -> None:
            self.image_format = image_format
            self.data = data

    class FakeDetector:
        @staticmethod
        def create_from_options(options):
            return FakeDetector()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def detect(self, image):
            assert image.data.ndim == 3
            return SimpleNamespace(
                detections=[
                    SimpleNamespace(
                        bounding_box=SimpleNamespace(origin_x=10, origin_y=0, width=100, height=50)
                    )
                ]
            )

    mediapipe = ModuleType("mediapipe")
    mediapipe.Image = FakeImage  # type: ignore[attr-defined]
    mediapipe.ImageFormat = SimpleNamespace(SRGB="SRGB")  # type: ignore[attr-defined]
    tasks = ModuleType("mediapipe.tasks")
    tasks_python = ModuleType("mediapipe.tasks.python")
    tasks_python.BaseOptions = lambda **kwargs: SimpleNamespace(**kwargs)  # type: ignore[attr-defined]
    vision = ModuleType("mediapipe.tasks.python.vision")
    vision.FaceDetectorOptions = lambda **kwargs: SimpleNamespace(**kwargs)  # type: ignore[attr-defined]
    vision.FaceDetector = FakeDetector  # type: ignore[attr-defined]
    tasks.python = tasks_python  # type: ignore[attr-defined]
    tasks_python.vision = vision  # type: ignore[attr-defined]
    for name, module in {
        "mediapipe": mediapipe,
        "mediapipe.tasks": tasks,
        "mediapipe.tasks.python": tasks_python,
        "mediapipe.tasks.python.vision": vision,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    centers = tracking._face_centers_mediapipe(
        np.zeros((1, 100, 200, 3), dtype=np.uint8), model_path=str(model)
    )
    assert centers == [0.3]


def test_motion_centers_accept_color_frames() -> None:
    from videoflow.application import tracking

    frames = np.zeros((3, 36, 64, 3), dtype=np.uint8)
    frames[:, :, 10:20, :] = 255
    frames[1:, :, 10:20, :] = 0
    centers = tracking._motion_centers(frames)
    assert len(centers) == 3
    assert centers[0] is None
    assert centers[1] is not None and 0.0 <= centers[1] <= 1.0


def test_mediapipe_model_path_uses_model_catalog(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from videoflow.application import models, settings, vision_backends

    model = tmp_path / "blaze_face_short_range.tflite"
    model.write_bytes(b"model")
    monkeypatch.delenv("VIDEOWFLOW_MEDIAPIPE_MODEL", raising=False)
    monkeypatch.setattr(
        settings,
        "load_settings",
        lambda: SimpleNamespace(vision=SimpleNamespace(mediapipe_model_path="")),
    )
    monkeypatch.setattr(
        models,
        "installed_path",
        lambda model_id: model if model_id == "mediapipe-face-detector" else None,
    )

    assert vision_backends.mediapipe_model_path() == str(model)


def test_opencv_tracking_samples_wide_gray_frames(monkeypatch) -> None:
    from pathlib import Path

    from videoflow.application import tracking

    seen: dict[str, object] = {}

    def fake_frames(*args, **kwargs):
        seen.update(kwargs)
        return np.zeros((2, 144, 256), dtype=np.uint8)

    monkeypatch.setattr(tracking, "frames_from_pieces", fake_frames)
    monkeypatch.setattr(tracking, "resolve_tracking_backend", lambda *a, **k: ("opencv_haar", "ok"))
    monkeypatch.setattr(tracking, "_face_centers", lambda frames: [0.4, 0.6])

    result = tracking.track_focus(Path("x.mp4"), [(0, 1)], 1, smoothing=0.0)

    assert seen["width"] == 256
    assert seen["height"] == 144
    assert seen["color"] is False
    assert result.backend == "opencv_haar"
    assert result.detections == 2
    assert [item["focus_x"] for item in result.keyframes] == [0.4, 0.6]


def test_fill_gaps_handles_leading_and_multiple_gaps() -> None:
    from videoflow.application.tracking import _fill_gaps

    assert np.allclose(
        _fill_gaps([None, 0.2, None, None, 0.8, None]),
        [0.2, 0.2, 0.4, 0.6, 0.8, 0.8],
    )


def test_yolo_model_is_loaded_once_per_path(monkeypatch, tmp_path) -> None:
    import sys
    from types import ModuleType, SimpleNamespace

    from videoflow.application import tracking

    model = tmp_path / "model.pt"
    model.write_bytes(b"model")
    monkeypatch.setenv("VIDEOWFLOW_YOLO_MODEL", str(model))
    loaded: list[str] = []

    class Model:
        def predict(self, image, **kwargs):
            return [SimpleNamespace(boxes=[])]

    def yolo(path):
        loaded.append(path)
        return Model()

    ultralytics = ModuleType("ultralytics")
    ultralytics.YOLO = yolo  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics)
    tracking._load_yolo_model.cache_clear()

    frames = np.zeros((1, 36, 64), dtype=np.uint8)
    assert tracking._face_centers_yolo(frames) == [None]
    assert tracking._face_centers_yolo(frames) == [None]
    assert loaded == [str(model)]
