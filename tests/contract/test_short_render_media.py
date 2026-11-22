from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.short_composition.captions import CaptionBlock, build_short_ass
from videoflow.core.context import PipelineContext
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan, ShortSegment
from videoflow.steps.base import StepIO
from videoflow.steps.short_export import ShortExportParams, ShortExportStep
from videoflow.steps.short_qa import ShortQaParams, ShortQaStep
from videoflow.steps.short_render import ShortRenderParams, ShortRenderStep

pytestmark = pytest.mark.media


def ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        pytest.skip("FFmpeg is not on PATH")
    return binary


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    target = tmp_path / "source.mp4"
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
            "testsrc2=size=320x180:rate=30:duration=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            "4",
            str(target),
        ],
        check=True,
        capture_output=True,
    )
    return target


def test_short_render_step_writes_vertical_mp4(
    source: Path, tmp_path: Path, monkeypatch
) -> None:
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
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
            "sine=frequency=880:sample_rate=48000:duration=0.3",
            str(sfx_dir / "whoosh_soft.wav"),
        ],
        check=True,
        capture_output=True,
    )
    from videoflow.steps import short_export as export_module
    from videoflow.steps import shorts_render as step_module

    monkeypatch.setattr(step_module, "sfx_dir", lambda: sfx_dir)
    monkeypatch.setattr(export_module, "sfx_dir", lambda: sfx_dir)
    manifest = ScenesManifest(
        video_id="sha-render",
        resolution={"w": 320, "h": 180},
        fps_num=30,
        fps_den=1,
        scenes=[
            SceneEntry(
                scene_id="SC_0001",
                start_sample=0,
                end_sample=192_000,
                start_sec=0.0,
                end_sec=4.0,
                layout_type="TALKING_HEAD",
                face_count=1,
                face_bbox_norm={"cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3},
                face_area_ratio=0.06,
                edge_density=0.02,
                sharpness_laplacian=120.0,
                editing_hints=["SAFE_FOR_BROLL"],
            )
        ],
    )
    plan = ShortCompositionPlan(
        short_id="SH",
        source_video_path=str(source),
        start=0.0,
        end=4.0,
        segments=[
            ShortSegment(
                seg_id="S1",
                rel_start=0.0,
                rel_end=4.0,
                layout="FULL_FACE",
            )
        ],
    )
    output = tmp_path / "out"
    captions = output / "shorts" / "SH" / "captions.ass"
    captions.parent.mkdir(parents=True)
    captions.write_text(
        build_short_ass(
            [
                CaptionBlock(
                    0.2,
                    3.8,
                    ("hello", "world"),
                    layout="FULL_FACE",
                    subtitle_y=1360,
                )
            ]
        ),
        encoding="utf-8",
    )
    cues = {
        "captions": [
            {
                "start": 0.2,
                "end": 3.8,
                "text": "hello world",
                "lines": ["hello world"],
                "layout": "FULL_FACE",
                "subtitle_y": 1360,
            }
        ],
        "ending": {
            "content_end_sec": 4.0,
            "effective_end_sec": 4.35,
            "fade_out_ms": 80,
        },
        "sfx": [
            {
                "asset": "whoosh_soft.wav",
                "time_sec": 1.0,
                "volume_db": -18.0,
            }
        ],
    }
    context = PipelineContext(
        source=source,
        output=output,
        work=tmp_path / "work",
        exports=tmp_path / "exports",
    )
    context.metadata["short_plan"] = plan.model_dump(mode="json")
    context.metadata["scenes_manifest"] = manifest.model_dump(mode="json")
    context.metadata["short_cues"] = cues
    context.artifacts["short_captions"] = str(captions)
    context.media = FFmpegAdapter().probe(source)
    ShortRenderStep().run(
        context,
        ShortRenderParams(
            compute_policy="local",
            encoder="libx264",
            output_name="short.mp4",
            keep_intermediates=False,
        ),
        StepIO(),
    )
    rendered = Path(context.artifacts["short_render"])
    assert rendered.is_file()
    assert rendered == output / "shorts" / "SH" / "short.mp4"
    media = FFmpegAdapter().probe(rendered)
    assert (media.width, media.height) == (1080, 1920)
    duration = media.duration_frames * media.fps_den / media.fps_num
    assert 4.2 <= duration <= 4.6
    report = json.loads(
        Path(context.artifacts["short_render_report"]).read_text(encoding="utf-8")
    )
    assert report["placement"] == "local"
    assert report["degraded"] is False
    assert report["segment_count"] == 1

    ShortExportStep().run(context, ShortExportParams(), StepIO())
    export = context.metadata["short_export"]
    assert export["ok"] is True
    assert export["tracks"] == {
        "V1": 1,
        "V2": 1,
        "A1": 1,
        "A2": 1,
        "captions": 1,
    }
    assert Path(context.artifacts["short_fcpxml"]).is_file()

    ShortQaStep().run(context, ShortQaParams(), StepIO())
    qa = context.metadata["short_qa"]
    assert qa["ok"] is True
    assert qa["tracks"]["V2"] == 1
    assert qa["tracks"]["A2"] == 1
    assert Path(context.artifacts["short_qa"]).is_file()
