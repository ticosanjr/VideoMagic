"""Coverage for motion codegen/render fallbacks and caches."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.steps import motion
from videoflow.steps.base import StepIO


def context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir()
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_motion_codegen_skips_bad_assets_and_handles_lists(
    tmp_path: Path,
) -> None:
    ctx = context(tmp_path)
    (ctx.output / "storyboard").mkdir()
    (ctx.output / "style").mkdir()
    (ctx.output / "assets").mkdir()
    (ctx.output / "storyboard" / "units.json").write_text(
        json.dumps([{"unit_id": "U1", "title": "One", "duration_sec": 4}]),
        encoding="utf-8",
    )
    (ctx.output / "style" / "style-guide.json").write_text("[]", encoding="utf-8")
    (ctx.output / "assets" / "assignments.json").write_text(
        json.dumps(
            [
                "bad",
                {"unit_id": "U1", "asset": "bad"},
                {
                    "unit_id": "U1",
                    "asset": {"path": "/tmp/a.png", "kind": "image"},
                },
            ]
        ),
        encoding="utf-8",
    )

    motion.MotionCodegenStep().run(ctx, motion.MotionCodegenParams(), StepIO())

    scenes = ctx.metadata["motion_scenes"]
    assert scenes
    assert scenes[0]["layers"][0]["path"] == "/tmp/a.png"
    assert motion.MotionCodegenStep().cache_outputs(ctx)
    second = tmp_path / "second"
    second.mkdir()
    empty = context(second)
    assert motion.MotionCodegenStep().cache_outputs(empty) == ()


def test_motion_render_handles_disabled_backends_and_failures(tmp_path: Path, monkeypatch) -> None:
    ctx = context(tmp_path)
    step = motion.MotionRenderStep()
    step.run(ctx, motion.MotionParams(render=False), StepIO())
    assert ctx.metadata["motion_plan"]["render"] is False
    assert step.cache_outputs(ctx)

    step.run(ctx, motion.MotionParams(engine="remotion"), StepIO())
    assert any("not bundled" in warning for warning in ctx.warnings)

    (ctx.output / "motion").mkdir(exist_ok=True)
    (ctx.output / "motion" / "scenes.json").write_text(
        json.dumps(
            {
                "scenes": [
                    "bad",
                    {"scene_id": "ok", "duration_sec": 1},
                    {"scene_id": "boom", "duration_sec": 1},
                ]
            }
        ),
        encoding="utf-8",
    )

    def render(scene, directory, **kwargs):  # type: ignore[no-untyped-def]
        if scene.get("scene_id") == "boom":
            raise RuntimeError("render failed")
        Path(directory).mkdir(parents=True, exist_ok=True)
        target = Path(directory) / "ok.mp4"
        target.write_bytes(b"mp4")
        return target

    monkeypatch.setattr(motion, "render_scene", render)
    step.run(ctx, motion.MotionParams(), StepIO())

    assert len(ctx.metadata["motion_manifest"]) == 1
    assert any("render failed" in warning for warning in ctx.warnings)
    assert step.cache_outputs(ctx)


def test_motion_render_without_scenes(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    motion.MotionRenderStep().run(ctx, motion.MotionParams(), StepIO())
    assert Path(ctx.artifacts["motion_manifest"]).is_file()
    assert any("Motion render skipped" in warning for warning in ctx.warnings)
