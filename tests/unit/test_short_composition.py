from __future__ import annotations

import json

import pytest

from videoflow.application.short_composition.broll import (
    broll_fallback,
    normalize_filter,
    validate_broll,
)
from videoflow.application.short_composition.geometry import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CONTENT_REGION,
    LAYOUTS,
    SAFE_ZONES,
    FaceBox,
    caption_region,
    captions_are_safe,
    crop_for_panel,
    low_resolution,
    upscale_ratio,
)
from videoflow.application.short_composition.plan import resolve_draft
from videoflow.application.short_composition.planner import (
    build_llm_request,
    default_window,
    deterministic_draft,
    parse_llm_response,
)
from videoflow.application.short_composition.tracking import (
    needs_smoothing,
    scene_crop_samples,
    smooth_series,
    static_crop,
)
from videoflow.application.short_composition.validate import validate_plan
from videoflow.domain.errors import ShortPlanError
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.domain.short_composition import (
    BrollSource,
    ShortCompositionDraft,
    ShortSegment,
    ShortSegmentDraft,
)


def _scene(
    scene_id: str,
    start: float,
    end: float,
    layout: str,
    *,
    face: bool = True,
    hints: list[str] | None = None,
) -> SceneEntry:
    return SceneEntry(
        scene_id=scene_id,
        start_sample=round(start * 48_000),
        end_sample=round(end * 48_000),
        start_sec=start,
        end_sec=end,
        layout_type=layout,  # type: ignore[arg-type]
        face_count=1 if face else 0,
        face_bbox_norm=(
            {"cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3} if face else None
        ),
        face_area_ratio=0.06 if face else 0.0,
        edge_density=0.2 if layout.startswith("SCREEN") else 0.02,
        sharpness_laplacian=120.0,
        editing_hints=hints or [],
    )


def _manifest(width: int = 1920, height: int = 1080) -> ScenesManifest:
    return ScenesManifest(
        video_id="sha",
        resolution={"w": width, "h": height},
        fps_num=30,
        fps_den=1,
        scenes=[
            _scene("SC_0001", 0.0, 8.0, "TALKING_HEAD", hints=["SAFE_FOR_BROLL"]),
            _scene(
                "SC_0002",
                8.0,
                20.0,
                "SCREEN_SHARE_PIP",
                hints=["PROTECT_FROM_BROLL"],
            ),
            _scene("SC_0003", 20.0, 30.0, "TALKING_HEAD", hints=["SAFE_FOR_BROLL"]),
        ],
    )


def _draft(segments: list[dict], *, start: float = 0.0, end: float = 30.0) -> ShortCompositionDraft:
    return ShortCompositionDraft(
        short_id="SH",
        start=start,
        end=end,
        segments=[ShortSegmentDraft.model_validate(item) for item in segments],
    )


def test_layouts_and_safe_zones_are_consistent() -> None:
    assert set(LAYOUTS) == {
        "FULL_FACE",
        "SPLIT_BROLL",
        "SPLIT_SCREEN_SAFE",
        "SPLIT_SCREEN_FILL",
    }
    assert SAFE_ZONES["shorts_bottom"].y == 1540
    assert SAFE_ZONES["shorts_right"].x == 940
    assert CONTENT_REGION.right == 940
    for layout in LAYOUTS:
        caption = caption_region(layout)
        assert caption.right < CANVAS_WIDTH
        assert caption.bottom < CANVAS_HEIGHT
        assert captions_are_safe(layout)


def test_crop_geometry_uses_headroom_and_clamps() -> None:
    from videoflow.application.short_composition.plan import camera_size

    dual = _manifest()
    dual = dual.model_copy(
        update={"source_topology": "dual_canvas", "resolution": {"w": 3840, "h": 1080}}
    )
    assert camera_size(dual) == (1920, 1080)
    panel = LAYOUTS["FULL_FACE"].face
    face = FaceBox(cx=0.2, cy=0.2, w=0.2, h=0.3)
    crop = crop_for_panel(cam_w=1920, cam_h=1080, panel=panel, face=face, zoom=1.0)
    assert crop.width == round(1080 * 0.5625)
    assert crop.height == 1080
    assert crop.x == 80
    assert crop.y == 0  # headroom pushes against the top edge
    assert crop.right <= 1920
    assert crop.bottom <= 1080
    assert upscale_ratio(crop.width) > 1.0
    assert low_resolution(crop.width, max_ratio=5.0) is False

    centered = crop_for_panel(
        cam_w=1920, cam_h=1080, panel=panel, face=FaceBox(0.5, 0.5, 0.2, 0.3)
    )
    assert centered.x == (1920 - centered.width) // 2
    assert crop_for_panel(
        cam_w=1920, cam_h=1080, panel=panel, face=FaceBox(0.02, 0.5, 0.2, 0.3)
    ).x == 0
    portrait = crop_for_panel(
        cam_w=1080,
        cam_h=1920,
        panel=LAYOUTS["SPLIT_SCREEN_SAFE"].face,
        face=FaceBox(0.5, 0.4, 0.2, 0.3),
    )
    assert portrait.height < 1920
    assert portrait.y == round(0.4 * 1920 - portrait.height * 0.38)


def test_broll_validation_and_filter() -> None:
    missing = validate_broll(BrollSource(path="/nope/clip.mp4"))
    assert missing.ok is False
    assert "missing" in missing.reason
    stock = validate_broll(BrollSource(type="stock", fallback_query="office"))
    assert stock.ok is True
    assert validate_broll(None).ok is False
    assert normalize_filter(width=1080, height=960, fps=30) == (
        "fps=30,scale=1080:960:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=1080:960,setsar=1,format=yuv420p"
    )
    fallback = broll_fallback(
        ShortSegment(seg_id="S1", rel_start=0, rel_end=5, layout="SPLIT_BROLL")
    )
    assert fallback.layout == "FULL_FACE"
    assert fallback.face_zoom == 1.12


def test_tracking_smooths_noise_and_keeps_median() -> None:
    smoothed = smooth_series([0.2, 0.21, 0.5, 0.5], deadzone_px=0.02, alpha=0.5)
    assert smoothed[1] == smoothed[0]
    assert smoothed[2] > smoothed[1]
    assert needs_smoothing([0.1, 0.2, 0.3]) is True
    assert needs_smoothing([0.5, 0.5, 0.5]) is False
    samples = scene_crop_samples(
        [
            {"start_sec": 0.0, "face_bbox_norm": {"cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3}},
            {"start_sec": 1.0, "face_bbox_norm": {"cx": 0.2, "cy": 0.4, "w": 0.2, "h": 0.3}},
            {"start_sec": 2.0, "face_bbox_norm": {"cx": 0.8, "cy": 0.4, "w": 0.2, "h": 0.3}},
        ],
        cam_w=1920,
        cam_h=1080,
        layout="SPLIT_BROLL",
        smooth=True,
    )
    median = static_crop(samples)
    assert median is not None
    assert 0 <= median.x <= 1920 - median.width


def test_resolution_fills_gaps_and_blocks_protected_broll() -> None:
    manifest = _manifest()
    draft = _draft(
        [
            {
                "seg_id": "S1",
                "rel_start": 0.0,
                "rel_end": 8.0,
                "layout": "FULL_FACE",
                "start_scene_id": "SC_0001",
                "end_scene_id": "SC_0001",
            },
            {
                "seg_id": "S2",
                "rel_start": 10.0,
                "rel_end": 20.0,
                "layout": "SPLIT_BROLL",
                "broll_source": {"path": "/tmp/clip.mp4"},
                "start_scene_id": "SC_0002",
                "end_scene_id": "SC_0002",
            },
            {
                "seg_id": "S3",
                "rel_start": 20.0,
                "rel_end": 30.0,
                "layout": "FULL_FACE",
                "start_scene_id": "SC_0003",
                "end_scene_id": "SC_0003",
            },
        ]
    )
    result = resolve_draft(draft, manifest, broll_exists=lambda path: True)
    assert [segment.rel_start for segment in result.plan.segments] == [0.0, 10.0, 20.0]
    assert result.plan.segments[1].layout == "SPLIT_SCREEN_SAFE"
    assert any("protected" in warning for warning in result.warnings)
    assert result.plan.segments[1].broll_source is None
    assert result.crops["S2"].static.width > 0
    validation = validate_plan(result.plan, manifest)
    assert validation["ok"] is True


def test_resolution_merges_short_segments() -> None:
    manifest = _manifest()
    draft = _draft(
        [
            {"seg_id": "S1", "rel_start": 0.0, "rel_end": 2.0, "layout": "FULL_FACE"},
            {"seg_id": "S2", "rel_start": 2.0, "rel_end": 10.0, "layout": "FULL_FACE"},
            {"seg_id": "S3", "rel_start": 10.0, "rel_end": 30.0, "layout": "FULL_FACE"},
        ]
    )
    result = resolve_draft(draft, manifest)
    assert [segment.seg_id for segment in result.plan.segments] == ["S2", "S3"]
    assert result.plan.segments[0].rel_start == 0.0
    assert any("merged" in warning for warning in result.warnings)


def test_resolution_rejects_overlap_and_unknown_scene() -> None:
    manifest = _manifest()
    overlapping = _draft(
        [
            {"seg_id": "S1", "rel_start": 0.0, "rel_end": 12.0, "layout": "FULL_FACE"},
            {"seg_id": "S2", "rel_start": 10.0, "rel_end": 30.0, "layout": "FULL_FACE"},
        ]
    )
    with pytest.raises(ShortPlanError, match="overlap"):
        resolve_draft(overlapping, manifest)
    unknown = _draft(
        [
            {
                "seg_id": "S1",
                "start_scene_id": "SC_9999",
                "end_scene_id": "SC_9999",
                "layout": "FULL_FACE",
            }
        ],
        end=10.0,
    )
    with pytest.raises(ShortPlanError, match="unknown scene"):
        resolve_draft(unknown, manifest)


def test_resolution_falls_back_when_broll_is_missing() -> None:
    manifest = _manifest()
    draft = _draft(
        [
            {
                "seg_id": "S1",
                "rel_start": 0.0,
                "rel_end": 8.0,
                "layout": "SPLIT_BROLL",
                "broll_source": {"path": "/missing/clip.mp4"},
            }
        ],
        end=8.0,
    )
    result = resolve_draft(draft, manifest, broll_exists=lambda path: False)
    assert result.plan.segments[0].layout == "FULL_FACE"
    assert any("B-roll unavailable" in warning for warning in result.warnings)


def test_low_resolution_split_falls_back() -> None:
    manifest = _manifest(width=480, height=270)
    draft = _draft(
        [
            {
                "seg_id": "S1",
                "rel_start": 0.0,
                "rel_end": 30.0,
                "layout": "SPLIT_SCREEN_SAFE",
            }
        ]
    )
    result = resolve_draft(draft, manifest)
    assert result.plan.segments[0].layout == "FULL_FACE"
    assert any("PIP_LOW_RES_WARNING" in warning for warning in result.warnings)


def test_deterministic_planner_maps_scene_layouts() -> None:
    manifest = _manifest()
    draft = deterministic_draft(manifest, short_id="SH", start_sec=0, end_sec=30)
    layouts = [segment.layout for segment in draft.segments]
    assert layouts == ["FULL_FACE", "SPLIT_SCREEN_SAFE", "FULL_FACE"]
    assert all(segment.broll_source is None for segment in draft.segments)
    result = resolve_draft(draft, manifest)
    assert result.plan.duration_sec == 30.0
    assert result.plan.segments[-1].rel_end == 30.0

    start, end = default_window(manifest, max_sec=10)
    assert start == 0.0
    assert end == 10.0


def test_llm_request_has_no_absolute_timestamps() -> None:
    request = build_llm_request(
        {
            "source_topology": "single_16x9",
            "scenes": [
                {
                    "scene_id": "SC_0001",
                    "layout_type": "TALKING_HEAD",
                    "duration_sec": 8.0,
                    "start_sec": 0.0,
                    "end_sec": 8.0,
                    "editing_hints": ["SAFE_FOR_BROLL"],
                    "protected_from_broll": False,
                }
            ],
            "asus": [
                {
                    "asu_id": "A1",
                    "scene_id": "SC_0001",
                    "text": "hello",
                    "duration_sec": 2.0,
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "broll_allowed": True,
                }
            ],
        },
        short_id="SH",
        start_sec=0.0,
        end_sec=8.0,
    )
    assert "start_sec" not in json.dumps(request["scenes"])
    assert "start_sec" not in json.dumps(request["asus"])
    parsed = parse_llm_response(
        {
            "short_id": "SH",
            "segments": [
                {
                    "seg_id": "S1",
                    "start_scene_id": "SC_0001",
                    "end_scene_id": "SC_0001",
                    "layout": "FULL_FACE",
                }
            ],
        },
        short_id="SH",
        start_sec=0.0,
        end_sec=8.0,
    )
    assert parsed.segments[0].start_scene_id == "SC_0001"


def test_short_plan_rejects_unsafe_short_id() -> None:
    from videoflow.domain.short_composition import ShortCompositionPlan

    with pytest.raises(ValueError):
        ShortCompositionPlan(
            short_id="../escape",
            start=0.0,
            end=5.0,
            segments=[{"seg_id": "S1", "rel_start": 0.0, "rel_end": 5.0, "layout": "FULL_FACE"}],
        )


def test_render_split_broll_without_asset_falls_back() -> None:
    from videoflow.application.short_composition.render import build_segment_renders

    manifest = _manifest()
    plan = _draft(
        [
            {
                "seg_id": "S1",
                "rel_start": 0.0,
                "rel_end": 8.0,
                "layout": "SPLIT_BROLL",
                "broll_source": {"path": "/tmp/clip.mp4"},
            }
        ],
        end=8.0,
    )
    resolved = resolve_draft(plan, manifest, broll_exists=lambda path: True).plan
    renders = build_segment_renders(resolved, manifest, broll_paths={})
    assert renders[0].layout == "FULL_FACE"
    assert renders[0].broll_path is None
