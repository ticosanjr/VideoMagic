from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.scene_intel.supercontext import build_supercontext
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ShortPlanError
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.steps.base import StepIO
from videoflow.steps.short_plan import ShortPlanParams, ShortPlanStep


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


def _context(tmp_path: Path) -> PipelineContext:
    manifest = _manifest()
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
    )
    context.metadata["scenes_manifest"] = manifest.model_dump(mode="json")
    context.metadata["scenes_supercontext"] = build_supercontext(manifest)
    return context


def test_short_plan_none_is_deterministic_and_protects_screen(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    ShortPlanStep().run(
        context,
        ShortPlanParams(short_id="SH", start_sec=0, end_sec=30, llm_policy="none"),
        StepIO(),
    )
    plan = context.metadata["short_plan"]
    assert plan["short_id"] == "SH"
    assert plan["start"] == 0.0
    assert plan["end"] == 30.0
    assert [segment["layout"] for segment in plan["segments"]] == [
        "FULL_FACE",
        "SPLIT_SCREEN_SAFE",
        "FULL_FACE",
    ]
    assert context.metadata["short_plan_report"]["validation"]["ok"] is True
    assert Path(context.artifacts["short_plan"]).is_file()
    assert Path(context.artifacts["short_plan_report"]).is_file()


def test_short_plan_caller_writes_request_without_planning(tmp_path: Path) -> None:
    context = _context(tmp_path)
    ShortPlanStep().run(
        context,
        ShortPlanParams(short_id="SH", start_sec=0, end_sec=30, llm_policy="caller"),
        StepIO(),
    )
    assert "short_plan" not in context.metadata
    request = json.loads(
        Path(context.artifacts["short_plan_request"]).read_text(encoding="utf-8")
    )
    assert request["schema"] == "short_composition_v1"
    assert context.metadata["short_plan_llm"]["status"] == "waiting"
    assert any("calling model" in warning for warning in context.warnings)


def test_short_plan_accepts_caller_response(tmp_path: Path) -> None:
    context = _context(tmp_path)
    ShortPlanStep().run(
        context,
        ShortPlanParams(
            short_id="SH",
            start_sec=0,
            end_sec=30,
            llm_policy="caller",
            plan={
                "short_id": "SH",
                "segments": [
                    {
                        "seg_id": "S1",
                        "start_scene_id": "SC_0001",
                        "end_scene_id": "SC_0001",
                        "layout": "FULL_FACE",
                    },
                    {
                        "seg_id": "S2",
                        "start_scene_id": "SC_0002",
                        "end_scene_id": "SC_0003",
                        "layout": "SPLIT_SCREEN_SAFE",
                    },
                ],
            },
        ),
        StepIO(),
    )
    plan = context.metadata["short_plan"]
    assert len(plan["segments"]) == 2
    assert plan["segments"][0]["rel_end"] == 8.0
    assert plan["segments"][1]["rel_start"] == 8.0
    assert plan["segments"][1]["rel_end"] == 30.0
    assert context.metadata["short_plan_llm"]["status"] == "provided"


def test_short_plan_videoflow_calls_the_explicit_client(tmp_path: Path) -> None:
    context = _context(tmp_path)

    class Client:
        def __init__(self) -> None:
            self.role = ""

        def complete_json(self, prompt: str, role: str) -> dict:
            self.role = role
            assert "scene_id" in prompt
            return {
                "short_id": "SH",
                "segments": [
                    {
                        "seg_id": "S1",
                        "start_scene_id": "SC_0001",
                        "end_scene_id": "SC_0003",
                        "layout": "FULL_FACE",
                    }
                ],
            }

    client = Client()
    io = StepIO()
    io.llm_client = client
    ShortPlanStep().run(
        context,
        ShortPlanParams(
            short_id="SH",
            start_sec=0,
            end_sec=30,
            llm_policy="videoflow",
            llm_role="shorts.composition",
        ),
        io,
    )
    assert client.role == "shorts.composition"
    assert context.metadata["short_plan_llm"]["calls_made"] == 1
    assert context.metadata["short_plan"]["segments"][0]["rel_end"] == 30.0


def test_short_plan_rejects_invalid_submitted_plan(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(ShortPlanError, match="unknown scene"):
        ShortPlanStep().run(
            context,
            ShortPlanParams(
                short_id="SH",
                start_sec=0,
                end_sec=30,
                llm_policy="caller",
                plan={
                    "short_id": "SH",
                    "segments": [
                        {
                            "seg_id": "S1",
                            "start_scene_id": "SC_9999",
                            "end_scene_id": "SC_9999",
                            "layout": "FULL_FACE",
                        }
                    ],
                },
            ),
            StepIO(),
        )


def test_short_validate_accepts_generated_plan(tmp_path: Path) -> None:
    from videoflow.steps.short_validate import ShortValidateParams, ShortValidateStep

    context = _context(tmp_path)
    ShortPlanStep().run(
        context,
        ShortPlanParams(short_id="SH", start_sec=0, end_sec=30, llm_policy="none"),
        StepIO(),
    )
    ShortValidateStep().run(context, ShortValidateParams(), StepIO())
    report = context.metadata["short_validation"]
    assert report["ok"] is True
    assert report["segment_count"] == 3
    assert Path(context.artifacts["short_validation"]).is_file()


def test_short_validate_rejects_missing_broll(tmp_path: Path) -> None:
    from videoflow.steps.short_validate import ShortValidateParams, ShortValidateStep

    context = _context(tmp_path)
    plan = {
        "short_id": "SH",
        "start": 0.0,
        "end": 8.0,
        "segments": [
            {
                "seg_id": "S1",
                "rel_start": 0.0,
                "rel_end": 8.0,
                "layout": "SPLIT_BROLL",
                "broll_source": {"path": "/missing/clip.mp4"},
            }
        ],
    }
    context.metadata["short_plan"] = plan
    with pytest.raises(ShortPlanError, match="broll file is missing"):
        ShortValidateStep().run(context, ShortValidateParams(strict=True), StepIO())
