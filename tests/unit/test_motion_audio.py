from __future__ import annotations

import json
import wave
from pathlib import Path

from videoflow.application.audio_synthesis import compose_music, synthesize_foley
from videoflow.application.motion import build_scenes
from videoflow.core.context import PipelineContext
from videoflow.steps.audio_synth import (
    AudioComposeStep,
    ComposeParams,
    SfxSynthParams,
    SfxSynthStep,
)
from videoflow.steps.base import StepIO
from videoflow.steps.intro import IntroCompileStep, IntroParams
from videoflow.steps.motion import (
    MotionCodegenParams,
    MotionCodegenStep,
    MotionParams,
    MotionRenderStep,
)


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    (output / "storyboard").mkdir(parents=True)
    (output / "style").mkdir(parents=True)
    (output / "assets").mkdir(parents=True)
    (output / "storyboard" / "units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "UNIT-0001",
                        "title": "Evidence",
                        "narration": "The document proves it.",
                        "layout": "lower_third",
                        "start_sec": 0,
                        "duration_sec": 5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (output / "style" / "style-guide.json").write_text(
        json.dumps(
            {
                "palette": ["#080B10", "#F8FAFC", "#FF3B30"],
                "theme": "dark",
            }
        ),
        encoding="utf-8",
    )
    (output / "assets" / "assignments.json").write_text(
        json.dumps(
            {
                "assignments": [
                    {
                        "unit_id": "UNIT-0001",
                        "asset": {"downloaded_path": "", "kind": "image"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_build_scenes_has_title_and_lower_third() -> None:
    scenes = build_scenes(
        [
            {
                "unit_id": "UNIT-0001",
                "title": "Evidence",
                "layout": "lower_third",
                "duration_sec": 5,
            }
        ],
        style={"palette": ["#080B10", "#F8FAFC", "#FF3B30"]},
        assets={},
    )
    assert scenes[0]["scene_id"] == "SCENE-0001"
    assert {layer["type"] for layer in scenes[0]["layers"]} >= {"title", "lower_third"}


def test_motion_codegen_and_render_manifest(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    MotionCodegenStep().run(context, MotionCodegenParams(), StepIO())
    assert context.metadata["motion_scenes"]
    assert (context.output / "motion" / "scenes.json").is_file()

    def fake_render(scene, directory):
        path = Path(directory) / f"{scene['scene_id']}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp4")
        return path

    monkeypatch.setattr("videoflow.steps.motion.render_scene", fake_render)
    MotionRenderStep().run(context, MotionParams(), StepIO())
    manifest = json.loads(
        (context.output / "motion" / "render-manifest.json").read_text()
    )
    assert manifest["count"] == 1
    assert Path(manifest["scenes"][0]["path"]).is_file()


def test_intro_compile_writes_manifest(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)

    def fake_intro(output, **kwargs):
        path = Path(output) / "motion" / "intro.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"intro")
        return {
            "available": True,
            "mode": "title_card",
            "path": str(path),
            "duration_sec": 8.0,
            "asset_count": 0,
        }

    monkeypatch.setattr("videoflow.steps.intro.compile_intro", fake_intro)
    IntroCompileStep().run(context, IntroParams(title="Dossier"), StepIO())
    assert (context.output / "motion" / "intro.json").is_file()
    assert context.metadata["intro"]["duration_sec"] == 8.0


def test_compose_and_foley_read_style_audio(tmp_path: Path) -> None:
    context = _context(tmp_path)
    style_path = context.output / "style" / "style-guide.json"
    style = json.loads(style_path.read_text(encoding="utf-8"))
    style["audio"] = {
        "bpm": 120,
        "root_midi": 50,
        "foley": ["paper_turn"],
    }
    style_path.write_text(json.dumps(style), encoding="utf-8")

    AudioComposeStep().run(
        context,
        ComposeParams(duration_sec=1.0),
        StepIO(),
    )
    music = json.loads(
        (context.output / "audio" / "music-plan.json").read_text(encoding="utf-8")
    )
    assert music["bpm"] == 120

    (context.output / "motion").mkdir(exist_ok=True)
    (context.output / "motion" / "render-manifest.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {"start_sec": 0},
                    {"start_sec": 1},
                    {"start_sec": 2},
                ]
            }
        ),
        encoding="utf-8",
    )
    SfxSynthStep().run(context, SfxSynthParams(max_cues=3), StepIO())
    sfx = json.loads(
        (context.output / "audio" / "sfx-plan.json").read_text(encoding="utf-8")
    )
    assert sfx["count"] == 3
    assert {cue["kind"] for cue in sfx["cues"]} == {"paper_turn"}


def test_procedural_music_and_foley(tmp_path: Path) -> None:
    music = compose_music(tmp_path / "music", duration_sec=1.0, sample_rate=8000)
    assert music["files"]["mix"].endswith("music-bed.wav")
    with wave.open(music["files"]["mix"], "rb") as handle:
        assert handle.getnframes() > 0
    foley = synthesize_foley(
        tmp_path / "sfx",
        [{"kind": "keyboard_click", "start_sec": 0.0}],
        sample_rate=8000,
    )
    assert foley["count"] == 1
    assert Path(foley["cues"][0]["path"]).is_file()
