"""Real FFmpeg proof that the final bed mixes music/SFX at -16 LUFS.

The test builds a dialogue track, a short music bed that must be looped, and
two Foley cues. It then runs the canonical audio stage with no explicit paths
so autodetection is exercised, and finally renders a preview MP4 to prove the
master inherits the same ``final_mix.wav``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.master_export import render_master
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.domains.audio.finalize import finalize_audio

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.media


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr[-1000:]


def _wav(path: Path, *, frequency: int, seconds: float, rate: int = 48000) -> Path:
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
            f"sine=frequency={frequency}:sample_rate={rate}:duration={seconds}",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(path),
        ]
    )
    return path


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
            "testsrc=size=320x180:rate=30:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=3",
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


def _state(source: Path) -> ProjectState:
    media = MediaInfo(
        source_path=str(source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=320,
        height=180,
        audio_sample_rate=48000,
    )
    return ProjectState(
        media_info=media,
        sources={"src1": media},
        primary_source_id="src1",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="src1",
                source_in_frame=0,
                source_out_frame=90,
                timeline_in_frame=0,
                timeline_out_frame=90,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="src1",
                source_in_sample=0,
                source_out_sample=144000,
                timeline_in_sample=0,
                timeline_out_sample=144000,
            )
        ],
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _loudness(path: Path) -> float:
    return float(FFmpegAdapter().measure_loudness(path)["integrated_lufs"])


def _extract_audio(source: Path, destination: Path) -> Path:
    _run(
        [
            FFMPEG or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-c:a",
            "pcm_s24le",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(destination),
        ]
    )
    return destination


@pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not installed")
def test_finalize_autodetects_music_and_sfx_and_preview_inherits_mix(
    tmp_path: Path,
) -> None:
    output = tmp_path / "project"
    dialogue = _wav(output / "audio" / "dialogue_timeline.wav", frequency=440, seconds=3.0)
    _wav(output / "audio" / "music" / "music-bed.wav", frequency=220, seconds=0.8)
    _wav(output / "audio" / "sfx" / "whoosh.wav", frequency=880, seconds=0.2)
    _wav(output / "audio" / "sfx" / "ding.wav", frequency=1320, seconds=0.2)
    (output / "beat_map.json").write_text(
        json.dumps(
            {
                "sfx_events": [
                    {
                        "path": "audio/sfx/whoosh.wav",
                        "start_sec": 0.6,
                        "gain_db": -6.0,
                    },
                    {
                        "path": "audio/sfx/ding.wav",
                        "start_frame": 120,
                        "gain_db": -6.0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    dialogue_sha = _sha256(dialogue)

    first = finalize_audio(dialogue, output, duration_sec=3.0)
    final_mix = output / "audio" / "final_mix.wav"
    assert final_mix.is_file()
    assert first.music_mixed is True
    assert first.sfx_events_requested == 2
    assert first.sfx_events_mixed == 2
    assert any("clamped" in warning for warning in first.warnings)
    assert abs(first.integrated_lufs + 16.0) <= 0.7, first.integrated_lufs
    assert _sha256(final_mix) != dialogue_sha

    second = finalize_audio(dialogue, output, duration_sec=3.0)
    assert second.ok is True
    assert _sha256(dialogue) == dialogue_sha
    assert second.sfx_events_mixed == 2
    assert abs(second.integrated_lufs + 16.0) <= 0.7

    state = _state(_source(tmp_path / "source.mp4"))
    preview = output / "exports" / "preview.mp4"
    render_master(
        state,
        preview,
        output=output,
        audio_source="timeline",
        mode="preview",
        qa_mode="off",
        crf=30,
        preset="ultrafast",
        cache_dir=output / "render" / "segments",
    )
    preview_audio = _extract_audio(preview, tmp_path / "preview.wav")
    assert abs(_loudness(preview_audio) - _loudness(final_mix)) <= 1.0
