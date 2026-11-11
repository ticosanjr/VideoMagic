"""Shorts renderer: captions, reuse, B-roll approval, SFX, and manifests."""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.test_steps_coverage_extra import (
    make_clip,
    make_context,
    make_media,
    sentence,
)
from videoflow.steps.base import StepIO
from videoflow.steps.shorts_render import RenderShortsParams, RenderShortsStep

RATE = 48000


class FakeAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def render_short(
        self, _source: Path, _pieces: object, destination: Path, **_kwargs: object
    ) -> Path:
        self.calls += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"mp4")
        return destination


def context_with_short(tmp_path: Path):
    context = make_context(
        tmp_path,
        media_info=make_media(tmp_path),
        transcript=[sentence(0, 0, 2 * RATE, "Hello world.")],
    )
    clip = make_clip("One", start=0, end=2 * RATE)
    context.selected_shorts = [clip]
    return context, clip


def test_no_selected_shorts_is_a_noop(tmp_path: Path) -> None:
    context = make_context(tmp_path, media_info=make_media(tmp_path))
    reports: list[str] = []

    RenderShortsStep().run(
        context,
        RenderShortsParams(),
        StepIO(progress=lambda _stage, _pct, message: reports.append(message)),
    )

    assert reports == ["No Shorts selected"]
    assert context.shorts == []


def test_render_writes_captions_and_manifest(tmp_path: Path) -> None:
    context, clip = context_with_short(tmp_path)
    adapter = FakeAdapter()

    RenderShortsStep().run(context, RenderShortsParams(), StepIO(adapter=adapter))

    assert adapter.calls == 1
    [entry] = context.shorts
    assert entry["title"] == "One"
    assert Path(str(entry["path"])).is_file()
    assert Path(str(entry["subtitles"])).is_file()
    report = json.loads((context.output / "shorts.json").read_text(encoding="utf-8"))
    assert report["clips"][0]["title"] == "One"
    assert "shorts_render" in context.hashes
    outputs = RenderShortsStep().cache_outputs(context)
    assert outputs
    assert outputs[0].suffix == ".mp4"


def test_render_reuses_a_matching_manifest(tmp_path: Path) -> None:
    context, _clip = context_with_short(tmp_path)
    adapter = FakeAdapter()
    step = RenderShortsStep()

    options = RenderShortsParams(burn_subtitles=False)
    step.run(context, options, StepIO(adapter=adapter))
    step.run(context, options, StepIO(adapter=adapter))

    assert adapter.calls == 1
    manifest = json.loads(
        (context.output / "shorts" / "render-manifest.json").read_text(encoding="utf-8")
    )
    assert next(iter(manifest["shorts"].values()))["reused"] is True


def test_render_uses_cached_captions_and_can_disable_them(tmp_path: Path) -> None:
    context, _clip = context_with_short(tmp_path)
    cached = context.output / "cached.ass"
    cached.write_text("[Script Info]", encoding="utf-8")
    context.short_captions["One"] = str(cached)
    adapter = FakeAdapter()

    RenderShortsStep().run(context, RenderShortsParams(), StepIO(adapter=adapter))
    assert Path(str(context.shorts[0]["subtitles"])) == cached

    context.metadata["captions_disabled"] = True
    context.short_captions.clear()
    context.hashes.clear()
    RenderShortsStep().run(context, RenderShortsParams(), StepIO(adapter=FakeAdapter()))

    assert "subtitles" not in context.shorts[0]


def test_render_without_transcript_has_no_captions(tmp_path: Path) -> None:
    context, _clip = context_with_short(tmp_path)
    context.transcript = []

    RenderShortsStep().run(context, RenderShortsParams(), StepIO(adapter=FakeAdapter()))

    assert "subtitles" not in context.shorts[0]


def test_sfx_and_broll_assets_are_resolved(tmp_path: Path) -> None:
    context, _clip = context_with_short(tmp_path)
    sfx = tmp_path / "boom.wav"
    sfx.write_bytes(b"wav")
    broll = tmp_path / "cut.mp4"
    broll.write_bytes(b"mp4")
    context.metadata["sfx_plan"] = {
        "One": [
            {"path": str(sfx), "start_sec": 0.5},
            {"path": str(tmp_path / "missing.wav")},
            {"start_sec": 0},
            "bad",
        ]
    }
    context.metadata["broll_plan"] = {
        "One": [
            {"path": str(tmp_path / "missing.mp4")},
            {"path": str(broll), "start_sec": 0.1, "duration_sec": 1.5},
        ]
    }
    (context.output / "broll_approval.json").write_text(
        json.dumps({"One": {"approved": [0, 1], "order": [1, 0]}}), encoding="utf-8"
    )
    seen: dict[str, object] = {}

    class Capture(FakeAdapter):
        def render_short(self, _source, _pieces, destination, **kwargs):  # type: ignore[no-untyped-def]
            seen.update(kwargs)
            return super().render_short(_source, _pieces, destination, **kwargs)

    RenderShortsStep().run(context, RenderShortsParams(), StepIO(adapter=Capture()))

    assert seen["sfx_clips"] == [(sfx, 0.5, 0.9)]
    assert seen["broll_clips"] == [(broll, 0.1, 1.5)]


def test_broll_missing_assets_are_warned(tmp_path: Path) -> None:
    context, _clip = context_with_short(tmp_path)
    missing = tmp_path / "missing.mp4"
    context.metadata["broll_plan"] = {"One": [{"path": str(missing)}]}

    RenderShortsStep().run(context, RenderShortsParams(), StepIO(adapter=FakeAdapter()))

    assert any("B-roll asset missing" in warning for warning in context.warnings)


def test_invalid_render_manifest_is_ignored(tmp_path: Path) -> None:
    context, _clip = context_with_short(tmp_path)
    manifest = context.output / "shorts" / "render-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("[]", encoding="utf-8")

    RenderShortsStep().run(context, RenderShortsParams(), StepIO(adapter=FakeAdapter()))

    assert Path(str(context.shorts[0]["path"])).is_file()


def test_piece_focus_uses_keyframes() -> None:
    from videoflow.adapters.ffmpeg import _piece_focus

    keyframes = [(0.0, 0.2), (0.5, 0.8), (1.0, 0.9)]
    assert round(_piece_focus(keyframes, 0, RATE, RATE, 0.5), 3) == 0.633
    assert _piece_focus(None, 0, RATE, RATE, 0.5) == 0.5
    assert _piece_focus([(0.0, 0.3)], 5 * RATE, 6 * RATE, RATE, 0.5) == 0.3


def test_crop_expression_is_piecewise_linear() -> None:
    from videoflow.adapters.ffmpeg import _crop_expression

    expression = _crop_expression([(0.0, 0.2), (1.0, 0.8)])
    assert "lerp(0.2,0.8" in expression
    assert expression.startswith("if(lt(t,1.0)")


def test_piece_keyframes_are_relative_and_capped() -> None:
    from videoflow.adapters.ffmpeg import _piece_keyframes

    keyframes = [(index * 0.5, 0.5) for index in range(30)]
    piece = _piece_keyframes(keyframes, 2 * RATE, 10 * RATE, RATE)
    assert piece[0][0] == 0.0
    assert piece[-1][0] == 8.0
    assert len(piece) <= 12
