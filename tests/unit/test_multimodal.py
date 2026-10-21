import numpy as np

from videoflow.application.multimodal import audio_features, motion_region


def test_audio_features_label_silence_as_calm() -> None:
    result = audio_features(np.zeros(16000, dtype=np.int16), 16000)
    assert result["label"] == "calm"
    assert result["rms"] == 0.0


def test_motion_region_tracks_the_right_side() -> None:
    frames = np.zeros((2, 36, 64), dtype=np.uint8)
    frames[1, 8:20, 48:60] = 255
    region = motion_region(frames)
    assert region is not None
    assert region["x"] > 0.6
    assert region["coverage"] > 0
