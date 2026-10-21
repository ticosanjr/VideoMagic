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
