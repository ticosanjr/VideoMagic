from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from gpu_worker import handlers_gpu  # noqa: E402
from scene_rules import classify_layout, editing_hints, sample_times  # noqa: E402

from videoflow.application.scene_intel import layout as local_layout  # noqa: E402
from videoflow.application.scene_intel import visual as local_visual  # noqa: E402
from videoflow.domain.state import MediaInfo  # noqa: E402


@pytest.mark.parametrize(
    ("face_count", "face_area", "edge", "width", "height", "topology"),
    [
        (1, 0.12, 0.01, 1920, 1080, "single_16x9"),
        (1, 0.02, 0.20, 1920, 1080, "single_16x9"),
        (0, 0.0, 0.30, 1920, 1080, "single_16x9"),
        (0, 0.0, 0.0, 3840, 1080, "dual_canvas"),
        (2, 0.0, 0.0, 1920, 1080, "single_16x9"),
    ],
)
def test_local_and_worker_classification_match(
    face_count: int,
    face_area: float,
    edge: float,
    width: int,
    height: int,
    topology: str,
) -> None:
    expected = classify_layout(
        face_count=face_count,
        face_area_ratio=face_area,
        edge_density=edge,
        width=width,
        height=height,
        topology=topology,
    )
    worker = handlers_gpu._scene_layout(
        {
            "face_count": face_count,
            "face_area_ratio": face_area,
            "edge_density": edge,
        },
        width,
        height,
        topology,
    )
    media = MediaInfo(
        source_path="x.mp4",
        width=width,
        height=height,
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        audio_sample_rate=48_000,
    )
    local = local_visual.classify_layout(
        local_visual.SceneVisual(
            face_count=face_count,
            face_area_ratio=face_area,
            edge_density=edge,
        ),
        media,
        topology,
    )
    assert worker == expected
    assert local == expected


def test_editing_hints_and_sampling_match() -> None:
    kwargs = {
        "layout": "TALKING_HEAD",
        "duration_sec": 14.0,
        "edge_density": 0.01,
        "sharpness_laplacian": 20.0,
        "previous_layout": "SCREEN_SHARE_FULL",
    }
    assert handlers_gpu._scene_hints(
        kwargs["layout"],
        kwargs["duration_sec"],
        {
            "edge_density": kwargs["edge_density"],
            "sharpness_laplacian": kwargs["sharpness_laplacian"],
        },
        kwargs["previous_layout"],
    ) == editing_hints(**kwargs) == local_layout.editing_hints(**kwargs)
    assert handlers_gpu._scene_sample_times(4.0, 10.0, max_frames=5) == sample_times(
        4.0, 10.0, max_frames=5
    )
