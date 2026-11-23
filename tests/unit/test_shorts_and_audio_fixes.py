from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.curation_board import CurationItem
from videoflow.application.shorts import select_shorts
from videoflow.application.shorts_batch import (
    MIN_SHORT_DURATION_SEC,
    ShortsClipSpec,
    run_shorts_batch,
)
from videoflow.core.media_contract import (
    LOUDNORM_TARGET_TP_DB,
    QA_MAX_TRUE_PEAK_DBTP,
    TARGET_LUFS,
    TOLERANCE_LUFS,
)
from videoflow.domain.errors import ExportError
from videoflow.domain.state import Sentence
from videoflow.steps.base import StepIO

RATE = 48_000


def _sentence(identifier: int, start: int, end: int, text: str | None = None) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=start * RATE,
        end_sample=end * RATE,
        text=text or ("gato", "cachorro", "pássaro")[identifier % 3] + " conteúdo exclusivo",
    )


def test_short_spec_aliases_timeline_and_burns_by_default() -> None:
    spec = ShortsClipSpec(start_sec=0, end_sec=4, time_basis="timeline")
    assert spec.time_basis == "edited"
    assert spec.burn_subtitles is True


def test_selection_honours_count_and_prefers_camera_scenes() -> None:
    sentences = [_sentence(index, index * 10, (index + 1) * 10) for index in range(3)]
    clips = select_shorts(
        sentences,
        min_samples=10 * RATE,
        max_samples=10 * RATE,
        count=2,
        sample_rate=RATE,
    )
    assert len(clips) == 2
    assert len({tuple(clip.sentence_ids) for clip in clips}) == 2

    camera = select_shorts(
        sentences[:2],
        min_samples=10 * RATE,
        max_samples=10 * RATE,
        count=1,
        sample_rate=RATE,
        scene_layouts=[
            (0, 10 * RATE, "TALKING_HEAD"),
            (10 * RATE, 20 * RATE, "SCREEN_SHARE_FULL"),
        ],
    )
    assert camera
    assert camera[0].start_sample == 0


def test_batch_burns_subtitles_by_default_and_can_disable_them(
    tmp_path: Path, monkeypatch
) -> None:
    from tests.unit.test_shorts_batch_spec import _project, _Renderer

    record = _project(tmp_path, monkeypatch)
    renderer = _Renderer()
    result = run_shorts_batch(
        record.project_id,
        [{"start_sec": 4, "end_sec": 7, "title": "Burn"}],
        adapter=renderer,
    )
    assert renderer.calls[0]["ass_path"] is not None
    assert result["clips"][0]["burn_subtitles"] is True
    assert Path(result["clips"][0]["subtitles"]).is_file()

    renderer = _Renderer()
    run_shorts_batch(
        record.project_id,
        [{"start_sec": 4, "end_sec": 7, "title": "No burn", "burn_subtitles": False}],
        adapter=renderer,
    )
    assert renderer.calls[0]["ass_path"] is None


def test_batch_rejects_sub_three_second_clip_before_rendering(
    tmp_path: Path, monkeypatch
) -> None:
    from tests.unit.test_shorts_batch_spec import _project, _Renderer

    record = _project(tmp_path, monkeypatch)
    renderer = _Renderer()
    with pytest.raises(ExportError, match="invalid_short_duration"):
        run_shorts_batch(
            record.project_id,
            [{"start_sec": 0, "end_sec": 0.3, "title": "Tiny"}],
            adapter=renderer,
        )
    assert renderer.calls == []
    assert MIN_SHORT_DURATION_SEC == 3.0
    assert not list((Path(record.output) / "shorts" / "batch").glob("*.mp4"))


def test_audio_contract_constants_and_curation_categories() -> None:
    assert TARGET_LUFS == -16.0
    assert TOLERANCE_LUFS == 1.5
    assert LOUDNORM_TARGET_TP_DB == -2.0
    assert QA_MAX_TRUE_PEAK_DBTP == -1.0
    for category in ("short", "cut_review"):
        item = CurationItem(
            item_id=f"{category}-1",
            category=category,
            title=category,
            media_type="video",
        )
        assert item.category == category


def test_video_export_finalizes_missing_mix(monkeypatch, tmp_path: Path) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.domain.state import MediaInfo, ProjectState
    from videoflow.steps import video_export

    output = tmp_path / "out"
    (output / "audio").mkdir(parents=True)
    (output / "audio" / "master.wav").write_bytes(b"master")
    media = MediaInfo(
        source_path=str(tmp_path / "source.mp4"),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=RATE,
    )
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=media,
        state=ProjectState(media_info=media),
    )
    calls: list[str] = []

    def fake_finalize(self, ctx, params, io):
        calls.append("finalize")
        target = ctx.output / "audio" / "final_mix.wav"
        target.write_bytes(b"mix")
        ctx.artifacts["audio_final_mix"] = str(target)
        ctx.artifacts["audio_mix"] = str(target)

    def fake_render(state, destination, **kwargs):
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"video")
        return Path(destination)

    monkeypatch.setattr(
        "videoflow.steps.audio_finalize.AudioFinalizeStep.run", fake_finalize
    )
    monkeypatch.setattr(video_export, "render_master", fake_render)
    video_export.VideoExportStep().run(
        context,
        video_export.VideoExportParams(
            filename_mode="fixed", filename="mix.mp4", audio_source="mix"
        ),
        StepIO(),
    )
    assert calls == ["finalize"]
    assert (output / "audio" / "final_mix.wav").is_file()
    assert context.artifacts["video"].endswith("mix.mp4")
