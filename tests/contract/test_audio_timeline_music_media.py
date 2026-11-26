"""Real FFmpeg proof that final audio follows the edited timeline and music."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.core.context import PipelineContext
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.domains.audio.finalize import AudioFinalizeError, finalize_audio
from videoflow.domains.audio.pcm_io import read_wav_mono_float32
from videoflow.steps.audio_finalize import AudioFinalizeParams, AudioFinalizeStep
from videoflow.steps.base import StepIO

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.media
RATE = 48_000


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr[-1000:]


def _duration(path: Path) -> float:
    completed = subprocess.run(
        [
            FFPROBE or "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return float(completed.stdout.strip())


def _source(path: Path) -> Path:
    _run(
        [
            FFMPEG or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=30:duration=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
    )
    return path


def _wav(path: Path, *, frequency: int, seconds: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            FFMPEG or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration={seconds}",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(path),
        ]
    )
    return path


def _state(source: Path) -> ProjectState:
    media = MediaInfo(
        source_path=str(source),
        duration_frames=300,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=RATE,
    )
    return ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=60,
                timeline_in_frame=0,
                timeline_out_frame=60,
            ),
            VideoSegment(
                clip_id="v2",
                source_id="primary",
                source_in_frame=90,
                source_out_frame=150,
                timeline_in_frame=60,
                timeline_out_frame=120,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=96_000,
                timeline_in_sample=0,
                timeline_out_sample=96_000,
            ),
            AudioSegment(
                clip_id="v2",
                source_id="primary",
                source_in_sample=144_000,
                source_out_sample=240_000,
                timeline_in_sample=96_000,
                timeline_out_sample=192_000,
            ),
        ],
    )


def _amp220_vs_440(path: Path) -> tuple[float, float]:
    samples, rate = read_wav_mono_float32(path)
    window = samples[: min(len(samples), rate * 4)]
    spectrum = np.abs(np.fft.rfft(window * np.hanning(len(window))))
    freqs = np.fft.rfftfreq(len(window), 1.0 / rate)

    def amp(frequency: int) -> float:
        index = int(np.argmin(np.abs(freqs - frequency)))
        return float(spectrum[index])

    return amp(220), amp(440)


@pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not installed")
def test_finalize_uses_timeline_duration_and_beatmap_music(tmp_path: Path) -> None:
    source = _source(tmp_path / "source.mp4")
    output = tmp_path / "project"
    music = _wav(output / "audio" / "music" / "bed.wav", frequency=220, seconds=2.0)
    (output / "beat_map.json").write_text(
        json.dumps({"music_tracks": [{"path": "audio/music/bed.wav"}]}),
        encoding="utf-8",
    )
    _wav(output / "audio" / "dialogue_timeline.wav", frequency=440, seconds=10.0)
    state = _state(source)
    context = PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=state.media_info,
        state=state,
    )

    AudioFinalizeStep().run(
        context,
        AudioFinalizeParams(duration_sec=0.0),
        StepIO(adapter=FFmpegAdapter()),
    )

    dialogue = output / "audio" / "dialogue_timeline.wav"
    final = output / "audio" / "final.wav"
    payload = json.loads((output / "audio" / "finalize.json").read_text(encoding="utf-8"))
    assert abs(_duration(dialogue) - 4.0) <= 0.1
    assert abs(_duration(final) - 4.0) <= 0.1
    assert payload["music_mixed"] is True
    assert payload["duration_sec"] == pytest.approx(4.0, abs=0.1)
    assert music.is_file()

    no_music = finalize_audio(
        dialogue,
        output,
        duration_sec=4.0,
        include_music=False,
        target_lufs=-16.0,
        target_name="no_music.wav",
    )
    assert no_music.music_mixed is False
    music_220, music_440 = _amp220_vs_440(final)
    plain_220, _plain_440 = _amp220_vs_440(Path(no_music.path))
    assert music_220 > plain_220 * 2.0, (music_220, plain_220)
    assert music_440 > 0


def test_declared_beatmap_music_must_exist(tmp_path: Path) -> None:
    output = tmp_path / "project"
    voice = _wav(output / "audio" / "voice.wav", frequency=440, seconds=1.0)
    (output / "beat_map.json").write_text(
        json.dumps({"music_tracks": [{"path": "audio/music/missing.wav"}]}),
        encoding="utf-8",
    )
    with pytest.raises(AudioFinalizeError, match="declared .* missing"):
        finalize_audio(voice, output, duration_sec=1.0)
