"""Build a reference edit-decision list (EDL) from a human-edited video.

The human edit is a cut of the raw source. This module aligns the edited audio
to the raw audio with a subsequence DTW, converts the monotonic mapping into
source-time intervals, and validates the result by reconstructing the edited
audio from the raw source.

The EDL is calibration data only. It is never read by the runtime recipe.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.application.audio_compare import (
    AudioFeatures,
    compare_audio,
    dtw_subsequence,
    extract_features,
    frame_rms,
    interval_union,
    load_pcm,
    reconstruct,
)
from videoflow.domain.state import Sentence


@dataclass(frozen=True, slots=True)
class ReferenceEdl:
    name: str
    raw: str
    edited: str
    kept_intervals: list[tuple[float, float]]
    validation: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        intervals = [
            [round(start, 6), round(end, 6)]
            for start, end in interval_union(self.kept_intervals)
        ]
        return {
            "name": self.name,
            "raw": self.raw,
            "edited": self.edited,
            "sample_rate": 16_000,
            "kept_intervals": intervals,
            "kept_intervals_48k": [
                [round(start * 48_000), round(end * 48_000)]
                for start, end in intervals
            ],
            "validation": self.validation,
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ReferenceEdl:
        intervals = [
            (float(item[0]), float(item[1]))
            for item in payload.get("kept_intervals", [])
            if len(item) >= 2
        ]
        return cls(
            name=str(payload.get("name", "")),
            raw=str(payload.get("raw", "")),
            edited=str(payload.get("edited", "")),
            kept_intervals=intervals,
            validation=dict(payload.get("validation", {})),
            diagnostics=dict(payload.get("diagnostics", {})),
        )


def save_reference_edl(path: Path, edl: ReferenceEdl) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(edl.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_reference_edl(path: Path) -> ReferenceEdl:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    return ReferenceEdl.from_dict(payload)


def _smooth(values: np.ndarray, size: int = 5) -> np.ndarray:
    if size <= 1 or values.size < size:
        return values.copy()
    half = size // 2
    padded = np.pad(values, (half, half), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, size)
    return np.median(windows, axis=1)


def _interpolate_indices(
    matches: list[tuple[int, int]],
    *,
    edited_count: int,
    raw_count: int,
) -> np.ndarray:
    """Expand sparse DTW matches into one raw index per edited window."""

    if not matches:
        return np.zeros(edited_count, dtype=np.int64)
    raw_index = np.full(edited_count, -1, dtype=np.int64)
    for edited_index, raw_position in matches:
        if 0 <= edited_index < edited_count:
            raw_index[edited_index] = raw_position
    known = np.flatnonzero(raw_index >= 0)
    if known.size == 0:
        return np.zeros(edited_count, dtype=np.int64)
    first = int(known[0])
    last = int(known[-1])
    for index in range(first):
        raw_index[index] = max(0, raw_index[first] - (first - index))
    for index in range(last + 1, edited_count):
        raw_index[index] = min(raw_count - 1, raw_index[last] + (index - last))
    for left, right in zip(known, known[1:], strict=False):
        left = int(left)
        right = int(right)
        if right - left <= 1:
            continue
        start_value = int(raw_index[left])
        end_value = int(raw_index[right])
        for index in range(left + 1, right):
            fraction = (index - left) / (right - left)
            raw_index[index] = round(start_value + (end_value - start_value) * fraction)
    raw_index = np.maximum.accumulate(np.clip(raw_index, 0, raw_count - 1))
    return raw_index


def _local_minimum(
    values: np.ndarray,
    center: int,
    radius: int,
) -> int:
    if values.size == 0:
        return center
    low = max(0, center - radius)
    high = min(values.size - 1, center + radius)
    if high <= low:
        return max(0, min(values.size - 1, center))
    return low + int(np.argmin(values[low : high + 1]))


def _refine_interval(
    interval: tuple[float, float],
    *,
    raw_rms: np.ndarray,
    raw_duration: float,
    frame_seconds: float = 0.01,
    start_radius: int = 20,
    end_radius: int = 25,
) -> tuple[float, float]:
    start, end = interval
    start = max(0.0, min(raw_duration, start))
    end = max(start, min(raw_duration, end))
    if end <= start:
        return start, end
    start_frame = round(start / frame_seconds)
    end_frame = round(end / frame_seconds)
    refined_start = _local_minimum(raw_rms, start_frame, start_radius) * frame_seconds
    refined_end = _local_minimum(raw_rms, end_frame, end_radius) * frame_seconds
    if refined_end <= refined_start:
        return start, end
    return refined_start, refined_end


def _build_intervals(
    offset: np.ndarray,
    *,
    edited: AudioFeatures,
    raw_duration: float,
    cut_threshold: float = 0.25,
    min_seconds: float = 0.75,
) -> list[tuple[float, float]]:
    hop = edited.window_hop_seconds
    window = edited.window_seconds
    deltas = np.diff(offset)
    cut_points = [index + 1 for index, value in enumerate(deltas) if abs(value) > cut_threshold]
    starts = [0, *cut_points]
    ends = [point - 1 for point in cut_points]
    ends.append(len(offset) - 1)
    intervals: list[tuple[float, float]] = []
    for start, end in zip(starts, ends, strict=False):
        if end < start:
            continue
        med = float(np.median(offset[start : end + 1]))
        edited_start = start * hop
        edited_end = end * hop + window
        raw_start = edited_start + med
        raw_end = edited_end + med
        if raw_end <= raw_start:
            continue
        intervals.append((max(0.0, raw_start), min(raw_duration, raw_end)))
    filtered = [
        (start, end)
        for start, end in interval_union(intervals)
        if end - start >= min_seconds
    ]
    return filtered


_TOKEN = re.compile(r"[^a-z0-9à-ÿ]+")


@dataclass(frozen=True, slots=True)
class FlatWord:
    start: float
    end: float
    text: str
    norm: str
    sentence_id: int = 0


def _normalise_word(text: str) -> str:
    return _TOKEN.sub("", text.casefold())


def flatten_sentences(
    sentences: Sequence[Sentence],
    *,
    sample_rate: int,
) -> list[FlatWord]:
    """Flatten sentence word timings to source-time seconds."""

    words: list[FlatWord] = []
    for sentence in sentences:
        for word in sentence.words:
            token = _normalise_word(word.word)
            if not token:
                continue
            words.append(
                FlatWord(
                    start=word.start_sample / sample_rate,
                    end=word.end_sample / sample_rate,
                    text=word.word,
                    norm=token,
                    sentence_id=sentence.id,
                )
            )
    words.sort(key=lambda item: (item.start, item.end))
    return words


def align_words(
    human: Sequence[FlatWord],
    source: Sequence[FlatWord],
) -> list[tuple[int, int, int]]:
    """Return monotonic matching blocks between the human and source words."""

    matcher = SequenceMatcher(
        None,
        [item.norm for item in human],
        [item.norm for item in source],
        autojunk=False,
    )
    return [
        (block.a, block.b, block.size)
        for block in matcher.get_matching_blocks()
        if block.size > 0
    ]


def _map_human_words(
    human: Sequence[FlatWord],
    source: Sequence[FlatWord],
    blocks: Sequence[tuple[int, int, int]],
) -> list[tuple[float, float]]:
    """Map every human word to ``(source_start, duration)``.

    Matched words use the source word start plus the human word duration, so
    inflated ASR word timings do not stretch the cut. Unmatched words are
    interpolated between their nearest matched neighbours; this keeps ASR-missed
    words inside the source audio instead of dropping them.
    """

    mapped: list[tuple[float, float] | None] = [None] * len(human)
    for a, b, size in blocks:
        if size <= 0 or a < 0 or b < 0:
            continue
        if a + size > len(human) or b + size > len(source):
            continue
        for offset in range(size):
            human_word = human[a + offset]
            source_word = source[b + offset]
            mapped[a + offset] = (
                source_word.start,
                max(0.0, human_word.end - human_word.start),
            )
    known = [index for index, value in enumerate(mapped) if value is not None]
    for index, value in enumerate(mapped):
        if value is not None:
            continue
        previous = max((item for item in known if item < index), default=None)
        following = min((item for item in known if item > index), default=None)
        duration = max(0.0, human[index].end - human[index].start)
        if previous is None and following is None:
            mapped[index] = (0.0, duration)
            continue
        if previous is None:
            assert following is not None
            next_start = mapped[following][0]  # type: ignore[index]
            mapped[index] = (
                max(0.0, next_start - (human[following].start - human[index].start)),
                duration,
            )
            continue
        previous_start, previous_duration = mapped[previous]  # type: ignore[misc]
        previous_end = previous_start + previous_duration
        if following is None:
            mapped[index] = (
                previous_end + max(0.0, human[index].start - human[previous].end),
                duration,
            )
            continue
        next_start = mapped[following][0]  # type: ignore[index]
        human_span = max(1e-6, human[following].start - human[previous].end)
        fraction = max(
            0.0,
            min(1.0, (human[index].start - human[previous].end) / human_span),
        )
        mapped[index] = (
            previous_end + fraction * max(0.0, next_start - previous_end),
            duration,
        )
    return [
        (max(0.0, start), max(0.0, duration))
        for start, duration in (value or (0.0, 0.0) for value in mapped)
    ]


def _best_offset(
    raw_pcm: np.ndarray,
    template: np.ndarray,
    *,
    search_start: float,
    search_end: float,
    sample_rate: int = 16_000,
    downsample: int = 4,
) -> tuple[float | None, float]:
    """Find the best normalized cross-correlation offset for a run.

    Correlating at 4 kHz keeps the FFT small while retaining sub-millisecond
    boundary resolution after converting back to 16 kHz.
    """

    factor = max(1, downsample)
    raw = np.asarray(raw_pcm, dtype=np.float32)[::factor]
    probe = np.asarray(template, dtype=np.float32)[::factor]
    if probe.size < max(1, (sample_rate // factor) // 4):
        return None, 0.0
    start = max(0, round(search_start * sample_rate / factor))
    end = min(raw.size, round(search_end * sample_rate / factor))
    window = raw[start:end]
    if window.size < probe.size:
        return None, 0.0
    size = 1 << (window.size + probe.size - 1).bit_length()
    spectrum = np.fft.rfft(window, size) * np.conj(np.fft.rfft(probe, size))
    correlation = np.fft.irfft(spectrum, size)[: window.size - probe.size + 1]
    squared = window.astype(np.float64) ** 2
    cumulative = np.concatenate(([0.0], np.cumsum(squared)))
    energy = cumulative[probe.size :] - cumulative[: -probe.size]
    denominator = np.sqrt(
        np.maximum(energy * float(np.dot(probe, probe)), 1e-12)
    )
    similarity = correlation / denominator
    index = int(np.argmax(similarity))
    score = float(np.clip(similarity[index], -1.0, 1.0))
    return (start + index) * factor / sample_rate, score


def _coverage_score(
    edited_pcm: np.ndarray,
    raw_pcm: np.ndarray,
    *,
    human_start: float,
    human_end: float,
    offset: float,
    sample_rate: int = 16_000,
    threshold: float = 0.5,
    window_seconds: float = 1.0,
) -> float:
    """Fraction of 1 s windows that correlate at a candidate source offset.

    PCM correlation is more discriminative than spectral descriptors for
    deciding whether a candidate offset covers the whole run or only a prefix.
    """

    template = edited_pcm[
        max(0, round(human_start * sample_rate)) : max(
            0, round(human_end * sample_rate)
        )
    ]
    source = raw_pcm[
        max(0, round(offset * sample_rate)) : max(0, round(offset * sample_rate))
        + template.size
    ]
    size = min(template.size, source.size)
    window = max(1, round(window_seconds * sample_rate))
    count = size // window
    if count == 0:
        return 0.0
    hits = 0
    valid = 0
    for index in range(count):
        left = template[index * window : (index + 1) * window]
        right = source[index * window : (index + 1) * window]
        if left.std() < 1e-6 or right.std() < 1e-6:
            continue
        valid += 1
        correlation = float(np.corrcoef(left, right)[0, 1])
        if correlation >= threshold:
            hits += 1
    if valid == 0:
        return 0.0
    return hits / valid


def _build_intervals_from_blocks(
    human: Sequence[FlatWord],
    source: Sequence[FlatWord],
    blocks: Sequence[tuple[int, int, int]],
    *,
    raw_duration: float,
    edited_duration: float | None = None,
    edge_seconds: float = 0.5,
    max_gap_seconds: float = 0.8,
    raw_pcm: np.ndarray | None = None,
    edited_pcm: np.ndarray | None = None,
    min_score: float = 0.2,
    min_coverage: float = 0.5,
) -> list[tuple[float, float]]:
    """Convert mapped human words into source-time intervals.

    Runs are built over every human word, including ASR-missed words. When PCM
    is available, each run is re-anchored by normalized cross-correlation around
    its provisional source position. This disambiguates repeated takes and
    corrects ASR timing drift. Short pauses between runs are added back up to
    the human pause, the available source pause, and the configured edge limit.
    """

    if not human:
        return []
    mapped = _map_human_words(human, source, blocks)
    runs: list[list[int]] = []
    current: list[int] = [0]
    for index in range(1, len(human)):
        human_gap = human[index].start - human[index - 1].end
        same_sentence = human[index].sentence_id == human[index - 1].sentence_id
        if same_sentence and human_gap <= max_gap_seconds:
            current.append(index)
        else:
            runs.append(current)
            current = [index]
    runs.append(current)

    def align(
        run: list[int],
        floor: float,
    ) -> tuple[list[tuple[float, float, float, float]], float]:
        first = run[0]
        last = run[-1]
        human_start = human[first].start
        human_end = human[last].end
        human_duration = max(0.0, human_end - human_start)
        provisional = mapped[first][0]
        accepted: float | None = None
        if raw_pcm is not None and edited_pcm is not None and human_duration > 0.05:
            template = edited_pcm[
                max(0, round(human_start * 16_000)) : max(
                    0, round(human_end * 16_000)
                )
            ]
            if template.size:
                # Coarse search over the remaining raw finds the final take even
                # when it is far from the word-alignment provisional position.
                coarse, coarse_score = _best_offset(
                    raw_pcm,
                    template,
                    search_start=max(0.0, floor - 2.0),
                    search_end=raw_duration,
                    downsample=16,
                )
                offset: float | None = None
                score = 0.0
                if coarse is not None and coarse_score >= 0.15:
                    offset, score = _best_offset(
                        raw_pcm,
                        template,
                        search_start=max(0.0, coarse - 0.5),
                        search_end=min(raw_duration, coarse + 0.5),
                        downsample=1,
                    )
                    if offset is None:
                        offset, score = coarse, coarse_score
                if offset is not None and score >= min_score:
                    coverage = _coverage_score(
                        edited_pcm,
                        raw_pcm,
                        human_start=human_start,
                        human_end=human_end,
                        offset=offset,
                    )
                    if coverage >= min_coverage:
                        accepted = offset
        if accepted is not None:
            end = min(raw_duration, accepted + human_duration)
            return (
                [
                    (
                        max(0.0, min(raw_duration, accepted)),
                        end,
                        human_start,
                        human_end,
                    )
                ],
                end,
            )
        end = min(raw_duration, provisional + human_duration)
        return (
            [
                (
                    max(0.0, min(raw_duration, provisional)),
                    end,
                    human_start,
                    human_end,
                )
            ],
            end,
        )

    runs_data: list[tuple[float, float, float, float]] = []
    floor = 0.0
    for run in runs:
        data, floor = align(run, floor)
        runs_data.extend(data)

    intervals: list[tuple[float, float]] = []
    for index, (source_start, source_end, human_start, human_end) in enumerate(runs_data):
        if index == 0:
            source_start = max(0.0, source_start - min(edge_seconds, human_start))
        if index + 1 < len(runs_data):
            next_start, _next_end, next_human_start, _next_human_end = runs_data[index + 1]
            human_gap = max(0.0, next_human_start - human_end)
            source_gap = max(0.0, next_start - source_end)
            source_end += min(edge_seconds, human_gap, source_gap)
        elif edited_duration is not None:
            source_end += min(edge_seconds, max(0.0, edited_duration - human_end))
        intervals.append((max(0.0, source_start), min(raw_duration, source_end)))
    return interval_union(intervals)


def _ncc_array(
    raw_pcm: np.ndarray,
    template: np.ndarray,
    *,
    downsample: int = 8,
) -> tuple[np.ndarray, int] | None:
    """Return the full normalized cross-correlation array and its factor."""

    factor = max(1, downsample)
    raw = np.asarray(raw_pcm, dtype=np.float32)[::factor]
    probe = np.asarray(template, dtype=np.float32)[::factor]
    if probe.size < 8 or raw.size < probe.size:
        return None
    size = 1 << (raw.size + probe.size - 1).bit_length()
    spectrum = np.fft.rfft(raw, size) * np.conj(np.fft.rfft(probe, size))
    correlation = np.fft.irfft(spectrum, size)[: raw.size - probe.size + 1]
    squared = raw.astype(np.float64) ** 2
    cumulative = np.concatenate(([0.0], np.cumsum(squared)))
    energy = cumulative[probe.size :] - cumulative[: -probe.size]
    denominator = np.sqrt(
        np.maximum(energy * float(np.dot(probe, probe)), 1e-12)
    )
    return correlation / denominator, factor


def _top_candidates(
    ncc: np.ndarray,
    *,
    factor: int,
    sample_rate: int = 16_000,
    top_k: int = 8,
    min_score: float = 0.25,
    min_separation_seconds: float = 1.0,
) -> list[tuple[float, float]]:
    """Extract separated NCC peaks and convert them to source seconds."""

    if ncc.size == 0:
        return []
    limit = min(ncc.size, max(top_k * 8, top_k))
    indices = np.argpartition(ncc, -limit)[-limit:]
    order = indices[np.argsort(ncc[indices])[::-1]]
    separation = max(1, round(min_separation_seconds * sample_rate / factor))
    chosen: list[tuple[float, float]] = []
    for index in order:
        index = int(index)
        score = float(ncc[index])
        if score < min_score:
            break
        if any(abs(index - round(item[0] * sample_rate / factor)) < separation for item in chosen):
            continue
        chosen.append((index * factor / sample_rate, score))
        if len(chosen) >= top_k:
            break
    return chosen


def _choose_candidate_path(
    candidates: Sequence[Sequence[tuple[float, float]]],
    *,
    jump_penalty_per_second: float = 0.002,
) -> list[tuple[float, float]]:
    """Pick one monotonic candidate per sentence with a forward-jump penalty."""

    if not candidates:
        return []
    negative = float("-inf")
    scores: list[list[float]] = [[negative] * len(items) for items in candidates]
    previous: list[list[int]] = [[-1] * len(items) for items in candidates]
    for index, (_offset, score) in enumerate(candidates[0]):
        scores[0][index] = score
    for row in range(1, len(candidates)):
        for index, (offset, score) in enumerate(candidates[row]):
            best = negative
            best_previous = -1
            for back, (previous_offset, _previous_score) in enumerate(candidates[row - 1]):
                if scores[row - 1][back] == negative:
                    continue
                jump = offset - previous_offset
                penalty = (
                    jump_penalty_per_second * jump
                    if jump >= 0
                    else 1.0 + jump_penalty_per_second * abs(jump)
                )
                value = scores[row - 1][back] + score - penalty
                if value > best:
                    best = value
                    best_previous = back
            scores[row][index] = best
            previous[row][index] = best_previous
    end = max(range(len(candidates[-1])), key=lambda item: scores[-1][item])
    path = [end]
    for row in range(len(candidates) - 1, 0, -1):
        path.append(previous[row][path[-1]])
    path.reverse()
    return [candidates[row][index] for row, index in enumerate(path)]


def _sentence_runs(human: Sequence[FlatWord]) -> list[list[int]]:
    runs: list[list[int]] = []
    current: list[int] = [0]
    for index in range(1, len(human)):
        if human[index].sentence_id == human[index - 1].sentence_id:
            current.append(index)
        else:
            runs.append(current)
            current = [index]
    runs.append(current)
    return runs


def build_reference_edl_from_sentences(
    raw_pcm: np.ndarray,
    edited_pcm: np.ndarray,
    *,
    name: str,
    raw_path: Path,
    edited_path: Path,
    sentences: Sequence[Sentence],
    tau: float = 0.9,
    min_score: float = 0.2,
) -> ReferenceEdl:
    """Align each human sentence to the raw audio with candidate DP.

    Each sentence contributes several audio candidates. A monotonic dynamic
    programme chooses one candidate per sentence, rewarding high correlation
    and penalising backward or very large forward jumps. This picks the take
    sequence actually used by the human edit instead of a single global maximum.
    """

    human = flatten_sentences(sentences, sample_rate=16_000)
    raw_duration = raw_pcm.size / 16_000
    edited_duration = edited_pcm.size / 16_000
    run_info: list[tuple[list[int], float, float, float]] = []
    candidate_sets: list[list[tuple[float, float]]] = []
    for run in _sentence_runs(human):
        human_start = human[run[0]].start
        human_end = human[run[-1]].end
        duration = max(0.0, human_end - human_start)
        if duration <= 0.05:
            continue
        template = edited_pcm[
            round(human_start * 16_000) : round(human_end * 16_000)
        ]
        data = _ncc_array(raw_pcm, template, downsample=8)
        if data is None:
            candidates: list[tuple[float, float]] = []
        else:
            candidates = _top_candidates(
                data[0],
                factor=data[1],
                top_k=8,
                min_score=min_score,
                min_separation_seconds=1.0,
            )
        if not candidates:
            candidates = [(0.0, 0.0)]
        candidate_sets.append(candidates)
        run_info.append((run, human_start, human_end, duration))

    chosen = _choose_candidate_path(candidate_sets)
    runs_data: list[tuple[float, float, float, float]] = []
    for (_run, human_start, human_end, duration), (offset, _score) in zip(
        run_info, chosen, strict=False
    ):
        trim = min(0.3, duration * 0.2) if duration > 0.8 else 0.0
        template_start = human_start + trim
        template_end = human_end - trim
        template = edited_pcm[
            round(template_start * 16_000) : round(template_end * 16_000)
        ]
        refined, _refined_score = _best_offset(
            raw_pcm,
            template,
            search_start=max(0.0, offset + trim - 0.5),
            search_end=min(raw_duration, offset + trim + 0.5),
            downsample=1,
        )
        start = refined - trim if refined is not None else offset
        start = max(0.0, min(raw_duration, start))
        end = min(raw_duration, start + duration)
        runs_data.append((start, end, human_start, human_end))

    paced: list[tuple[float, float, float, float]] = []
    for index, (start, end, human_start, human_end) in enumerate(runs_data):
        if index + 1 < len(runs_data):
            next_start, _next_end, next_human_start, _next_human_end = runs_data[index + 1]
            human_gap = max(0.0, next_human_start - human_end)
            source_gap = max(0.0, next_start - end)
            end += min(0.5, human_gap, source_gap)
        paced.append((start, end, human_start, human_end))
    intervals = interval_union([(start, end) for start, end, _h0, _h1 in paced])

    reconstructed = reconstruct(raw_pcm, intervals)
    comparison = compare_audio(edited_pcm, reconstructed, tau=tau)
    covered = sum(end - start for start, end in intervals)
    diagnostics = {
        "mode": "sentences",
        "sentences": len(run_info),
        "candidates": sum(len(items) for items in candidate_sets),
        "selected": len(chosen),
        "intervals": len(intervals),
        "coverage": round(covered / max(1e-9, edited_duration), 6),
        "covered_seconds": round(covered, 6),
        "edited_seconds": round(edited_duration, 6),
        "cuts": max(0, len(intervals) - 1),
    }
    return ReferenceEdl(
        name=name,
        raw=str(raw_path),
        edited=str(edited_path),
        kept_intervals=intervals,
        validation=comparison.to_dict(),
        diagnostics=diagnostics,
    )


def build_reference_edl_from_words(
    raw_pcm: np.ndarray,
    edited_pcm: np.ndarray,
    *,
    name: str,
    raw_path: Path,
    edited_path: Path,
    human_words: Sequence[FlatWord],
    source_words: Sequence[FlatWord],
    tau: float = 0.9,
) -> ReferenceEdl:
    """Build an EDL from word alignment, then refine and validate on audio."""

    raw_duration = raw_pcm.size / 16_000
    edited_duration = edited_pcm.size / 16_000
    blocks = align_words(human_words, source_words)
    intervals = _build_intervals_from_blocks(
        human_words,
        source_words,
        blocks,
        raw_duration=raw_duration,
        edited_duration=edited_duration,
        raw_pcm=raw_pcm,
        edited_pcm=edited_pcm,
    )
    refined = [
        (start, end)
        for start, end in interval_union(intervals)
        if end - start >= 0.1
    ]
    reconstructed = reconstruct(raw_pcm, refined)
    comparison = compare_audio(edited_pcm, reconstructed, tau=tau)
    covered = sum(end - start for start, end in refined)
    diagnostics = {
        "mode": "words",
        "blocks": len(blocks),
        "matched_words": sum(size for _a, _b, size in blocks),
        "human_words": len(human_words),
        "source_words": len(source_words),
        "coverage": round(covered / max(1e-9, edited_duration), 6),
        "covered_seconds": round(covered, 6),
        "edited_seconds": round(edited_duration, 6),
        "cuts": max(0, len(refined) - 1),
    }
    return ReferenceEdl(
        name=name,
        raw=str(raw_path),
        edited=str(edited_path),
        kept_intervals=refined,
        validation=comparison.to_dict(),
        diagnostics=diagnostics,
    )


def build_reference_edl(
    raw_pcm: np.ndarray,
    edited_pcm: np.ndarray,
    *,
    name: str,
    raw_path: Path,
    edited_path: Path,
    tau: float = 0.9,
    cut_threshold: float = 0.25,
) -> ReferenceEdl:
    """Align the edited audio to the raw source and return the kept intervals."""

    raw = extract_features(raw_pcm)
    edited = extract_features(edited_pcm)
    matches, total_cost = dtw_subsequence(
        edited.descriptors,
        raw.descriptors,
        source_speech=edited.speech,
        target_speech=raw.speech,
        speech_penalty=0.25,
        gap_source=2.0,
    )
    raw_index = _interpolate_indices(
        matches,
        edited_count=edited.descriptors.shape[0],
        raw_count=raw.descriptors.shape[0],
    )
    hop = edited.window_hop_seconds
    edited_positions = np.arange(raw_index.size, dtype=np.float64) * hop
    raw_positions = raw_index.astype(np.float64) * hop
    offset = _smooth(raw_positions - edited_positions, size=5)
    intervals = _build_intervals(
        offset,
        edited=edited,
        raw_duration=raw.duration,
        cut_threshold=cut_threshold,
    )
    raw_rms = frame_rms(raw_pcm, frame_length=160, hop=160)
    refined = [
        _refine_interval(item, raw_rms=raw_rms, raw_duration=raw.duration)
        for item in intervals
    ]
    refined = [
        (start, end)
        for start, end in interval_union(refined)
        if end - start >= 0.75
    ]
    reconstructed = reconstruct(raw_pcm, refined)
    comparison = compare_audio(edited_pcm, reconstructed, tau=tau)
    covered = sum(end - start for start, end in refined)
    diagnostics = {
        "edited_windows": int(edited.descriptors.shape[0]),
        "raw_windows": int(raw.descriptors.shape[0]),
        "matches": len(matches),
        "dtw_cost": round(total_cost, 6),
        "cut_points": max(0, len(refined) - 1),
        "median_offset_seconds": round(float(np.median(offset)), 6),
        "covered_seconds": round(covered, 6),
        "edited_seconds": round(edited.duration, 6),
        "coverage": round(covered / max(1e-9, edited.duration), 6),
    }
    return ReferenceEdl(
        name=name,
        raw=str(raw_path),
        edited=str(edited_path),
        kept_intervals=refined,
        validation=comparison.to_dict(),
        diagnostics=diagnostics,
    )


def build_reference_edl_from_paths(
    raw_path: Path,
    edited_path: Path,
    *,
    name: str = "",
    tau: float = 0.9,
    cut_threshold: float = 0.25,
) -> ReferenceEdl:
    raw = load_pcm(raw_path)
    edited = load_pcm(edited_path)
    return build_reference_edl(
        raw,
        edited,
        name=name or raw_path.stem,
        raw_path=raw_path,
        edited_path=edited_path,
        tau=tau,
        cut_threshold=cut_threshold,
    )
