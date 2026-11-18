from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.captions import build_ass
from videoflow.application.crop_preview import render_crop_preview
from videoflow.application.media_integrity import validate_duration
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.mp4 import export_mp4

pytestmark = pytest.mark.media


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        pytest.skip("FFmpeg is not on PATH")
    return binary


def _source(tmp_path: Path) -> Path:
    path = tmp_path / "source.mp4"
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
            "testsrc2=size=640x360:rate=30",
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
            str(path),
        ],
        check=True,
    )
    return path


def test_crop_preview_renders_a_jpeg(tmp_path: Path) -> None:
    source = _source(tmp_path)
    result = render_crop_preview(
        source,
        tmp_path,
        time_sec=1.0,
        aspect="9:16",
        fx=0.5,
        fy=0.5,
    )
    path = Path(result["path"])
    assert path.is_file()
    assert path.suffix == ".jpg"
    assert result["crop"]["width"] > 0
    assert result["crop"]["height"] > 0


def test_short_with_crop_ass_and_intro_renders(tmp_path: Path) -> None:
    source = _source(tmp_path)
    intro = tmp_path / "intro.png"
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
            "color=c=red:size=640x360",
            "-frames:v",
            "1",
            str(intro),
        ],
        check=True,
    )
    ass = tmp_path / "captions.ass"
    ass.write_text(
        build_ass([(0.0, 1.0, "legenda normal")], width=1080, height=1920),
        encoding="utf-8",
    )
    output = tmp_path / "short.mp4"
    FFmpegAdapter().render_short(
        source,
        [(0, 48000), (48000, 96000)],
        output,
        sample_rate=48000,
        width=320,
        height=568,
        ass_path=ass,
        fontsdir=str(tmp_path),
        intro_path=intro,
        intro_duration_sec=1.0,
        crop_focus_x=0.5,
        crop_focus_y=0.5,
    )
    assert output.is_file()
    assert output.stat().st_size > 0
    assert validate_duration(output, 3.0).ok


def test_export_duration_gate_accepts_real_mp4(tmp_path: Path) -> None:
    source = _source(tmp_path)
    media = MediaInfo(
        source_path=str(source),
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    state = ProjectState(
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
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=96000,
                timeline_in_sample=0,
                timeline_out_sample=96000,
            )
        ],
    )
    output = tmp_path / "master.mp4"
    adapter = FFmpegAdapter()
    export_mp4(state, output, adapter=adapter)
    assert output.is_file()
    report = validate_duration(output, 2.0)
    assert report.ok, report.to_dict()
