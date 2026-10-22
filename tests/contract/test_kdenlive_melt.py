import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.timeline_builder import build_timeline
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.state import ProjectState
from videoflow.exporters.kdenlive import export_kdenlive


@pytest.mark.media
def test_kdenlive_project_renders_with_melt(tmp_path: Path) -> None:
    melt = shutil.which("melt")
    if melt is None:
        pytest.skip("melt is not installed")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg is not installed")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-t",
            "2",
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
    media = FFmpegAdapter().probe(source)
    built = build_timeline(
        media,
        [(0, 24000), (48000, 72000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="alternate_cuts", progressive_zoom=True),
        transition_frames=4,
    )
    state = ProjectState(
        media_info=media,
        video_segments=list(built.video_segments),
        audio_segments=list(built.audio_segments),
    )
    project = export_kdenlive(state, tmp_path / "timeline.kdenlive")
    output = tmp_path / "melt.mp4"
    completed = subprocess.run(
        [melt, "-consumer", f"avformat:{output}", str(project)],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert output.is_file() and output.stat().st_size > 0
