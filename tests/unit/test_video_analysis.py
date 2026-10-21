from videoflow.application.video_analysis import parse_scene_times, scene_intervals


def test_scene_times_are_parsed_and_deduplicated() -> None:
    log = "showinfo pts_time:1.250\nnoise\nshowinfo pts_time:3.5\nshowinfo pts_time:1.25"
    assert parse_scene_times(log) == [1.25, 3.5]


def test_scene_intervals_are_centered_and_clamped() -> None:
    intervals = scene_intervals([0.0, 2.0], sample_rate=1000, window_sec=0.5)
    assert intervals == [(0, 500), (1500, 2500)]
