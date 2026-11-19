from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.application import compositor
from videoflow.application.compositor import picture_in_picture
from videoflow.application.projects import (
    get_project,
    init_project,
    load_project_state,
    project_uuid,
    save_project_state,
)
from videoflow.domain.state import MediaInfo, ProjectState

pytestmark = pytest.mark.media


def ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        pytest.skip("FFmpeg is not on PATH")
    return binary


def test_picture_in_picture_preserves_alpha(tmp_path: Path) -> None:
    asset = tmp_path / "screen.mp4"
    subprocess.run(
        [
            ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(asset),
        ],
        check=True,
    )
    record, _state = init_project(
        project_id="pip-media",
        name="PiP",
        output=tmp_path / "out",
    )
    media = MediaInfo(
        source_path=str(asset),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=1080,
        height=1920,
        audio_sample_rate=48000,
    )
    state = ProjectState(
        project_id=project_uuid(record.project_id),
        media_info=media,
        sources={"src1": media},
        primary_source_id="src1",
    )
    save_project_state(record, state, bump_revision=False)

    result = picture_in_picture(
        record.project_id,
        str(asset),
        0.0,
        0.5,
        width_ratio=0.4,
    )

    output = Path(result["asset"])
    assert output.is_file()
    assert output.suffix == ".webm"
    frame = tmp_path / "frame.png"
    subprocess.run(
        [
            ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-c:v",
            "libvpx-vp9",
            "-i",
            str(output),
            "-frames:v",
            "1",
            str(frame),
        ],
        check=True,
    )
    from PIL import Image

    image = Image.open(frame)
    assert image.mode in {"RGBA", "LA"}
    assert image.getchannel("A").getextrema() == (0, 255)
    saved = load_project_state(get_project(record.project_id))
    assert saved.overlays[-1].z == 25


def test_trim_clip_cuts_only_the_requested_range(tmp_path: Path) -> None:
    source = tmp_path / "trim.mp4"
    subprocess.run(
        [
            ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    record, _state = init_project(
        project_id="trim-media",
        name="Trim",
        output=tmp_path / "trim-out",
    )
    media = MediaInfo(
        source_path=str(source),
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=320,
        height=180,
        audio_sample_rate=48000,
    )
    state = ProjectState(
        project_id=project_uuid(record.project_id),
        media_info=media,
        sources={"src1": media},
        primary_source_id="src1",
    )
    save_project_state(record, state, bump_revision=False)
    target = compositor._trim_clip(record.project_id, state, 0.2, 0.8)
    assert target.is_file()
    assert compositor._trim_clip(record.project_id, state, 0.2, 0.8) == target
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert abs(float(probe.stdout.strip()) - 0.6) < 0.15
