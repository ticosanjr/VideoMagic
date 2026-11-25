"""Real FFmpeg proof for burned subtitles and strict target fps."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
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
            "testsrc=size=640x360:rate=60:duration=3",
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


def _ass(path: Path) -> Path:
    text = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 640",
            "PlayResY: 360",
            "WrapStyle: 0",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding"
            ),
            (
                "Style: Default,DejaVu Sans,64,&H00FFFFFF,&H00FFFFFF,"
                "&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,2,5,20,20,20,1"
            ),
            "",
            "[Events]",
            (
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
                "MarginV, Effect, Text"
            ),
            "Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,BURN TEST",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")
    return path


def _state(source: Path) -> ProjectState:
    media = MediaInfo(
        source_path=str(source),
        duration_frames=180,
        fps_num=60,
        fps_den=1,
        width=640,
        height=360,
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
                source_out_frame=180,
                timeline_in_frame=0,
                timeline_out_frame=180,
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


def _probe(path: Path) -> dict:
    completed = subprocess.run(
        [
            FFPROBE or "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


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
def test_burn_subtitles_changes_pixels_and_fps_is_30(tmp_path: Path) -> None:
    source = _source(tmp_path / "source.mp4")
    ass = _ass(tmp_path / "captions.ass")
    state = _state(source)
    burned = tmp_path / "exports" / "burned.mp4"
    plain = tmp_path / "exports" / "plain.mp4"
    export_mp4(
        state,
        burned,
        ass_path=ass,
        burn_subtitles=True,
        fps=30,
        mode="preview",
        qa_mode="off",
    )
    export_mp4(
        state,
        plain,
        fps=30,
        mode="preview",
        qa_mode="off",
    )

    probe = _probe(burned)
    video = next(item for item in probe["streams"] if item["codec_type"] == "video")
    assert video["r_frame_rate"] == "30/1"
    frames = int(video.get("nb_frames") or 0)
    assert abs(frames - 90) <= 2

    with_burn = _frame(burned, 1.5, tmp_path / "burn.png")
    without = _frame(plain, 1.5, tmp_path / "plain.png")
    diff = ImageChops.difference(with_burn, without)
    changed = sum(1 for byte in diff.tobytes() if byte)
    total = with_burn.width * with_burn.height * 3
    assert changed / total > 0.005, (changed, total)


@pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not installed")
def test_missing_ass_fails_closed(tmp_path: Path) -> None:
    from videoflow.exporters.mp4 import SubtitleBurnError

    source = _source(tmp_path / "source.mp4")
    state = _state(source)
    with pytest.raises(SubtitleBurnError):
        export_mp4(
            state,
            tmp_path / "exports" / "missing.mp4",
            ass_path=tmp_path / "missing.ass",
            burn_subtitles=True,
            fps=30,
            mode="preview",
            qa_mode="off",
        )
