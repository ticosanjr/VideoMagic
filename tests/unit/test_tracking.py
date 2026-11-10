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
