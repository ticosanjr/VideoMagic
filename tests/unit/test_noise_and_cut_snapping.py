from __future__ import annotations

from videoflow.application.retakes import snap_cuts_to_silence
from videoflow.application.timeline_builder import (
    build_inactive_segments,
    detect_noise_spans,
)
from videoflow.domain.state import (
    InactiveSpan,
    MediaInfo,
    Sentence,
    VideoSegment,
    WordTiming,
)


def _sentence(identifier: int, text: str, start: int, end: int, word: str) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=start,
        end_sample=end,
        text=text,
        words=[
            WordTiming(
                word=word,
                start_sample=start,
                end_sample=end,
                probability=0.9,
            )
        ],
    )


def test_no_speech_interval_becomes_noise() -> None:
    transcript = [_sentence(0, "real speech", 0, 100_000, "speech")]
    spans = detect_noise_spans(
        [(0, 100_000), (200_000, 300_000)],
        transcript,
        sample_rate=48_000,
        mode="non_speech",
    )
    assert [(span.start_sample, span.end_sample, span.reason) for span in spans] == [
        (200_000, 300_000, "noise")
    ]


def test_watermark_is_noise_only_in_aggressive_mode() -> None:
    transcript = [
        _sentence(
            0,
            "Legendas pela comunidade de Amara.org",
            0,
            100_000,
            "Legendas",
        )
    ]
    conservative = detect_noise_spans(
        [(0, 100_000)],
        transcript,
        sample_rate=48_000,
        mode="non_speech",
    )
    aggressive = detect_noise_spans(
        [(0, 100_000)],
        transcript,
        sample_rate=48_000,
        mode="non_speech_and_nonlexical",
    )
    assert conservative == []
    assert [(span.start_sample, span.end_sample) for span in aggressive] == [
        (0, 100_000)
    ]


def test_noise_filter_ignores_missing_transcript() -> None:
    assert detect_noise_spans([(0, 100_000)], [], sample_rate=48_000) == []


def test_cut_snapping_moves_edges_into_silence() -> None:
    cuts, snapped = snap_cuts_to_silence(
        [(1_000, 2_000)],
        [
            InactiveSpan(start_sample=1_150, end_sample=1_250),
            InactiveSpan(start_sample=1_750, end_sample=1_850),
        ],
        sample_rate=1_000,
        search_ms=400,
    )
    assert cuts == [(1_150, 1_850)]
    assert snapped == 1


def test_cut_snapping_leaves_a_far_cut_alone() -> None:
    cuts, snapped = snap_cuts_to_silence(
        [(1_000, 2_000)],
        [InactiveSpan(start_sample=10_000, end_sample=11_000)],
        sample_rate=1_000,
        search_ms=100,
    )
    assert cuts == [(1_000, 2_000)]
    assert snapped == 0


def test_inactive_gap_reason_prefers_noise() -> None:
    media = MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=600,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48_000,
    )
    active = [
        VideoSegment(
            clip_id="c1",
            source_in_frame=0,
            source_out_frame=300,
            timeline_in_frame=0,
            timeline_out_frame=300,
        )
    ]
    inactive = build_inactive_segments(
        media,
        active,
        noise_spans=[
            InactiveSpan(
                start_sample=480_000,
                end_sample=528_000,
                reason="noise",
            )
        ],
        silence_spans=[
            InactiveSpan(
                start_sample=528_000,
                end_sample=960_000,
                reason="silence",
            )
        ],
    )
    assert len(inactive) == 1
    assert inactive[0].reason == "noise"


def test_transcript_spans_skip_discarded_and_noise_sentences() -> None:
    from videoflow.application.timeline_builder import transcript_spans

    transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=48_000,
            text="First sentence.",
            words=[
                WordTiming(
                    word="First",
                    start_sample=0,
                    end_sample=24_000,
                    probability=0.9,
                ),
                WordTiming(
                    word="sentence.",
                    start_sample=24_000,
                    end_sample=48_000,
                    probability=0.9,
                ),
            ],
        ),
        Sentence(
            id=1,
            start_sample=48_000,
            end_sample=96_000,
            text="Discarded retake.",
            words=[
                WordTiming(
                    word="Discarded",
                    start_sample=48_000,
                    end_sample=72_000,
                    probability=0.9,
                )
            ],
        ),
        Sentence(
            id=2,
            start_sample=96_000,
            end_sample=144_000,
            text="Legendas pela comunidade de Amara.org",
            words=[
                WordTiming(
                    word="Legendas",
                    start_sample=96_000,
                    end_sample=120_000,
                    probability=0.4,
                )
            ],
        ),
        Sentence(
            id=3,
            start_sample=144_000,
            end_sample=192_000,
            text="Last sentence.",
            words=[
                WordTiming(
                    word="Last",
                    start_sample=144_000,
                    end_sample=168_000,
                    probability=0.9,
                ),
                WordTiming(
                    word="sentence.",
                    start_sample=168_000,
                    end_sample=192_000,
                    probability=0.9,
                ),
            ],
        ),
    ]
    spans, noise = transcript_spans(
        transcript,
        {1},
        sample_rate=48_000,
        duration_samples=240_000,
        pad_before_ms=50,
        pad_after_ms=50,
        noise_mode="non_speech",
    )
    assert [(span.start_sample, span.end_sample) for span in noise] == [(96_000, 144_000)]
    assert spans == [(0, 48_000), (144_000, 194_400)]


def test_transcript_spans_clamp_pads_to_the_gap_midpoint() -> None:
    from videoflow.application.timeline_builder import transcript_spans

    transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=48_000,
            text="One.",
            words=[WordTiming(word="One.", start_sample=0, end_sample=48_000, probability=1.0)],
        ),
        Sentence(
            id=1,
            start_sample=52_800,
            end_sample=96_000,
            text="Two.",
            words=[
                WordTiming(
                    word="Two.",
                    start_sample=52_800,
                    end_sample=96_000,
                    probability=1.0,
                )
            ],
        ),
    ]
    spans, _ = transcript_spans(
        transcript,
        set(),
        sample_rate=48_000,
        duration_samples=96_000,
        pad_before_ms=200,
        pad_after_ms=200,
    )
    assert spans == [(0, 50_400), (50_400, 96_000)]


def test_transcript_spans_merge_overlaps_and_remove_aggressive_noise() -> None:
    from videoflow.application.timeline_builder import transcript_spans

    transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=48_000,
            text="First.",
            words=[
                WordTiming(
                    word="First.", start_sample=0, end_sample=48_000, probability=0.9
                )
            ],
        ),
        Sentence(
            id=1,
            start_sample=40_000,
            end_sample=96_000,
            text="Overlap.",
            words=[
                WordTiming(
                    word="Overlap.",
                    start_sample=40_000,
                    end_sample=96_000,
                    probability=0.9,
                )
            ],
        ),
        Sentence(
            id=2,
            start_sample=100_000,
            end_sample=140_000,
            text="...",
            words=[
                WordTiming(
                    word="...", start_sample=100_000, end_sample=140_000, probability=0.2
                )
            ],
        ),
    ]
    spans, noise = transcript_spans(
        transcript,
        set(),
        sample_rate=48_000,
        duration_samples=200_000,
        pad_before_ms=0,
        pad_after_ms=0,
        noise_mode="non_speech_and_nonlexical",
    )
    assert spans == [(0, 96_000)]
    assert [(span.start_sample, span.end_sample) for span in noise] == [
        (100_000, 140_000)
    ]


def test_cut_snapping_without_cuts_or_silence_is_a_noop() -> None:
    assert snap_cuts_to_silence([], [InactiveSpan(start_sample=0, end_sample=10)]) == (
        [],
        0,
    )
    assert snap_cuts_to_silence([(1, 2)], []) == ([(1, 2)], 0)


def _word_sentence(words: list[tuple[str, int, int]]) -> Sentence:
    return Sentence(
        id=0,
        start_sample=words[0][1],
        end_sample=words[-1][2],
        text=" ".join(text for text, _start, _end in words),
        words=[
            WordTiming(
                word=text,
                start_sample=start,
                end_sample=end,
                probability=0.9,
            )
            for text, start, end in words
        ],
    )


def test_word_runs_split_internal_gaps() -> None:
    from videoflow.application.timeline_builder import transcript_spans

    transcript = [
        _word_sentence(
            [
                ("one", 0, 4_800),
                ("two", 24_000, 28_800),
                ("three", 48_000, 52_800),
            ]
        )
    ]
    spans, _noise = transcript_spans(
        transcript,
        set(),
        sample_rate=48_000,
        duration_samples=60_000,
        pad_before_ms=20,
        pad_after_ms=40,
        max_internal_gap_ms=200,
        internal_gap_mode="all",
        drop_isolated_words=False,
    )
    assert len(spans) == 3
    assert spans[0][0] == 0
    assert all(not (start < 20_000 < end) for start, end in spans)


def test_smart_gap_keeps_long_speech_but_removes_short_cough() -> None:
    from videoflow.application.timeline_builder import transcript_spans

    long_gap = [
        _word_sentence(
            [
                ("one", 0, 4_800),
                ("two", 52_800, 57_600),
            ]
        )
    ]
    kept, _noise = transcript_spans(
        long_gap,
        set(),
        sample_rate=48_000,
        duration_samples=96_000,
        max_internal_gap_ms=200,
        internal_gap_mode="smart",
        gap_energy_threshold=800,
        long_gap_ms=800,
        rms_at=lambda _start, _end: 1_000,
        drop_isolated_words=False,
    )
    quiet, _noise = transcript_spans(
        long_gap,
        set(),
        sample_rate=48_000,
        duration_samples=96_000,
        max_internal_gap_ms=200,
        internal_gap_mode="smart",
        gap_energy_threshold=800,
        long_gap_ms=800,
        rms_at=lambda _start, _end: 100,
        drop_isolated_words=False,
    )
    short_gap = [
        _word_sentence(
            [
                ("one", 0, 4_800),
                ("two", 19_200, 24_000),
            ]
        )
    ]
    short, _noise = transcript_spans(
        short_gap,
        set(),
        sample_rate=48_000,
        duration_samples=48_000,
        max_internal_gap_ms=200,
        internal_gap_mode="smart",
        rms_at=lambda _start, _end: 1_000,
        drop_isolated_words=False,
    )
    assert len(kept) == 1
    assert len(quiet) == 2
    assert len(short) == 2


def test_isolated_content_word_tail_is_kept() -> None:
    from videoflow.application.timeline_builder import transcript_spans

    transcript = [
        _word_sentence(
            [
                ("complete", 0, 9_600),
                ("sentence", 9_600, 19_200),
                ("tail", 48_000, 52_800),
            ]
        )
    ]
    spans, noise = transcript_spans(
        transcript,
        set(),
        sample_rate=48_000,
        duration_samples=60_000,
        max_internal_gap_ms=200,
        internal_gap_mode="all",
        drop_isolated_words=True,
    )
    assert len(spans) == 2
    assert spans[-1][0] <= 48_000 <= spans[-1][1]
    assert not any(span.start_sample == 48_000 for span in noise)


def test_isolated_filler_tail_is_dropped() -> None:
    from videoflow.application.timeline_builder import transcript_spans

    transcript = [
        _word_sentence(
            [
                ("complete", 0, 9_600),
                ("sentence", 9_600, 19_200),
                ("hum", 48_000, 52_800),
            ]
        )
    ]
    spans, noise = transcript_spans(
        transcript,
        set(),
        sample_rate=48_000,
        duration_samples=60_000,
        max_internal_gap_ms=200,
        internal_gap_mode="all",
        drop_isolated_words=True,
    )
    assert len(spans) == 1
    assert any(span.start_sample == 48_000 for span in noise)


def test_forced_overlap_cut_removes_a_speech_like_gap() -> None:
    from videoflow.application.timeline_builder import transcript_spans

    transcript = [
        _word_sentence(
            [
                ("one", 0, 4_800),
                ("two", 52_800, 57_600),
            ]
        )
    ]
    spans, _noise = transcript_spans(
        transcript,
        set(),
        sample_rate=48_000,
        duration_samples=96_000,
        max_internal_gap_ms=200,
        internal_gap_mode="smart",
        gap_energy_threshold=800,
        long_gap_ms=800,
        rms_at=lambda _start, _end: 2_000,
        forced_cuts=[(4_800, 52_800)],
        drop_isolated_words=False,
    )
    assert len(spans) == 2
    assert all(not (start < 40_000 < end) for start, end in spans)
