"""Real FFmpeg/FCPXML proof for idempotent overlays and compositing."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from videoflow.application.beatmap import apply_beatmap
from videoflow.application.nle_extras import nle_extras_from_output
from videoflow.application.nle_validation import validate_nle_exports
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.fcpxml import export_fcpxml
from videoflow.exporters.mp4 import export_mp4

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.media


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr[-1000:]


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
            "color=c=green:s=640x360:r=30:d=3",
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


def _red_image(path: Path) -> Path:
    Image.new("RGB", (640, 360), (255, 0, 0)).save(path)
    return path


def _state(source: Path) -> ProjectState:
    media = MediaInfo(
        source_path=str(source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48_000,
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
                source_out_frame=90,
                timeline_in_frame=0,
                timeline_out_frame=90,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=144_000,
                timeline_in_sample=0,
                timeline_out_sample=144_000,
            )
        ],
    )


def _frame(path: Path, seconds: float, destination: Path) -> Image.Image:
    _run(
        [
            FFMPEG or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            str(destination),
        ]
    )
    return Image.open(destination).convert("RGB")


@pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not installed")
def test_apply_beatmap_twice_composes_overlay_in_mp4_and_fcpxml(
    tmp_path: Path,
) -> None:
    output = tmp_path / "project"
    source = _source(tmp_path / "source.mp4")
    red = _red_image(tmp_path / "red.png")
    state = _state(source)
    manifest = {
        "broll": [
            {
                "path": str(red),
                "start_frame": 30,
                "duration_frames": 30,
                "kind": "image",
                "anchor": "fullscreen",
                "width_ratio": 1.0,
                "z": 10,
            }
        ]
    }

    first, report, _ = apply_beatmap(state, output, manifest, force=True)
    assert report.overlays == 1
    assert len(first.overlays) == 1
    second, report, _ = apply_beatmap(first, output, manifest, force=True)
    assert report.overlays == 1
    assert len(second.overlays) == 1
    assert second.overlays[0].overlay_id == "beatmap-1"

    mp4 = output / "exports" / "overlay.mp4"
    export_mp4(
        second,
        mp4,
        fps=30,
        mode="preview",
        qa_mode="off",
    )
    frame = _frame(mp4, 1.5, tmp_path / "overlay.png")
    red_pixel = frame.getpixel((frame.width // 2, frame.height // 2))
    assert red_pixel[0] > 180, red_pixel
    assert red_pixel[1] < 80, red_pixel

    output.mkdir(parents=True, exist_ok=True)
    (output / "project_state.json").write_text(
        json.dumps(second.model_dump(mode="json")),
        encoding="utf-8",
    )
    fcpxml = output / "exports" / "resolve_timeline.fcpxml"
    export_fcpxml(
        second,
        fcpxml,
        extras=nle_extras_from_output(output),
    )
    check = validate_nle_exports(
        output / "exports",
        check_media=False,
        formats={"fcpxml"},
    )
    assert check["exports"]["fcpxml"]["broll_clips"] == 1, check
