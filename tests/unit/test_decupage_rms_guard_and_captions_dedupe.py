"""v4.8.0 decupage guards and caption de-duplication."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from videoflow.application.beatmap import apply_beatmap
from videoflow.application.captions import (
    caption_lines,
    filter_caption_sentences,
)
from videoflow.application.decupage.deterministic import rms_energy_guard
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)

RATE = 16_000


def _word(text: str, start: float, end: float) -> WordTiming:
    return WordTiming(
        word=text,
        start_sample=round(start * RATE),
        end_sample=round(end * RATE),
        probability=0.95,
    )


def _sentence(identifier: int, words: list[WordTiming]) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=words[0].start_sample,
        end_sample=words[-1].end_sample,
        text=" ".join(word.word for word in words),
        words=words,
    )


def test_rms_guard_preserves_a_word_with_early_timestamp() -> None:
    seconds = 2.0
    count = round(seconds * RATE)
    noise = 10 ** (-55.0 / 20.0)
    voice = 10 ** (-18.0 / 20.0)
    samples = np.full(count, noise, dtype=np.float32)
    first = round(1.000 * RATE)
    last = round(1.500 * RATE)
    samples[first:last] = voice

    guarded = rms_energy_guard(
        [(round(1.12 * RATE), round(1.50 * RATE))],
        samples=samples,
        sample_rate=RATE,
        duration_samples=count,
    )

    assert len(guarded) == 1
    start, end = guarded[0]
    assert start <= round(1.01 * RATE)
    assert start >= round(0.99 * RATE)
    assert end >= round(1.50 * RATE)


def test_rms_guard_stops_at_the_deliberate_cut() -> None:
    count = 2 * RATE
    samples = np.full(count, 10 ** (-55.0 / 20.0), dtype=np.float32)
    samples[round(1.0 * RATE) : round(1.5 * RATE)] = 10 ** (-18.0 / 20.0)

    guarded = rms_energy_guard(
        [(round(1.12 * RATE), round(1.48 * RATE))],
        samples=samples,
        sample_rate=RATE,
        duration_samples=count,
        blocked_spans=[(0, round(1.10 * RATE))],
    )

    assert guarded[0][0] >= round(1.10 * RATE)


def _long_state(tmp_path: Path) -> ProjectState:
    duration_frames = round(125.35 * 30)
    samples = round(duration_frames / 30 * 48_000)
    media = MediaInfo(
        source_path=str(tmp_path / "source.mp4"),
        duration_frames=duration_frames,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48_000,
    )
    return ProjectState(
        media_info=media,
        video_segments=[
            VideoSegment(
                clip_id="c1",
                source_in_frame=0,
                source_out_frame=duration_frames,
                timeline_in_frame=0,
                timeline_out_frame=duration_frames,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="c1",
                source_in_sample=0,
                source_out_sample=samples,
                timeline_in_sample=0,
                timeline_out_sample=samples,
            )
        ],
    )


def test_apply_beatmap_without_apply_cuts_keeps_the_timeline(tmp_path: Path) -> None:
    state = _long_state(tmp_path)
    for index in range(2):
        asset = tmp_path / "assets" / "broll" / f"br_{index}.mp4"
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(b"clip")

    duration_before = max(clip.timeline_out_frame for clip in state.video_segments)
    updated, report, _sidecar = apply_beatmap(
        state,
        tmp_path,
        {
            "keep_ranges": [{"start_sec": 0.0, "end_sec": 10.0}],
            "broll": [
                {
                    "path": "assets/broll/br_0.mp4",
                    "start_frame": 27 * 30,
                    "duration_frames": 30,
                },
                {
                    "path": "assets/broll/br_1.mp4",
                    "start_frame": 60 * 30,
                    "duration_frames": 30,
                },
            ],
        },
    )

    assert report.ok is True
    assert report.cuts == 0
    assert report.overlays == 2
    duration_after = max(clip.timeline_out_frame for clip in updated.video_segments)
    assert duration_after == duration_before
    assert updated.video_segments == state.video_segments
    assert updated.audio_segments == state.audio_segments


def test_caption_lines_dedupe_similar_cues_within_two_seconds() -> None:
    first = _sentence(0, [_word("this", 0.0, 0.2), _word("is", 0.2, 0.4), _word("final", 0.4, 0.9)])
    second = _sentence(
        1,
        [_word("this", 0.9, 1.1), _word("is", 1.1, 1.3), _word("final", 1.3, 1.8)],
    )
    lines = caption_lines(
        [first, second],
        [(0, 3 * RATE)],
        sample_rate=RATE,
        word_timing="word",
    )
    assert len(lines) == 1

    different = _sentence(2, [_word("completely", 2.4, 2.8), _word("different", 2.8, 3.0)])
    extended = caption_lines(
        [first, different],
        [(0, 3 * RATE)],
        sample_rate=RATE,
        word_timing="word",
    )
    assert len(extended) == 2


def test_caption_filter_drops_discards_and_words_outside_segments() -> None:
    kept = _sentence(
        0,
        [_word("alpha", 0.2, 0.5), _word("beta", 1.0, 1.4), _word("late", 5.0, 5.4)],
    )
    discarded = _sentence(1, [_word("discard", 0.6, 0.9)])

    filtered = filter_caption_sentences(
        [kept, discarded],
        discard_ids={1},
        kept_source_ranges=[(0, 3 * RATE)],
    )

    assert len(filtered) == 1
    assert filtered[0].id == 0
    assert filtered[0].text == "alpha beta"
    assert [word.word for word in filtered[0].words] == ["alpha", "beta"]
