from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application.short_composition.geometry import CanvasRegion
from videoflow.application.short_composition.plan import resolve_draft
from videoflow.application.short_composition.planner import deterministic_draft
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import NeedsReviewError
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan
from videoflow.exporters.short_fcpxml import (
    CaptionClip,
    FaceClip,
    SfxClip,
    export_short_fcpxml,
    generate_face_clips,
    validate_short_fcpxml,
)
from videoflow.steps.base import StepIO
from videoflow.steps.short_export import ShortExportParams, ShortExportStep
from videoflow.steps.short_qa import ShortQaParams, ShortQaStep


def _manifest() -> ScenesManifest:
    def scene(scene_id: str, start: float, end: float, layout: str, hints: list[str]):
        return SceneEntry(
            scene_id=scene_id,
            start_sample=round(start * 48_000),
            end_sample=round(end * 48_000),
            start_sec=start,
            end_sec=end,
            layout_type=layout,  # type: ignore[arg-type]
            face_count=1,
            face_bbox_norm={"cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3},
            face_area_ratio=0.06,
            edge_density=0.2 if layout.startswith("SCREEN") else 0.02,
            sharpness_laplacian=120.0,
            editing_hints=hints,
        )

    return ScenesManifest(
        video_id="sha",
        resolution={"w": 1920, "h": 1080},
        fps_num=30,
        fps_den=1,
        scenes=[
            scene("SC_0001", 0.0, 8.0, "TALKING_HEAD", ["SAFE_FOR_BROLL"]),
            scene("SC_0002", 8.0, 20.0, "SCREEN_SHARE_PIP", ["PROTECT_FROM_BROLL"]),
            scene("SC_0003", 20.0, 30.0, "TALKING_HEAD", ["SAFE_FOR_BROLL"]),
        ],
    )


def _plan() -> ShortCompositionPlan:
    manifest = _manifest()
    draft = deterministic_draft(manifest, short_id="SH", start_sec=0, end_sec=30)
    return resolve_draft(draft, manifest).plan


def _files(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source.mp4"
    final = tmp_path / "short.mp4"
    source.write_bytes(b"src")
    final.write_bytes(b"mp4")
    return source, final


def test_fcpxml_has_v1_v2_a1_a2_lanes(tmp_path: Path) -> None:
    source, final = _files(tmp_path)
    face = tmp_path / "face_0001.mp4"
    sfx = tmp_path / "whoosh.wav"
    face.write_bytes(b"face")
    sfx.write_bytes(b"wav")
    xml_path = export_short_fcpxml(
        _plan(),
        tmp_path / "short.fcpxml",
        final_video=final,
        source=source,
        face_clips=[
            FaceClip(
                seg_id="S1",
                path=face,
                offset_sec=0.0,
                duration_sec=8.0,
                panel=CanvasRegion(0, 0, 1080, 1920),
            ),
            FaceClip(
                seg_id="S2",
                path=face,
                offset_sec=8.0,
                duration_sec=12.0,
                panel=CanvasRegion(0, 840, 1080, 700),
            ),
        ],
        sfx=[SfxClip(path=sfx, offset_sec=8.0, duration_sec=0.6)],
        captions=[
            CaptionClip(0.5, 2.5, "hello world", 1360),
        ],
        source_duration=30.0,
        duration_sec=30.35,
        fps=30,
    )
    root = ET.parse(xml_path).getroot()
    assert root.get("version") == "1.10"
    spine = root.find(".//spine")
    assert spine is not None
    lanes = {clip.get("lane", "0") for clip in spine}
    assert {"0", "1", "-1", "-2", "6"} <= lanes
    clips = spine.findall("asset-clip")
    face_clip = next(clip for clip in clips if clip.get("lane") == "1")
    transform = face_clip.find("adjust-transform")
    assert transform is not None
    positions = [
        clip.find("adjust-transform").get("position")
        for clip in clips
        if clip.get("lane") == "1"
    ]
    assert positions == ["0 0", "0 -230"]
    voice = next(clip for clip in clips if clip.get("lane") == "-1")
    assert voice.get("audioRole") == "dialogue"
    assert voice.get("offset") == "0/1s"
    sfx_clip = next(clip for clip in clips if clip.get("lane") == "-2")
    assert sfx_clip.get("audioRole") == "effects"
    assert len(spine.findall("title")) == 1
    assert len(root.findall(".//marker")) == 2

    validation = validate_short_fcpxml(xml_path)
    assert validation["ok"] is True
    assert validation["media_count"] == 4
    assert validation["lanes"] == ["-1", "-2", "0", "1", "6"]


def test_fcpxml_detects_offline_media_and_missing_lane(tmp_path: Path) -> None:
    source, final = _files(tmp_path)
    xml_path = export_short_fcpxml(
        _plan(),
        tmp_path / "broken.fcpxml",
        final_video=final,
        source=source,
        duration_sec=30.35,
    )
    validation = validate_short_fcpxml(xml_path)
    assert validation["ok"] is False
    assert any("missing expected lanes" in item for item in validation["errors"])
    final.unlink()
    validation = validate_short_fcpxml(xml_path)
    assert any("offline media" in item for item in validation["errors"])


def test_generate_face_clips_uses_panel_geometry(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.short_composition.render import build_segment_renders

    source, _final = _files(tmp_path)
    renders = build_segment_renders(_plan(), _manifest())
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        Path(argv[-1]).write_bytes(b"face")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("subprocess.run", fake_run)
    clips, warnings = generate_face_clips(
        renders,
        source,
        tmp_path / "face",
        fps=30,
        offset_base=0.0,
    )
    assert warnings == []
    assert len(clips) == len(renders)
    assert "crop=" in calls[0][calls[0].index("-vf") + 1]
    assert clips[1].panel.height == 700


def _context(tmp_path: Path) -> tuple[PipelineContext, ShortCompositionPlan, Path]:
    manifest = _manifest()
    plan = _plan()
    source, final = _files(tmp_path)
    output = tmp_path / "out"
    context = PipelineContext(
        source=source,
        output=output,
        work=tmp_path / "work",
        exports=tmp_path / "exports",
    )
    context.metadata["short_plan"] = plan.model_dump(mode="json")
    context.metadata["scenes_manifest"] = manifest.model_dump(mode="json")
    context.metadata["short_cues"] = {
        "captions": [
            {
                "start": 0.5,
                "end": 2.5,
                "text": "hello world",
                "lines": ["hello world"],
                "layout": "FULL_FACE",
                "subtitle_y": 1360,
            }
        ],
        "ending": {
            "content_end_sec": 30.0,
            "effective_end_sec": 30.35,
            "fade_out_ms": 80,
        },
        "sfx": [],
        "warnings": [],
    }
    context.artifacts["short_render"] = str(final)
    return context, plan, final


def test_short_export_step_writes_report(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps import short_export as step_module

    context, plan, final = _context(tmp_path)
    face = tmp_path / "face.mp4"
    face.write_bytes(b"face")

    def fake_face_clips(*args, **kwargs):
        return (
            [
                FaceClip(
                    seg_id=segment.seg_id,
                    path=face,
                    offset_sec=segment.rel_start,
                    duration_sec=segment.rel_end - segment.rel_start,
                    panel=CanvasRegion(0, 0, 1080, 1920),
                )
                for segment in plan.segments
            ],
            [],
        )

    monkeypatch.setattr(step_module, "generate_face_clips", fake_face_clips)
    ShortExportStep().run(context, ShortExportParams(), StepIO())
    report = context.metadata["short_export"]
    assert report["ok"] is True
    assert report["tracks"]["V2"] == 3
    assert Path(context.artifacts["short_fcpxml"]).is_file()
    assert Path(context.artifacts["short_export_report"]).is_file()


def test_short_export_strict_requires_rendered_video(tmp_path: Path) -> None:
    context, _plan, final = _context(tmp_path)
    final.unlink()
    with pytest.raises(Exception, match="short.render"):
        ShortExportStep().run(context, ShortExportParams(), StepIO())


def test_short_qa_passes_and_flags_bad_captions(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps import short_qa as qa_module

    context, _plan, final = _context(tmp_path)
    context.artifacts["short_export_report"] = str(tmp_path / "export.json")
    (tmp_path / "export.json").write_text(
        json.dumps(
            {
                "ok": True,
                "errors": [],
                "warnings": [],
                "face_clips": ["face.mp4"],
                "sfx": [],
            }
        ),
        encoding="utf-8",
    )
    context.artifacts["short_cues"] = str(tmp_path / "cues.json")
    (tmp_path / "cues.json").write_text(
        json.dumps(context.metadata["short_cues"]), encoding="utf-8"
    )
    monkeypatch.setattr(
        qa_module,
        "FFmpegAdapter",
        lambda: SimpleNamespace(
            probe=lambda path: SimpleNamespace(
                width=1080, height=1920, duration_frames=910, fps_den=1, fps_num=30
            )
        ),
    )
    ShortQaStep().run(context, ShortQaParams(), StepIO())
    assert context.metadata["short_qa"]["ok"] is True
    assert context.metadata["short_qa"]["tracks"]["V2"] == 1

    bad = dict(context.metadata["short_cues"])
    bad["captions"] = [
        {
            "start": 0.0,
            "end": 2.0,
            "text": "bottom",
            "lines": ["bottom"],
            "layout": "SPLIT_SCREEN_FILL",
            "subtitle_y": 1700,
        }
    ]
    context.metadata["short_cues"] = bad
    with pytest.raises(NeedsReviewError):
        ShortQaStep().run(context, ShortQaParams(), StepIO())
