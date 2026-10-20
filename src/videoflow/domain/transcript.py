"""Subtitle import.

SRT is enough to drive retake culling without a speech model. Times become source
sample indices at the media sample rate; there are no word timings.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from videoflow.domain.errors import TranscriptError
from videoflow.domain.state import Sentence

_TIME = re.compile(
    r"(?P<h1>\d+):(?P<m1>\d{2}):(?P<s1>\d{2})[,.](?P<ms1>\d{3})"
    r"\s*-->\s*"
    r"(?P<h2>\d+):(?P<m2>\d{2}):(?P<s2>\d{2})[,.](?P<ms2>\d{3})"
)


def parse_srt(text: str, sample_rate: int) -> list[Sentence]:
    """Parse SRT into sequential sentences in source samples."""

    if sample_rate <= 0:
        raise TranscriptError("sample rate must be positive")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise TranscriptError("subtitle file is empty")
    sentences: list[Sentence] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        match: re.Match[str] | None = None
        time_index = 0
        for index, line in enumerate(lines):
            match = _TIME.search(line)
            if match:
                time_index = index
                break
        if match is None:
            raise TranscriptError(f"missing timecode in block: {lines[0]}")
        body = " ".join(lines[time_index + 1 :]).strip()
        if not body:
            raise TranscriptError(f"empty subtitle text in block: {lines[0]}")
        start = _to_samples(match, "1", sample_rate)
        end = _to_samples(match, "2", sample_rate)
        if end <= start:
            raise TranscriptError(f"subtitle ends before it starts: {lines[0]}")
        sentences.append(
            Sentence(
                id=len(sentences),
                start_sample=start,
                end_sample=end,
                text=body,
            )
        )
    if not sentences:
        raise TranscriptError("subtitle file has no valid cues")
    return sentences


def parse_srt_file(path: Path, sample_rate: int) -> list[Sentence]:
    source = Path(path).expanduser()
    try:
        text = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise TranscriptError(f"cannot read subtitle file: {source}") from exc
    return parse_srt(text, sample_rate)


def format_srt(sentences: Sequence[Sentence], sample_rate: int) -> str:
    """Render sentences as SRT without losing their source sample times."""

    if sample_rate <= 0:
        raise TranscriptError("sample rate must be positive")
    blocks: list[str] = []
    for index, sentence in enumerate(sentences, start=1):
        blocks.append(
            f"{index}\n"
            f"{format_srt_time(sentence.start_sample, sample_rate)} --> "
            f"{format_srt_time(sentence.end_sample, sample_rate)}\n"
            f"{sentence.text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def format_srt_time(samples: int, sample_rate: int) -> str:
    """Format a sample index as a millisecond SRT timestamp."""

    if sample_rate <= 0:
        raise TranscriptError("sample rate must be positive")
    total_ms = (max(0, samples) * 1000 + sample_rate // 2) // sample_rate
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _to_samples(match: re.Match[str], side: str, sample_rate: int) -> int:
    hours = int(match.group(f"h{side}"))
    minutes = int(match.group(f"m{side}"))
    seconds = int(match.group(f"s{side}"))
    milliseconds = int(match.group(f"ms{side}"))
    total_ms = ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds
    return (total_ms * sample_rate + 500) // 1000
