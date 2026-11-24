"""Word-timing repair before retakes and timeline decisions.

Whisper word timestamps are sometimes wildly wrong: a single token can span
several seconds of silence. Those timings cause clipped word tails and bad cut
decisions downstream. This module clamps each word to the VAD speech region that
contains it and snaps the edges to nearby low-energy valleys, without ever
crossing a neighbouring word.
"""

from __future__ import annotations

import contextlib
import re
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from videoflow.domain.state import Sentence, WordTiming
from videoflow.domains.audio.pcm_io import decode_pcm_mono_rms

_LETTER = re.compile(r"[^a-z0-9à-ÿ]")
_FRAME_MS = 10


def _letters(text: str) -> int:
    return len(_LETTER.sub("", text.casefold()))


def plausible_ms(word: str) -> int:
    """Upper bound for a believable word duration, based on its length."""

    return min(1500, 150 + 60 * max(1, _letters(word)))


class _Rms:
    def __init__(self, path: Path | None, sample_rate: int) -> None:
        self.handle: wave.Wave_read | None = None
        self.channels = 1
        self.width = 2
        self.rate = sample_rate
        if path is None or not Path(path).is_file():
            return
        try:
            self.handle = wave.open(str(path), "rb")  # noqa: SIM115 - closed in close()
        except (OSError, EOFError, wave.Error):
            self.handle = None
            return
        self.channels = max(1, self.handle.getnchannels())
        self.width = self.handle.getsampwidth()
        self.rate = self.handle.getframerate() or sample_rate

    def close(self) -> None:
        if self.handle is not None:
            with contextlib.suppress(OSError, EOFError, wave.Error):
                self.handle.close()
            self.handle = None

    def __call__(self, start: int, end: int) -> int:
        if self.handle is None:
            return 0
        if self.width not in {2, 3, 4}:
            raise ValueError(f"Unsupported PCM sample width: {self.width}")
        start = max(0, start)
        end = max(start + 1, end)
        try:
            self.handle.setpos(start)
            data = self.handle.readframes(end - start)
        except (OSError, EOFError, wave.Error):
            return 0
        return decode_pcm_mono_rms(data, sampwidth=self.width, channels=self.channels)


def _snap(
    rms: _Rms | None,
    position: int,
    *,
    direction: int,
    limit: int,
    frame: int,
    sample_rate: int,
    threshold: int = 400,
) -> int:
    """Move an edge to the quietest nearby frame, within ``limit`` samples."""

    if rms is None or limit <= 0:
        return position
    best = position
    best_energy = rms(max(0, position - frame), position + frame)
    steps = max(1, limit // frame)
    for step in range(1, steps + 1):
        candidate = position + direction * step * frame
        if candidate < 0:
            break
        energy = rms(max(0, candidate - frame // 2), candidate + frame // 2)
        if energy < best_energy:
            best = candidate
            best_energy = energy
        if energy <= threshold:
            break
    return best


def _vad_span(
    start: int,
    end: int,
    speech: Sequence[tuple[int, int]],
) -> tuple[int, int] | None:
    midpoint = (start + end) // 2
    for span_start, span_end in speech:
        if span_start <= midpoint <= span_end:
            return span_start, span_end
    return None


def refine_transcript(
    sentences: Sequence[Sentence],
    speech_intervals: Sequence[tuple[int, int]],
    *,
    pcm_path: Path | None = None,
    sample_rate: int = 48_000,
    snap_ms: int = 60,
    min_word_ms: int = 40,
) -> tuple[list[Sentence], dict[str, Any]]:
    """Return sentences with VAD-clamped, valley-snapped word timings."""

    if not sentences:
        return [], {"words": 0, "adjusted": 0}
    speech = sorted(
        (int(start), int(end)) for start, end in speech_intervals if end > start
    )
    frame = max(1, round(sample_rate * _FRAME_MS / 1000))
    snap = max(0, round(snap_ms * sample_rate / 1000))
    minimum = max(1, round(min_word_ms * sample_rate / 1000))
    rms = _Rms(pcm_path, sample_rate)
    adjusted = 0
    clamped = 0
    snapped = 0
    implausible_before = 0
    implausible_after = 0
    max_before = 0
    max_after = 0
    output: list[Sentence] = []
    try:
        previous_end = 0
        for sentence in sentences:
            floor = previous_end
            words = sorted(sentence.words, key=lambda item: item.start_sample)
            refined: list[WordTiming] = []
            for index, word in enumerate(words):
                start = word.start_sample
                end = word.end_sample
                duration = end - start
                max_before = max(max_before, duration)
                limit = round(
                    min(1500, max(600, plausible_ms(word.word) * 2))
                    * sample_rate
                    / 1000
                )
                if duration > limit:
                    implausible_before += 1
                span = _vad_span(start, end, speech) if speech else None
                changed = False
                margin = round(100 * sample_rate / 1000)
                if span is not None and (
                    start < span[0] - margin or end > span[1] + margin
                ):
                    new_start = max(start, span[0])
                    new_end = min(end, span[1])
                    if new_end - new_start >= minimum and (
                        new_start != start or new_end != end
                    ):
                        start, end = new_start, new_end
                        clamped += 1
                        changed = True
                if end - start > limit:
                    # A token stamped across seconds of audio is not usable.
                    # Keep the word text, centre its span on the midpoint, and
                    # cap it to a believable duration before snapping.
                    midpoint = (start + end) // 2
                    start = max(0, midpoint - limit // 2)
                    end = start + limit
                    if span is not None:
                        start = max(start, span[0])
                        end = min(end, span[1])
                    if end - start < minimum:
                        end = start + minimum
                    clamped += 1
                    changed = True
                next_start = (
                    words[index + 1].start_sample
                    if index + 1 < len(words)
                    else sentence.end_sample
                )
                start = max(start, previous_end)
                end = min(end, next_start) if next_start > start else end
                if changed:
                    start = _snap(
                        rms,
                        start,
                        direction=-1,
                        limit=snap,
                        frame=frame,
                        sample_rate=sample_rate,
                    )
                    end = _snap(
                        rms,
                        end,
                        direction=1,
                        limit=snap,
                        frame=frame,
                        sample_rate=sample_rate,
                    )
                if start != word.start_sample or end != word.end_sample:
                    snapped += 1
                if end - start < minimum:
                    end = start + minimum
                if end - start > limit:
                    implausible_after += 1
                max_after = max(max_after, end - start)
                refined.append(
                    WordTiming(
                        word=word.word,
                        start_sample=start,
                        end_sample=end,
                        probability=word.probability,
                    )
                )
                previous_end = end
            for index in range(1, len(refined)):
                if refined[index].start_sample < refined[index - 1].end_sample:
                    refined[index] = refined[index].model_copy(
                        update={"start_sample": refined[index - 1].end_sample}
                    )
                if refined[index].end_sample <= refined[index].start_sample:
                    refined[index] = refined[index].model_copy(
                        update={
                            "end_sample": refined[index].start_sample + minimum
                        }
                    )
            if not refined:
                output.append(sentence)
                continue
            first = refined[0].start_sample
            last = refined[-1].end_sample
            if first < floor:
                shift = floor - first
                refined = [
                    word.model_copy(
                        update={
                            "start_sample": word.start_sample + shift,
                            "end_sample": word.end_sample + shift,
                        }
                    )
                    for word in refined
                ]
                first += shift
                last += shift
            if first != sentence.start_sample or last != sentence.end_sample:
                adjusted += 1
            output.append(
                Sentence(
                    id=sentence.id,
                    start_sample=first,
                    end_sample=max(first, last),
                    text=sentence.text,
                    speaker=sentence.speaker,
                    words=refined,
                )
            )
            previous_end = max(previous_end, last)
            if output and output[-1].id != sentence.id:
                previous_end = max(previous_end, output[-1].end_sample)
    finally:
        rms.close()
    return output, {
        "words": sum(len(sentence.words) for sentence in sentences),
        "adjusted": adjusted,
        "vad_clamped": clamped,
        "snapped": snapped,
        "implausible_before": implausible_before,
        "implausible_after": implausible_after,
        "max_word_ms_before": round(max_before / sample_rate * 1000, 1),
        "max_word_ms_after": round(max_after / sample_rate * 1000, 1),
    }
