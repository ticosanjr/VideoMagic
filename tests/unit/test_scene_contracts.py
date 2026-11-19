from __future__ import annotations

import pytest
from pydantic import ValidationError

from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan


def _scene(scene_id: str, start: int, end: int) -> dict:
    return {
        "scene_id": scene_id,
        "start_sample": start,
        "end_sample": end,
        "start_sec": start / 1000,
        "end_sec": end / 1000,
        "layout_type": "TALKING_HEAD",
        "face_count": 1,
        "face_bbox_norm": {"cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3},
        "face_area_ratio": 0.06,
        "edge_density": 0.02,
        "sharpness_laplacian": 200.0,
    }


def test_scene_manifest_accepts_ordered_scenes() -> None:
    manifest = ScenesManifest.model_validate(
        {
            "video_id": "sha",
            "resolution": {"w": 1920, "h": 1080},
            "fps_num": 30,
            "fps_den": 1,
            "scenes": [_scene("SC_0001", 0, 1000), _scene("SC_0002", 1000, 2000)],
        }
    )
    assert len(manifest.scenes) == 2


def test_scene_manifest_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        ScenesManifest.model_validate(
            {
                "video_id": "sha",
                "resolution": {"w": 1920, "h": 1080},
                "fps_num": 30,
                "fps_den": 1,
                "scenes": [_scene("SC_0001", 0, 1000), _scene("SC_0001", 1000, 2000)],
            }
        )


def _plan(segments: list[dict]) -> dict:
    return {
        "short_id": "SH_01",
        "start": 10.0,
        "end": 20.0,
        "segments": segments,
    }


def test_short_plan_requires_contiguous_coverage() -> None:
    plan = ShortCompositionPlan.model_validate(
        _plan(
            [
                {"seg_id": "S1", "rel_start": 0.0, "rel_end": 5.0, "layout": "FULL_FACE"},
                {
                    "seg_id": "S2",
                    "rel_start": 5.0,
                    "rel_end": 10.0,
                    "layout": "SPLIT_SCREEN_SAFE",
                },
            ]
        )
    )
    assert plan.duration_sec == 10.0


def test_short_plan_rejects_gap_and_short_segments() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        ShortCompositionPlan.model_validate(
            _plan(
                [
                    {"seg_id": "S1", "rel_start": 0.0, "rel_end": 4.0, "layout": "FULL_FACE"},
                    {
                        "seg_id": "S2",
                        "rel_start": 5.0,
                        "rel_end": 10.0,
                        "layout": "SPLIT_SCREEN_SAFE",
                    },
                ]
            )
        )
    with pytest.raises(ValidationError, match="2.5"):
        ShortCompositionPlan.model_validate(
            _plan(
                [
                    {"seg_id": "S1", "rel_start": 0.0, "rel_end": 1.0, "layout": "FULL_FACE"},
                    {
                        "seg_id": "S2",
                        "rel_start": 1.0,
                        "rel_end": 10.0,
                        "layout": "SPLIT_SCREEN_SAFE",
                    },
                ]
            )
        )
