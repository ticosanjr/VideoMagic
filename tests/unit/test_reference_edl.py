from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from videoflow.application import reference_edl
from videoflow.application.reference_edl import (
    FlatWord,
    ReferenceEdl,
    _build_intervals_from_blocks,
    _choose_candidate_path,
    _interpolate_indices,
    _map_human_words,
    _smooth,
    _top_candidates,
    align_words,
    build_reference_edl,
    build_reference_edl_from_paths,
    build_reference_edl_from_sentences,
    build_reference_edl_from_words,
    load_reference_edl,
    save_reference_edl,
)
from videoflow.domain.state import Sentence, WordTiming


def _tone(frequency: float, seconds: float, rate: int = 16_000) -> np.ndarray:
    time = np.arange(round(seconds * rate), dtype=np.float32) / rate
    signal = 0.3 * np.sin(2 * np.pi * frequency * time)
    signal += 0.003 * np.random.default_rng(int(frequency)).normal(size=signal.size).astype(
        np.float32
    )
    return signal.astype(np.float32)


def _piecewise(seconds_per_segment: float = 2.0, count: int = 15) -> np.ndarray:
    return np.concatenate(
        [_tone(200.0 + 30.0 * index, seconds_per_segment) for index in range(count)]
    )


def test_interpolate_indices_fills_gaps_and_edges() -> None:
    raw_index = _interpolate_indices(
        [(2, 10), (5, 20)],
        edited_count=7,
        raw_count=100,
    )
    assert raw_index[0] == 8
    assert raw_index[1] == 9
    assert raw_index[2] == 10
    assert raw_index[5] == 20
    assert raw_index[6] == 21


def test_build_reference_edl_recovers_two_known_cuts() -> None:
    raw = _piecewise()
    edited = np.concatenate(
        [raw[5 * 16_000 : 12 * 16_000], raw[20 * 16_000 : 27 * 16_000]]
    )
    edl = build_reference_edl(
        raw,
        edited,
        name="synthetic",
        raw_path=Path("raw.wav"),
        edited_path=Path("edited.wav"),
    )
    assert len(edl.kept_intervals) == 2
    first, second = edl.kept_intervals
    assert abs(first[0] - 5.0) <= 1.0
    assert abs(first[1] - 12.0) <= 1.0
    assert abs(second[0] - 20.0) <= 1.0
    assert abs(second[1] - 27.0) <= 1.0
    assert edl.validation["audio_f1"] >= 0.98
    assert edl.diagnostics["coverage"] > 0.9


def _flat(
    words: list[str],
    *,
    start: float,
    step: float = 0.3,
    sentence_id: int = 0,
) -> list[FlatWord]:
    return [
        FlatWord(
            start=start + index * step,
            end=start + index * step + step * 0.8,
            text=word,
            norm=word,
            sentence_id=sentence_id,
        )
        for index, word in enumerate(words)
    ]


def test_word_alignment_builds_source_intervals() -> None:
    source = _flat([f"s{index}" for index in range(100)], start=0.0)
    human = _flat([f"s{index}" for index in range(10, 30)], start=0.0, sentence_id=0)
    human += _flat(
        [f"s{index}" for index in range(50, 70)], start=6.0, sentence_id=1
    )
    blocks = align_words(human, source)
    intervals = _build_intervals_from_blocks(
        human,
        source,
        blocks,
        raw_duration=30.0,
        edge_seconds=0.0,
    )
    assert len(intervals) == 2
    assert abs(intervals[0][0] - source[10].start) < 0.05
    assert abs(intervals[0][1] - source[29].end) < 0.05
    assert abs(intervals[1][0] - source[50].start) < 0.05
    assert abs(intervals[1][1] - source[69].end) < 0.05


def test_build_reference_edl_from_words_recovers_known_cuts() -> None:
    raw = _piecewise()
    edited = np.concatenate(
        [raw[4 * 16_000 : 10 * 16_000], raw[20 * 16_000 : 26 * 16_000]]
    )
    source_words: list[FlatWord] = []
    for segment in range(15):
        for index in range(4):
            start = segment * 2.0 + index * 0.5
            source_words.append(
                FlatWord(
                    start=start,
                    end=start + 0.45,
                    text=f"seg{segment}word{index}",
                    norm=f"seg{segment}word{index}",
                )
            )
    human_words: list[FlatWord] = []
    cursor = 0.0
    for block, segment in enumerate((2, 3, 4, 10, 11, 12)):
        for index in range(4):
            human_words.append(
                FlatWord(
                    start=cursor,
                    end=cursor + 0.45,
                    text=f"seg{segment}word{index}",
                    norm=f"seg{segment}word{index}",
                    sentence_id=0 if block < 3 else 1,
                )
            )
            cursor += 0.5
    edl = build_reference_edl_from_words(
        raw,
        edited,
        name="synthetic-words",
        raw_path=Path("raw.wav"),
        edited_path=Path("edited.wav"),
        human_words=human_words,
        source_words=source_words,
    )
    assert len(edl.kept_intervals) == 2
    first, second = edl.kept_intervals
    assert abs(first[0] - 4.0) <= 1.0
    assert abs(first[1] - 10.0) <= 1.0
    assert abs(second[0] - 20.0) <= 1.0
    assert abs(second[1] - 26.0) <= 1.0
    assert edl.validation["audio_f1"] >= 0.95


def _sentence(
    identifier: int,
    *,
    start: float,
    words: int,
    step: float = 0.5,
) -> Sentence:
    timings = []
    for index in range(words):
        word_start = start + index * step
        timings.append(
            WordTiming(
                word=f"w{identifier}_{index}",
                start_sample=round(word_start * 16_000),
                end_sample=round((word_start + step * 0.9) * 16_000),
                probability=1.0,
            )
        )
    return Sentence(
        id=identifier,
        start_sample=timings[0].start_sample,
        end_sample=timings[-1].end_sample,
        text=" ".join(word.word for word in timings),
        words=timings,
    )


def test_build_reference_edl_from_sentences_recovers_known_cuts() -> None:
    raw = _piecewise()
    edited = np.concatenate(
        [raw[4 * 16_000 : 10 * 16_000], raw[20 * 16_000 : 26 * 16_000]]
    )
    sentences = [
        _sentence(0, start=0.0, words=12),
        _sentence(1, start=6.0, words=12),
    ]
    edl = build_reference_edl_from_sentences(
        raw,
        edited,
        name="synthetic-sentences",
        raw_path=Path("raw.wav"),
        edited_path=Path("edited.wav"),
        sentences=sentences,
    )
    assert len(edl.kept_intervals) == 2
    first, second = edl.kept_intervals
    assert abs(first[0] - 4.0) <= 1.0
    assert abs(first[1] - 10.0) <= 1.0
    assert abs(second[0] - 20.0) <= 1.0
    assert abs(second[1] - 26.0) <= 1.0
    assert edl.validation["audio_f1"] >= 0.95


def test_map_human_words_interpolates_unmatched_neighbours() -> None:
    source = _flat([f"s{index}" for index in range(10)], start=0.0)
    human = _flat([f"s{index}" for index in range(10)], start=0.0)
    mapped = _map_human_words(human, source, [(2, 2, 1)])
    assert mapped[2][0] == source[2].start
    assert mapped[0][0] < mapped[2][0] < mapped[9][0]
    assert all(duration > 0 for _start, duration in mapped)


def test_interpolate_indices_handles_edges() -> None:
    leading = _interpolate_indices([(2, 5)], edited_count=6, raw_count=10)
    assert list(leading) == [3, 4, 5, 6, 7, 8]
    trailing = _interpolate_indices([(0, 3), (4, 8)], edited_count=6, raw_count=10)
    assert trailing[0] == 3
    assert trailing[5] == 9


def test_smooth_short_inputs_are_unchanged() -> None:
    assert list(_smooth(np.asarray([1.0, 2.0]), size=5)) == [1.0, 2.0]
    assert list(_smooth(np.asarray([4.0]), size=1)) == [4.0]


def test_build_reference_edl_from_paths_wraps_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pcm = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(reference_edl, "load_pcm", lambda _path: pcm)

    def fake_build(raw: np.ndarray, edited: np.ndarray, **kwargs: object) -> ReferenceEdl:
        return ReferenceEdl(
            name=str(kwargs["name"]),
            raw=str(kwargs["raw_path"]),
            edited=str(kwargs["edited_path"]),
            kept_intervals=[(0.0, 1.0)],
        )

    monkeypatch.setattr(reference_edl, "build_reference_edl", fake_build)
    edl = build_reference_edl_from_paths(Path("raw.wav"), Path("edited.wav"), name="demo")
    assert edl.name == "demo"
    assert edl.kept_intervals == [(0.0, 1.0)]


def test_map_human_words_without_matches_uses_zero_start() -> None:
    human = _flat(["a", "b", "c"], start=0.0)
    source = _flat(["x", "y", "z"], start=0.0)
    mapped = _map_human_words(human, source, [])
    assert len(mapped) == 3
    assert all(start == 0.0 for start, _duration in mapped)


def test_map_human_words_interpolates_between_two_matches() -> None:
    human = _flat(["a", "b", "c", "d", "e", "f"], start=0.0)
    source = _flat(["x", "y", "z", "w", "v", "u"], start=0.0)
    mapped = _map_human_words(human, source, [(1, 1, 1), (4, 4, 1)])
    assert mapped[1][0] < mapped[2][0] < mapped[3][0] < mapped[4][0]


def test_top_candidates_keeps_separated_peaks() -> None:
    ncc = np.zeros(1000, dtype=np.float32)
    ncc[100] = 0.9
    ncc[110] = 0.8
    ncc[500] = 0.95
    candidates = _top_candidates(
        ncc,
        factor=1,
        sample_rate=1000,
        top_k=3,
        min_score=0.5,
        min_separation_seconds=0.05,
    )
    assert [round(offset, 3) for offset, _score in candidates] == [0.5, 0.1]


def test_choose_candidate_path_prefers_monotonic_sequence() -> None:
    path = _choose_candidate_path(
        [
            [(0.0, 0.9), (100.0, 1.0)],
            [(50.0, 0.9), (200.0, 0.6)],
        ]
    )
    assert [offset for offset, _score in path] == [0.0, 50.0]
    assert _choose_candidate_path([]) == []


def test_save_and_load_reference_edl(tmp_path: Path) -> None:
    edl = ReferenceEdl(
        name="demo",
        raw="/tmp/raw.mp4",
        edited="/tmp/edited.mp4",
        kept_intervals=[(1.0, 2.0), (4.0, 6.5)],
        validation={"audio_f1": 0.9},
        diagnostics={"mode": "test"},
    )
    path = tmp_path / "edl.json"
    save_reference_edl(path, edl)
    restored = load_reference_edl(path)
    assert restored.kept_intervals == [(1.0, 2.0), (4.0, 6.5)]
    assert restored.validation["audio_f1"] == 0.9
    assert restored.diagnostics["mode"] == "test"


def test_reference_edl_round_trip() -> None:
    edl = ReferenceEdl(
        name="demo",
        raw="/tmp/raw.mp4",
        edited="/tmp/edited.mp4",
        kept_intervals=[(0.0, 1.5), (3.0, 5.25)],
        validation={"audio_f1": 0.99},
        diagnostics={"matches": 10},
    )
    payload = edl.to_dict()
    restored = ReferenceEdl.from_dict(payload)
    assert restored.kept_intervals == [(0.0, 1.5), (3.0, 5.25)]
    assert restored.validation["audio_f1"] == 0.99
    assert payload["kept_intervals_48k"][0] == [0, 72_000]
