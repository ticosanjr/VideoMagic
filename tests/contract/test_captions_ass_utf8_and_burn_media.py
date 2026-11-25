"""Real FFmpeg proof for UTF-8 ASS cues and burned pixels."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from videoflow.application.files import read_json_dict
from videoflow.core.context import PipelineContext
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)
from videoflow.exporters.mp4 import export_mp4
from videoflow.steps.base import StepIO
from videoflow.steps.captions import CaptionsPlanParams, CaptionsPlanStep

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.media
RATE = 48_000


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
            "testsrc=size=640x360:rate=30:duration=3",
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


def _sentence() -> Sentence:
    text = "público, império, ação"
    tokens = ["público,", "império,", "ação"]
    start = round(0.2 * RATE)
    end = round(2.8 * RATE)
    step = (end - start) // len(tokens)
    words = [
        WordTiming(
            word=token,
            start_sample=start + index * step,
            end_sample=start + (index + 1) * step,
            probability=0.95,
        )
        for index, token in enumerate(tokens)
    ]
    return Sentence(id=0, start_sample=start, end_sample=end, text=text, words=words)


def _state(source: Path) -> ProjectState:
    media = MediaInfo(
        source_path=str(source),
        duration_frames=90,
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
        transcript=[_sentence()],
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
def test_captions_ass_is_populated_utf8_and_burns_pixels(tmp_path: Path) -> None:
    source = _source(tmp_path / "source.mp4")
    state = _state(source)
    context = PipelineContext(
        source=source,
        output=tmp_path / "project",
        work=tmp_path / "project" / "work",
        exports=tmp_path / "project" / "exports",
        media=state.media_info,
        state=state,
        transcript=list(state.transcript),
    )
    CaptionsPlanStep().run(context, CaptionsPlanParams(), StepIO())

    ass_path = context.artifacts["captions_ass"]
    srt_path = context.artifacts["captions_srt"]
    ass = Path(ass_path).read_text(encoding="utf-8")
    srt = Path(srt_path).read_text(encoding="utf-8")
    assert "Dialogue:" in ass
    assert "público" in ass
    assert "império" in ass
    assert "ação" in ass
    assert "pÃºblico" not in ass
    assert "público" in srt
    assert len(srt.split("-->")) > 1

    burned = tmp_path / "project" / "exports" / "burned.mp4"
    plain = tmp_path / "project" / "exports" / "plain.mp4"
    export_mp4(
        state,
        burned,
        ass_path=Path(ass_path),
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

    with_burn = _frame(burned, 1.5, tmp_path / "burn.png")
    without = _frame(plain, 1.5, tmp_path / "plain.png")
    diff = ImageChops.difference(with_burn, without)
    changed = sum(1 for byte in diff.tobytes() if byte)
    total = with_burn.width * with_burn.height * 3
    assert changed / total > 0.005, (changed, total)


def test_read_json_dict_accepts_a_utf8_bom(tmp_path: Path) -> None:
    target = tmp_path / "beat_map.json"
    target.write_bytes(b"\xef\xbb\xbf" + json.dumps({"ok": True}).encode("utf-8"))
    assert read_json_dict(target) == {"ok": True}
