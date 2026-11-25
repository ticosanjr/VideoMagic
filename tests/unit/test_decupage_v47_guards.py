"""v4.7.0 decupage guards: word safety, cull fallback, review packet."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from videoflow.application.beatmap_plan import build_beatmap_plan
from videoflow.application.decupage.deterministic import build_safe_speech_spans
from videoflow.application.decupage.snap import build_plan
from videoflow.application.editorial_clean import (
    build_decupage_review_packet,
    clean_editorial,
)
from videoflow.application.silence import PACING_PROFILES, resolve_pacing_profile
from videoflow.core.context import PipelineContext
from videoflow.domain.config import ZoomsConfig
from videoflow.domain.decupage import Asu, AsuWord
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    PipelineState,
    ProjectState,
    SampleSpan,
    Sentence,
    VideoSegment,
    WordTiming,
)
from videoflow.domain.styles import StyleDefinition
from videoflow.steps.base import StepIO
from videoflow.steps.decupage_snap import SnapParams
from videoflow.steps.session_cull import SessionCullParams, SessionCullStep
from videoflow.steps.timeline import TimelineParams

RATE = 48_000


def _media(frames: int = 30) -> MediaInfo:
    return MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=frames,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=RATE,
    )


def _sentence(
    identifier: int,
    start: int,
    end: int,
    text: str,
    *,
    words: list[WordTiming] | None = None,
) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=start,
        end_sample=end,
        text=text,
        words=words or [],
    )


def _context(tmp_path: Path) -> PipelineContext:
    media = _media(frames=30)
    state = ProjectState(
        media_info=media,
        sources={"src1": media},
        primary_source_id="src1",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="src1",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_id="src1",
                source_in_sample=0,
                source_out_sample=RATE,
                timeline_in_sample=0,
                timeline_out_sample=RATE,
            )
        ],
    )
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=media,
        state=state,
        transcript=[_sentence(0, 0, RATE, "take único")],
    )


def test_pacing_profiles_match_v47_defaults() -> None:
    assert PACING_PROFILES["tight"] == {
        "min_silence_ms": 260,
        "max_pause_ms": 260,
        "pad_before_ms": 75,
        "pad_after_ms": 115,
        "qa_dead_air_ms": 650,
        "min_cut_gap_ms": 140,
    }
    assert PACING_PROFILES["balanced"]["min_silence_ms"] == 380
    assert PACING_PROFILES["balanced"]["qa_dead_air_ms"] == 900
    resolved = resolve_pacing_profile("tight", max_pause_ms=300)
    assert resolved["max_pause_ms"] == 300
    assert resolved["min_cut_gap_ms"] == 140


def test_session_cull_restores_the_timeline_instead_of_removing_every_clip(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    original_video = list(context.state.video_segments) if context.state else []
    original_audio = list(context.state.audio_segments) if context.state else []
    SessionCullStep().run(
        context,
        SessionCullParams(discard_sentence_ids=[0]),
        StepIO(),
    )
    assert context.state is not None
    assert context.state.video_segments == original_video
    assert context.state.audio_segments == original_audio
    report = context.metadata["session_cull_report"]
    assert report["restored_all"] is True
    assert report["warning"] == "cull_guard_restored_all"
    assert report["requested_discarded_sentences"] == 1
    assert any("cull_guard_restored_all" in item for item in context.warnings)


def test_safe_spans_protect_low_confidence_words_with_75_115_padding() -> None:
    word_start = 10 * RATE
    word_end = 11 * RATE
    words = [
        WordTiming(
            word="palavra",
            start_sample=word_start,
            end_sample=word_end,
            probability=0.40,
        )
    ]
    spans, _flagged = build_safe_speech_spans(
        [],
        [_sentence(0, word_start, word_end, "palavra", words=words)],
        set(),
        sample_rate=RATE,
        duration_samples=15 * RATE,
    )
    assert spans
    start, end = spans[0]
    assert start <= word_start - round(0.075 * RATE)
    assert end >= word_end + round(0.115 * RATE)


def test_snap_plan_never_cuts_a_kept_word() -> None:
    word = AsuWord(
        idx=0,
        w="palavra",
        start_sample=10 * RATE,
        end_sample=11 * RATE,
        start_sec=10.0,
        end_sec=11.0,
        p=0.9,
    )
    asu = Asu(
        asu_id="ASU_1",
        start_sample=10 * RATE,
        end_sample=11 * RATE,
        start_sec=10.0,
        end_sec=11.0,
        text="palavra",
        words=[word],
        avg_word_prob=0.9,
    )
    plan = build_plan(
        _media(frames=15 * 30),
        [asu],
        [],
        profile={"db": [-60.0] * 4000, "hop_samples": 480},
        noise_events=[],
        review_flags=[],
        min_clip_ms=0,
        pre_roll_ms=0,
        post_roll_ms=0,
        pre_roll_floor_ms=75,
        post_roll_floor_ms=115,
    )
    span = plan.active_spans[0]
    assert span.start_sample <= word.start_sample - round(0.075 * RATE)
    assert span.end_sample >= word.end_sample + round(0.115 * RATE)


def test_repeated_content_word_is_removed() -> None:
    sentence = _sentence(
        0,
        0,
        RATE,
        "forma forma",
        words=[
            WordTiming(word="forma", start_sample=0, end_sample=RATE // 3, probability=0.9),
            WordTiming(
                word="forma",
                start_sample=RATE // 2,
                end_sample=RATE,
                probability=0.9,
            ),
        ],
    )
    result = clean_editorial([sentence], semantic=False, second_pass=False)
    assert result.transcript
    assert result.transcript[0].text == "forma"
    assert [word.word for word in result.transcript[0].words] == ["forma"]


def test_review_packet_returns_every_sentence_and_flags_retakes() -> None:
    state = ProjectState(
        media_info=_media(),
        transcript=[
            _sentence(0, 0, 1000, "primeira tentativa"),
            _sentence(1, 1000, 2000, "segunda tentativa completa"),
            _sentence(2, 2000, 3000, "frase única"),
        ],
        pipeline=PipelineState(
            metadata={
                "editorial_clean": {
                    "semantic_candidates": [
                        {
                            "sentence_id": 0,
                            "keeper_id": 1,
                            "similarity": 0.82,
                            "reason": "semantic_retake_candidate",
                        }
                    ]
                }
            },
            discard_sentence_ids=[2],
        ),
    )
    packet = build_decupage_review_packet(state)
    assert packet["count"] == 3
    assert packet["discarded_sentence_ids"] == [2]
    by_id = {item["id"]: item for item in packet["sentences"]}
    assert by_id[0]["flags"] == ["SUSPECT_RETAKE"]
    assert by_id[1]["flags"] == ["SUSPECT_RETAKE"]
    assert by_id[2]["flags"] == ["DISCARDED"]
    assert "SUSPECT_RETAKE" in packet["text"]
    assert "[2] [DISCARDED]" in packet["text"]


def test_plan_fills_ranges_from_safe_spans_without_a_timeline() -> None:
    state = ProjectState(
        media_info=_media(frames=15 * 30),
        transcript=[_sentence(0, 0, RATE, "texto")],
        pipeline=PipelineState(
            metadata={"decupage_safe_spans": [[0, RATE], [2 * RATE, 3 * RATE]]}
        ),
    )
    plan = build_beatmap_plan(state, StyleDefinition(style_id="s", name="S"))
    assert plan["keep_ranges"]
    assert plan["remove_ranges"]
    assert plan["time_basis"] == "source"


def test_plan_fills_ranges_from_vad_when_no_transcript_or_timeline() -> None:
    state = ProjectState(
        media_info=_media(frames=15 * 30),
        vad_intervals=[SampleSpan(start_sample=0, end_sample=RATE)],
    )
    plan = build_beatmap_plan(state, StyleDefinition(style_id="s", name="S"))
    assert plan["keep_ranges"]
    assert plan["remove_ranges"]


def test_punch_in_defaults_are_capped_at_108() -> None:
    assert ZoomsConfig().punch_in_scale == 1.06
    assert ZoomsConfig().max_scale == 1.08
    assert TimelineParams().punch_in_scale == 1.06
    assert TimelineParams().zoom_max_scale == 1.08
    assert SnapParams().pre_roll_ms == 75
    assert SnapParams().post_roll_ms == 115
    assert SnapParams().min_cut_gap_ms == 140
    with pytest.raises(ValidationError):
        ZoomsConfig(punch_in_scale=1.09)
    with pytest.raises(ValidationError):
        TimelineParams(punch_in_scale=1.09)


def test_vf_decupage_review_packet_returns_the_whole_transcript(
    tmp_path: Path, monkeypatch
) -> None:
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.mcp_server.core_tools.official import register_official_tools

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    record, state = init_project(
        project_id="review-demo",
        name="Review demo",
        output=tmp_path / "review-demo",
    )
    state = state.model_copy(
        update={
            "media_info": _media(),
            "transcript": [
                _sentence(0, 0, 1000, "primeira tentativa"),
                _sentence(1, 1000, 2000, "segunda tentativa completa"),
            ],
        }
    )
    save_project_state(record, state, bump_revision=False)
    captured: dict[str, object] = {}

    def register(func):
        captured[func.__name__] = func
        return func

    def noop(**kwargs):
        return {"ok": True}

    register_official_tools(
        register,
        {
            "vf_beatmap_plan": noop,
            "vf_run": noop,
            "vf_transcript_query": noop,
            "vf_shorts_batch": noop,
            "vf_qa_final": noop,
            "vf_job": noop,
        },
    )
    result = captured["vf_decupage"](
        action="review_packet",
        project_id="review-demo",
    )
    assert result["ok"] is True
    assert result["action"] == "review_packet"
    assert result["count"] == 2
    assert result["project_id"] == "review-demo"
