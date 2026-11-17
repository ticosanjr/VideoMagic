from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.steps import audio_synth
from videoflow.steps.audio_synth import (
    AudioComposeStep,
    AudioMixStep,
    ComposeParams,
    MixParams,
    SfxSynthParams,
    SfxSynthStep,
)
from videoflow.steps.base import StepIO


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir()
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_compose_requires_a_duration(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(ExportError):
        AudioComposeStep().run(context, ComposeParams(), StepIO())


def test_compose_uses_narration_duration(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    context.metadata["narration_duration_sec"] = 2.0
    calls: list[float] = []

    def compose(directory, *, duration_sec, **kwargs):
        calls.append(duration_sec)
        mix = Path(directory) / "music-bed.wav"
        mix.parent.mkdir(parents=True, exist_ok=True)
        mix.write_bytes(b"music")
        return {"files": {"mix": str(mix)}, "duration_sec": duration_sec}

    monkeypatch.setattr(audio_synth, "compose_music", compose)
    AudioComposeStep().run(context, ComposeParams(), StepIO())
    assert calls == [2.0]
    assert Path(context.artifacts["audio_music"]).is_file()
    assert context.artifacts["music_bed"] == context.artifacts["audio_music"]


def test_sfx_uses_rendered_scenes(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    (context.output / "motion").mkdir(parents=True)
    (context.output / "motion" / "render-manifest.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {"start_sec": 0},
                    {"start_sec": 2},
                ]
            }
        )
    )
    captured: list[list[dict]] = []

    def synth(directory, cues):
        captured.append(cues)
        return {"cues": cues}

    monkeypatch.setattr(audio_synth, "synthesize_foley", synth)
    SfxSynthStep().run(context, SfxSynthParams(), StepIO())
    assert len(captured[0]) == 2
    assert context.metadata["sfx_cues"]


def test_sfx_falls_back_to_narration_cadence(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    context.metadata["narration_duration_sec"] = 65.0
    monkeypatch.setattr(
        audio_synth,
        "synthesize_foley",
        lambda directory, cues: {"cues": cues},
    )
    SfxSynthStep().run(context, SfxSynthParams(), StepIO())
    assert len(context.metadata["sfx_cues"]) >= 3


def test_mix_copies_dialogue_when_there_is_no_music(tmp_path: Path) -> None:
    context = _context(tmp_path)
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"dialogue")
    context.artifacts["audio_master"] = str(master)
    AudioMixStep().run(context, MixParams(), StepIO())
    assert Path(context.artifacts["audio_mix"]).read_bytes() == b"dialogue"
    assert (context.output / "audio" / "master.wav").is_file()


def test_mix_runs_ffmpeg_with_music_and_sfx(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"dialogue")
    music = context.output / "audio" / "music.wav"
    music.write_bytes(b"music")
    context.artifacts["audio_master"] = str(master)
    context.artifacts["audio_music"] = str(music)
    context.artifacts["sfx_cues"] = str(context.output / "sfx.json")
    (context.output / "sfx.json").write_text(
        json.dumps({"cues": [{"start_sec": 0, "path": str(master), "gain": 0.2}]})
    )
    monkeypatch.setattr(audio_synth, "find_binary", lambda name: "ffmpeg")
    commands: list[list[str]] = []

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"mixed")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(audio_synth.subprocess, "run", run)
    AudioMixStep().run(context, MixParams(target_lufs=-14), StepIO())
    assert Path(context.artifacts["audio_mix"]).read_bytes() == b"mixed"
    assert any("loudnorm" in item for item in commands[-1])


def test_mix_reports_ffmpeg_failure(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"dialogue")
    music = context.output / "audio" / "music.wav"
    music.write_bytes(b"music")
    context.artifacts["audio_master"] = str(master)
    context.artifacts["audio_music"] = str(music)
    monkeypatch.setattr(audio_synth, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        audio_synth.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(ExportError, match="mix"):
        AudioMixStep().run(context, MixParams(), StepIO())


def test_compose_reads_style_audio_and_media_duration(tmp_path: Path, monkeypatch) -> None:
    from videoflow.domain.state import MediaInfo

    context = _context(tmp_path)
    (context.output / "style").mkdir(parents=True)
    (context.output / "style" / "style-guide.json").write_text(
        json.dumps({"audio": {"bpm": "slow", "root_midi": "high"}})
    )
    context.media = MediaInfo(
        source_path=str(context.source),
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=1280,
        height=720,
        audio_sample_rate=48000,
    )
    captured: dict = {}

    def compose(directory, **kwargs):
        captured.update(kwargs)
        return {"files": {"mix": str(Path(directory) / "mix.wav")}}

    monkeypatch.setattr(audio_synth, "compose_music", compose)
    AudioComposeStep().run(context, ComposeParams(), StepIO())
    assert captured["bpm"] == ComposeParams().bpm
    assert captured["root_midi"] == ComposeParams().root_midi
    assert captured["duration_sec"] == 2.0
    assert AudioComposeStep().cache_outputs(context)


def test_compose_ignores_non_dict_files(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    context.metadata["narration_duration_sec"] = 1.0
    monkeypatch.setattr(audio_synth, "compose_music", lambda directory, **kwargs: {"files": "bad"})
    AudioComposeStep().run(context, ComposeParams(), StepIO())
    assert "audio_music_plan" in context.artifacts
    assert AudioComposeStep().cache_outputs(context)


def test_sfx_skips_non_dict_scenes_and_uses_style_kinds(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    (context.output / "style").mkdir(parents=True)
    (context.output / "style" / "style-guide.json").write_text(
        json.dumps({"audio": {"foley": ["whoosh"]}})
    )
    (context.output / "motion").mkdir(parents=True)
    (context.output / "motion" / "render-manifest.json").write_text(
        json.dumps({"scenes": [1, {"start_sec": 1}]})
    )
    captured: list[dict] = []
    monkeypatch.setattr(
        audio_synth,
        "synthesize_foley",
        lambda directory, cues: captured.append(cues[0]) or {"cues": cues},
    )
    SfxSynthStep().run(context, SfxSynthParams(), StepIO())
    assert captured[0]["kind"] == "whoosh"


def test_mix_reports_missing_dialogue_and_bad_sfx_plan(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(ExportError, match="dialogue master"):
        AudioMixStep().run(context, MixParams(), StepIO())

    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"dialogue")
    context.artifacts["audio_master"] = str(master)
    plan = context.output / "sfx.json"
    plan.write_text("{bad")
    context.artifacts["sfx_cues"] = str(plan)
    AudioMixStep().run(context, MixParams(), StepIO())
    assert Path(context.artifacts["audio_mix"]).read_bytes() == b"dialogue"


def test_mix_without_ffmpeg_or_music_but_with_foley(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"dialogue")
    cue = context.output / "audio" / "hit.wav"
    cue.write_bytes(b"cue")
    context.artifacts["audio_master"] = str(master)
    context.artifacts["sfx_cues"] = str(context.output / "sfx.json")
    (context.output / "sfx.json").write_text(
        json.dumps({"cues": [{"start_sec": 0, "path": str(cue)}]})
    )
    monkeypatch.setattr(audio_synth, "find_binary", lambda name: None)
    with pytest.raises(ExportError, match="FFmpeg"):
        AudioMixStep().run(context, MixParams(), StepIO())


def test_mix_loops_music_and_applies_notch(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"dialogue")
    music = context.output / "audio" / "music.wav"
    music.write_bytes(b"music")
    cue = context.output / "audio" / "hit.wav"
    cue.write_bytes(b"cue")
    context.artifacts["audio_master"] = str(master)
    context.artifacts["audio_music"] = str(music)
    context.artifacts["sfx_cues"] = str(context.output / "sfx.json")
    (context.output / "sfx.json").write_text(
        json.dumps(
            {
                "cues": [
                    {"start_sec": 1.5, "path": str(cue), "gain": 0.4},
                    {"start_sec": 2.0, "path": str(tmp_path / "missing.wav")},
                ]
            }
        )
    )
    context.metadata["audio_music"] = {"loop_seconds": 5}
    (context.output / "style").mkdir(parents=True)
    (context.output / "style" / "style-guide.json").write_text(
        json.dumps({"audio": {"keyboard_notch_hz": "x", "keyboard_notch_db": "y"}})
    )
    monkeypatch.setattr(audio_synth, "find_binary", lambda name: "ffmpeg")
    commands: list[list[str]] = []

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"mixed")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(audio_synth.subprocess, "run", run)
    AudioMixStep().run(
        context,
        MixParams(sfx_notch_hz=3000, sfx_notch_db=-6, duck_music=False),
        StepIO(),
    )
    assert "-stream_loop" in commands[-1]
    assert any("equalizer" in item for item in commands[-1])
    assert AudioMixStep().cache_outputs(context)


def test_mix_accepts_explicit_paths_and_legacy_music_alias(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from videoflow.steps import audio_synth

    context = _context(tmp_path)
    master = tmp_path / "dialogue.wav"
    master.write_bytes(b"dialogue")
    music = tmp_path / "bed.wav"
    music.write_bytes(b"music")
    commands: list[list[str]] = []

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"mixed")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(audio_synth, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(audio_synth.subprocess, "run", run)

    AudioMixStep().run(
        context,
        MixParams(master_path=str(master), music_path=str(music)),
        StepIO(),
    )

    assert str(music) in commands[-1]
    assert Path(context.artifacts["audio_mix"]).read_bytes() == b"mixed"

    (tmp_path / "alias").mkdir()
    context2 = _context(tmp_path / "alias")
    context2.artifacts["audio_master"] = str(master)
    context2.artifacts["music_bed"] = str(music)
    AudioMixStep().run(context2, MixParams(), StepIO())
    assert str(music) in commands[-1]


def test_mix_recovers_music_from_plan_and_builds_three_act_envelope(
    tmp_path: Path, monkeypatch
) -> None:
    from types import SimpleNamespace

    from videoflow.steps import audio_synth

    context = _context(tmp_path)
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"dialogue")
    context.artifacts["audio_master"] = str(master)
    music = context.output / "audio" / "music" / "music-bed.wav"
    music.parent.mkdir(parents=True)
    music.write_bytes(b"music")
    plan = context.output / "audio" / "music-plan.json"
    plan.write_text(
        json.dumps({"files": {"mix": str(music)}, "loop_seconds": 5}),
        encoding="utf-8",
    )
    context.artifacts["audio_music"] = str(context.output / "audio" / "missing.wav")
    context.artifacts["audio_music_plan"] = str(plan)
    commands: list[list[str]] = []

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"mixed")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(audio_synth, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(audio_synth.subprocess, "run", run)

    AudioMixStep().run(context, MixParams(music_arc="three_act"), StepIO())

    assert str(music) in commands[-1]
    assert any("if(lt(t," in item for item in commands[-1])
