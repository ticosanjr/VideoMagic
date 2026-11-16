"""Delivery package applies the winning thumbnail and lists mix assets."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.deliverables import select_thumbnail
from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.delivery import DeliveryPackageStep, PackageParams


def build_context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    (output / "thumbnails").mkdir(parents=True)
    (output / "thumbnails" / "variant-1-1.png").write_bytes(b"one")
    (output / "thumbnails" / "variant-1-2.png").write_bytes(b"two")
    select_thumbnail(output, "variant-1-2.png")
    music = tmp_path / "music"
    music.mkdir()
    (music / "theme.mp3").write_bytes(b"music")
    sfx = tmp_path / "sfx"
    sfx.mkdir()
    (sfx / "whoosh.wav").write_bytes(b"sfx")
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        shorts=[{"title": "Short one", "path": str(output / "shorts" / "01.mp4")}],
        metadata={"sfx_plan": {"Short one": [{"path": str(sfx / "whoosh.wav")}]}},
    )


def test_package_copies_the_winner_and_lists_assets(tmp_path: Path) -> None:
    context = build_context(tmp_path)

    DeliveryPackageStep().run(context, PackageParams(), StepIO(stage="delivery"))

    manifest = json.loads(
        (context.output / "delivery" / "package.json").read_text(encoding="utf-8")
    )
    assert manifest["thumbnail_winner"] == "variant-1-2.png"
    assert (context.output / "delivery" / "thumbnail.png").read_bytes() == b"two"
    assert manifest["music"] == [str(tmp_path / "music" / "theme.mp3")]
    assert manifest["sfx"] == [str(tmp_path / "sfx" / "whoosh.wav")]
    assert manifest["shorts"][0]["thumbnail"].endswith("thumbnail.png")
    assert context.artifacts["delivery_package"].endswith("package.json")


def test_package_without_a_choice_still_writes_a_manifest(tmp_path: Path) -> None:
    context = build_context(tmp_path)
    (context.output / "thumbnail_choice.json").unlink()

    DeliveryPackageStep().run(
        context, PackageParams(copy_thumbnail=False, include_music=False), StepIO(stage="delivery")
    )

    manifest = json.loads(
        (context.output / "delivery" / "package.json").read_text(encoding="utf-8")
    )
    assert manifest["thumbnail"] == ""
    assert manifest["music"] == []
    assert not (context.output / "delivery" / "thumbnail.png").exists()


def test_package_can_embed_a_multi_nle_bundle(tmp_path: Path) -> None:
    from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment

    context = build_context(tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    context.state = ProjectState(
        media_info=media,
        video_segments=[
            VideoSegment(
                clip_id="c1",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="c1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
    )

    class FakeAdapter:
        def render(self, command, progress=None):
            Path(command[-1]).write_bytes(b"mp4")

    DeliveryPackageStep().run(
        context,
        PackageParams(targets=["resolve"]),
        StepIO(stage="delivery", adapter=FakeAdapter()),
    )

    manifest = json.loads(
        (context.output / "delivery" / "package.json").read_text(encoding="utf-8")
    )
    assert manifest["ok"] is True
    assert manifest["nle_bundle"]["files"]["resolve"]["path"].endswith("timeline.fcpxml")
    assert context.artifacts["delivery_bundle"].endswith("bundle.json")
