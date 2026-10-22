"""Real FFmpeg ingest on a generated fixture. Skipped when FFmpeg is absent."""

import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter

pytestmark = pytest.mark.media


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        pytest.skip("FFmpeg is not on PATH")
    return binary


@pytest.fixture()
def fixture(tmp_path: Path) -> Path:
    target = tmp_path / "sample.mp4"
    subprocess.run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(target),
        ],
        check=True,
    )
    return target


def test_probe_reads_the_generated_fixture(fixture: Path) -> None:
    info = FFmpegAdapter().probe(fixture)
    assert (info.fps_num, info.fps_den) == (30, 1)
    assert info.width == 320
    assert info.height == 240
    assert info.audio_sample_rate == 48000
    assert 55 <= info.duration_frames <= 65


def test_extract_pcm_writes_an_analysis_wav(fixture: Path, tmp_path: Path) -> None:
    adapter = FFmpegAdapter()
    wav = adapter.extract_pcm(fixture, tmp_path / "work" / "source.wav")
    assert wav.exists()
    assert wav.stat().st_size > 1000
    assert len(adapter.pcm_digest(wav)) == 64


def test_silence_detection_finds_gated_speech(tmp_path: Path) -> None:
    source = tmp_path / "gated.mp4"
    subprocess.run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            "-af",
            "volume=0:enable='between(t,1,2)'",
            "-t",
            "4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    adapter = FFmpegAdapter()
    adapter.probe(source)
    wav = adapter.extract_pcm(source, tmp_path / "source.wav", sample_rate=48000)
    spans = adapter.detect_speech(
        wav,
        duration_samples=4 * 48000,
        sample_rate=48000,
        min_silence_ms=400,
    )
    assert len(spans) == 2
    assert spans[0][0] == 0
    assert spans[-1][1] == 4 * 48000


@pytest.mark.media
def test_direct_mp4_render_from_a_real_timeline(fixture: Path, tmp_path: Path) -> None:
    from videoflow.application.timeline_builder import build_timeline
    from videoflow.domain.config import JlCutsConfig, ZoomsConfig
    from videoflow.domain.state import ProjectState
    from videoflow.domain.timebase import Rounding
    from videoflow.exporters.mp4 import export_mp4

    adapter = FFmpegAdapter()
    media = adapter.probe(fixture)
    timebase = media.timebase()
    duration_samples = timebase.seconds_to_samples(
        timebase.frames_to_seconds(media.duration_frames), Rounding.NEAREST
    )
    built = build_timeline(
        media,
        [(0, duration_samples)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    state = ProjectState(
        media_info=media,
        video_segments=list(built.video_segments),
        audio_segments=list(built.audio_segments),
    )
    output = export_mp4(state, tmp_path / "main.mp4")
    assert output.is_file()
    assert output.stat().st_size > 1000
    rendered = adapter.probe(output)
    assert rendered.width == media.width
    assert rendered.height == media.height
