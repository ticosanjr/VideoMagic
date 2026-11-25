"""v4.7.0 audio finalize: idempotent dialogue, loop, and SFX events."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState
from videoflow.domains.audio import finalize as finalize_module
from videoflow.domains.audio.finalize import AudioFinalizeResult, finalize_audio
from videoflow.steps.audio_finalize import AudioFinalizeParams, AudioFinalizeStep
from videoflow.steps.base import StepIO

FFMPEG = shutil.which("ffmpeg")
RATE = 48_000


def _run(*args: str) -> None:
    assert FFMPEG is not None
    completed = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _wav(path: Path, *, seconds: float, frequency: int = 440) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={frequency}:sample_rate=48000:duration={seconds}",
        "-ac",
        "2",
        "-c:a",
        "pcm_s24le",
        str(path),
    )
    return path


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    for name in ("work", "exports", "audio"):
        (output / name).mkdir(parents=True, exist_ok=True)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=RATE,
    )
    state = ProjectState(
        media_info=media,
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_in_sample=0,
                source_out_sample=2 * RATE,
                timeline_in_sample=0,
                timeline_out_sample=2 * RATE,
            )
        ],
    )
    return PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=media,
        state=state,
    )


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_finalize_audio_runs_twice_and_loops_short_music(tmp_path: Path) -> None:
    voice = _wav(tmp_path / "voice.wav", seconds=2.0)
    music = _wav(tmp_path / "music.wav", seconds=0.6, frequency=220)
    first = finalize_audio(
        voice,
        tmp_path / "project",
        music_path=music,
        duration_sec=2.0,
        target_name="final_mix.wav",
    )
    second = finalize_audio(
        voice,
        tmp_path / "project",
        music_path=music,
        duration_sec=2.0,
        target_name="final_mix.wav",
    )
    assert first.ok is True
    assert second.ok is True
    target = Path(second.path)
    assert target.name == "final_mix.wav"
    assert target.is_file()
    assert not (target.parent / ".final_mix.tmp.wav").exists()


def test_music_graph_loops_and_fades_out() -> None:
    graph = finalize_module._build_graph(
        duration=691.0,
        mono_repair="",
        music=True,
        sfx=False,
        music_gain=0.2,
        sfx_gain=0.5,
        ducking=True,
    )
    assert "aloop=loop=-1" in graph
    assert "afade=t=out:st=688.500000:d=2.500000" in graph


def test_finalize_rejects_missing_sfx_events(tmp_path: Path) -> None:
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"wav")
    with pytest.raises(ExportError, match="No SFX events"):
        finalize_audio(
            voice,
            tmp_path / "project",
            sfx_events=[{"path": str(tmp_path / "missing.wav"), "start_sec": 0.0}],
            duration_sec=1.0,
        )


def test_step_always_reads_dialogue_timeline_and_mixes_sfx_plan(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    dialogue = context.output / "audio" / "dialogue_timeline.wav"
    dialogue.write_bytes(b"dialogue")
    previous_final = context.output / "audio" / "final.wav"
    previous_final.write_bytes(b"previous")
    context.artifacts["audio_mix"] = str(previous_final)
    music = context.output / "audio" / "music.wav"
    music.write_bytes(b"music")
    context.artifacts["audio_music"] = str(music)
    sfx = context.output / "audio" / "sfx" / "whoosh.wav"
    sfx.parent.mkdir(parents=True, exist_ok=True)
    sfx.write_bytes(b"sfx")
    (context.output / "audio" / "sfx-plan.json").write_text(
        '{"cues": [{"path": "audio/sfx/whoosh.wav", "start_sec": 1.2, "gain": 0.5}]}',
        encoding="utf-8",
    )
    captures: list[dict[str, object]] = []

    def fake_finalize(voice, output, **kwargs):
        captures.append({"voice": Path(voice), **kwargs})
        target = Path(output) / "audio" / str(kwargs.get("target_name") or "final.wav")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"final")
        return AudioFinalizeResult(
            ok=True,
            path=str(target),
            duration_sec=2.0,
            sample_rate=48000,
            channels=2,
            codec="pcm_s24le",
            integrated_lufs=-16.0,
            true_peak_db=-2.0,
        )

    monkeypatch.setattr(
        "videoflow.steps.audio_finalize.finalize_audio", fake_finalize
    )
    AudioFinalizeStep().run(context, AudioFinalizeParams(duration_sec=2.0), StepIO())
    AudioFinalizeStep().run(context, AudioFinalizeParams(duration_sec=2.0), StepIO())

    assert len(captures) == 2
    for captured in captures:
        assert captured["voice"] == dialogue
        assert captured["music_path"] == str(music)
        events = captured["sfx_events"]
        assert isinstance(events, list) and len(events) == 1
        assert Path(str(events[0]["path"])).name == "whoosh.wav"
        assert events[0]["start_sec"] == 1.2
    assert (context.output / "audio" / "final_mix.wav").is_file()
    assert (context.output / "audio" / "final.wav").is_file()
    assert (context.output / "audio" / "master.wav").is_file()
    assert context.metadata["audio_finalize"]["sfx_events_requested"] == 1


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_finalize_autodetects_music_and_clamps_late_sfx(tmp_path: Path) -> None:
    output = tmp_path / "project"
    voice = _wav(output / "audio" / "dialogue_timeline.wav", seconds=2.0)
    music = _wav(output / "audio" / "music" / "music-bed.wav", seconds=0.5, frequency=220)
    sfx = _wav(output / "audio" / "sfx" / "hit.wav", seconds=0.2, frequency=880)
    (output / "beat_map.json").write_text(
        (
            '{"sfx": [{"path": "audio/sfx/hit.wav", "start_frame": 90, '
            '"gain_db": -6.0}]}'
        ),
        encoding="utf-8",
    )
    voice_sha = voice.read_bytes()

    first = finalize_audio(voice, output, duration_sec=2.0)
    assert first.music_mixed is True
    assert first.sfx_events_requested == 1
    assert first.sfx_events_mixed == 1
    assert any("clamped" in warning for warning in first.warnings)
    assert abs(first.integrated_lufs + 16.0) <= 0.7

    second = finalize_audio(voice, output, duration_sec=2.0)
    assert second.ok is True
    assert voice.read_bytes() == voice_sha
    assert music.is_file() and sfx.is_file()
