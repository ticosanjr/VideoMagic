from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.domains.audio.finalize import AudioFinalizeResult
from videoflow.engine.recipes import BUILTIN_RECIPES
from videoflow.steps.audio_finalize import AudioFinalizeParams, AudioFinalizeStep
from videoflow.steps.base import StepIO

CONSUMERS = {"audio.qa", "export.nle", "export.video", "shorts.render", "delivery.package"}


def test_every_delivery_recipe_wires_audio_finalize() -> None:
    for recipe_id, recipe in BUILTIN_RECIPES.items():
        steps = recipe.get("steps") or []
        types = [step.get("type") for step in steps]
        if not CONSUMERS & set(types):
            continue
        finals = [step for step in steps if step.get("type") == "audio.finalize"]
        assert len(finals) == 1, recipe_id
        assert finals[0]["params"]["target_name"] == "master.wav"
        assert finals[0]["needs"], recipe_id
        for step in steps:
            if step.get("type") == "audio.qa":
                assert finals[0]["id"] in (step.get("needs") or []), recipe_id
        if isinstance(recipe.get("ui"), dict) and recipe["ui"].get("nodes"):
            assert finals[0]["id"] in recipe["ui"]["nodes"], recipe_id


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    for name in ("work", "exports", "audio"):
        (output / name).mkdir(parents=True, exist_ok=True)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    state = ProjectState(media_info=media)
    return PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=media,
        state=state,
    )


def test_audio_finalize_step_does_not_remix_an_already_mixed_track(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    mix = context.output / "audio" / "mix.wav"
    mix.write_bytes(b"mix")
    music = context.output / "audio" / "music.wav"
    music.write_bytes(b"music")
    context.artifacts["audio_mix"] = str(mix)
    context.artifacts["audio_music"] = str(music)
    captured: dict[str, object] = {}

    def fake_finalize(voice, output, **kwargs):
        captured.update({"voice": voice, **kwargs})
        target = Path(output) / "audio" / "final.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"final")
        return AudioFinalizeResult(
            ok=True,
            path=str(target),
            duration_sec=1.0,
            sample_rate=48000,
            channels=2,
            codec="pcm_s24le",
            integrated_lufs=-15.5,
            true_peak_db=-2.0,
        )

    monkeypatch.setattr("videoflow.steps.audio_finalize.finalize_audio", fake_finalize)
    AudioFinalizeStep().run(context, AudioFinalizeParams(), StepIO())

    assert captured["voice"] == mix
    assert captured["music_path"] is None
    assert captured["sfx_path"] is None
    assert captured["target_lufs"] == -15.5
    assert (context.output / "audio" / "master.wav").read_bytes() == b"final"
    assert context.artifacts["audio_master"] == str(
        context.output / "audio" / "master.wav"
    )
    assert context.artifacts["audio_final"] == str(context.output / "audio" / "final.wav")
