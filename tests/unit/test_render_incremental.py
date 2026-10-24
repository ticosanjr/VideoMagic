"""Shorts render reuse: unchanged Shorts are not rendered again."""

from __future__ import annotations

from pathlib import Path

from videoflow.application.shorts import ShortClip
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.domain.state import MediaInfo, Sentence
from videoflow.steps.base import StepIO
from videoflow.steps.shorts_render import RenderShortsParams, RenderShortsStep


class FakeAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def render_short(self, source, pieces, destination, **kwargs):
        self.calls += 1
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"rendered")
        return Path(destination)


def build(tmp_path: Path, pieces: tuple[tuple[int, int], ...]) -> PipelineContext:
    media = MediaInfo(
        source_path=str(tmp_path / "source.mp4"),
        duration_frames=100,
        fps_num=25,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    clip = ShortClip(
        title="One",
        start_sample=pieces[0][0],
        end_sample=pieces[-1][1],
        sentence_ids=(0,),
        pieces=pieces,
    )
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=media,
        transcript=[Sentence(id=0, start_sample=0, end_sample=48000, text="hello")],
        selected_shorts=[clip],
        shorts=[clip.to_dict(48000)],
    )


def run(context: PipelineContext, adapter: FakeAdapter) -> None:
    RenderShortsStep().run(
        context,
        RenderShortsParams(burn_subtitles=False, caption_style=CaptionStyle()),
        StepIO(stage="render", adapter=adapter),
    )


def test_unchanged_short_is_reused(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    context = build(tmp_path, ((0, 48000),))
    run(context, adapter)
    first = Path(str(context.shorts[0]["path"]))
    first.write_bytes(b"cached")

    run(context, adapter)

    assert adapter.calls == 1
    assert first.read_bytes() == b"cached"


def test_changed_pieces_force_a_new_render(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    context = build(tmp_path, ((0, 48000),))
    run(context, adapter)

    changed = build(tmp_path, ((0, 24000), (24000, 48000)))
    run(changed, adapter)

    assert adapter.calls == 2
