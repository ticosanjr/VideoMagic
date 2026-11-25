"""v4.9.0: manual discards must not erase the following good take."""

from __future__ import annotations

from pathlib import Path

from videoflow.application.decupage.deterministic import build_safe_speech_spans
from videoflow.application.decupage.snap import build_plan
from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, ProjectState, Sentence, WordTiming
from videoflow.steps.base import StepIO
from videoflow.steps.decupage_snap import DecupageTimelineParams, DecupageTimelineStep
from videoflow.steps.editorial_clean import EditorialCleanParams, apply_editorial_clean

RATE = 48_000


def _sentence(
    identifier: int,
    start_sec: float,
    end_sec: float,
    text: str,
) -> Sentence:
    tokens = text.split()
    start = round(start_sec * RATE)
    end = round(end_sec * RATE)
    step = max(1, (end - start) // max(1, len(tokens)))
    words = [
        WordTiming(
            word=token,
            start_sample=start + index * step,
            end_sample=start + (index + 1) * step,
            probability=0.92,
        )
        for index, token in enumerate(tokens)
    ]
    return Sentence(
        id=identifier,
        start_sample=start,
        end_sample=end,
        text=text,
        words=words,
    )


def _context(tmp_path: Path) -> PipelineContext:
    media = MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=30 * 30,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=RATE,
    )
    state = ProjectState(media_info=media, sources={"primary": media}, primary_source_id="primary")
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=media,
        state=state,
    )


def test_manual_discards_do_not_erase_the_next_good_take(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript = [
        _sentence(0, 0.0, 2.0, "primeira tentativa sem ponto final"),
        _sentence(1, 2.0, 4.0, "segunda tentativa sem ponto final"),
        _sentence(2, 5.0, 25.0, "frase boa que deve permanecer inteira."),
    ]
    context.discard_sentence_ids = [0, 1]

    apply_editorial_clean(
        context,
        EditorialCleanParams(semantic=False, second_pass=False),
        StepIO(),
    )

    kept = [
        sentence
        for sentence in context.transcript
        if sentence.id not in set(context.discard_sentence_ids)
    ]
    assert any(sentence.id == 2 for sentence in kept), [
        (sentence.id, sentence.text) for sentence in context.transcript
    ]
    good = next(sentence for sentence in kept if sentence.id == 2)
    assert good.words
    assert good.start_sample == round(5.0 * RATE)
    assert good.end_sample == round(25.0 * RATE)

    context.speech_intervals = [(0, round(25.0 * RATE))]
    spans, _flags = build_safe_speech_spans(
        context.speech_intervals,
        kept,
        set(),
        sample_rate=RATE,
        duration_samples=round(25.0 * RATE),
    )
    assert any(start <= round(5.0 * RATE) and end >= round(25.0 * RATE) for start, end in spans)

    plan = build_plan(
        context.media,
        [],
        [],
        profile={},
        base_spans=spans,
        noise_events=[],
        review_flags=[],
        min_clip_ms=0,
    )
    context.metadata["decupage_plan"] = plan.model_dump(mode="json")
    DecupageTimelineStep().run(
        context,
        DecupageTimelineParams(expected_revision=1, replace_manual=False),
        StepIO(),
    )
    assert context.state is not None
    timeline_frames = sum(
        segment.timeline_out_frame - segment.timeline_in_frame
        for segment in context.state.video_segments
    )
    timeline_duration = timeline_frames / 30
    report_duration = float(plan.metrics["final_duration_sec"])
    assert abs(report_duration - timeline_duration) <= 0.05
    assert timeline_duration >= 19.9


def test_kept_sentence_without_words_keeps_its_interval() -> None:
    sentence = Sentence(
        id=2,
        start_sample=round(5.0 * RATE),
        end_sample=round(25.0 * RATE),
        text="frase transcrita sem word timings.",
        words=[],
    )
    spans, _flags = build_safe_speech_spans(
        [],
        [sentence],
        set(),
        sample_rate=RATE,
        duration_samples=round(30.0 * RATE),
    )
    assert any(
        start <= round(5.0 * RATE) and end >= round(25.0 * RATE)
        for start, end in spans
    )


def test_decupage_diff_lists_the_removed_text() -> None:
    from videoflow.application.decupage.snap import diff_markdown

    media = MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=30 * 30,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=RATE,
    )
    sentences = [
        _sentence(0, 0.0, 2.0, "primeira tentativa sem ponto final"),
        _sentence(1, 2.0, 4.0, "segunda tentativa sem ponto final"),
        _sentence(2, 5.0, 25.0, "frase boa que deve permanecer inteira."),
    ]
    plan = build_plan(
        media,
        [],
        [{"start_sample": 0, "end_sample": round(5.0 * RATE), "reason": "retake"}],
        profile={},
        base_spans=[(0, round(25.0 * RATE))],
        noise_events=[],
        review_flags=[],
        min_clip_ms=0,
    )
    diff = diff_markdown(plan, sentences)
    assert "[CORTADO 0.000s–5.000s]" in diff
    assert "primeira tentativa" in diff
    assert "frase boa" not in diff
