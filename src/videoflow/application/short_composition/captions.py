# ruff: noqa: E501
"""Short caption blocks, ASS rendering, and overlap sanitising."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from videoflow.application.captions import CaptionLine
from videoflow.application.short_composition.geometry import CANVAS_HEIGHT, CANVAS_WIDTH
from videoflow.domain.short_composition import ShortCompositionPlan
from videoflow.domain.state import Sentence

DEFAULT_MAX_WORDS = 4
DEFAULT_MIN_WORDS = 3
DEFAULT_MAX_CHARS = 18
DEFAULT_MAX_LINES = 2
DEFAULT_MAX_GAP = 0.6
DEFAULT_FONT_SIZE = 64
DEFAULT_OUTLINE = 5
DEFAULT_SHADOW = 2
MIN_CAPTION_SEC = 0.06
OVERLAP_GAP_SEC = 0.01

SENTENCE_END = (".", "!", "?", "…", "。", "！", "？")


@dataclass(frozen=True, slots=True)
class CaptionWord:
    start: float
    end: float
    text: str
    speaker: int = 0


@dataclass(frozen=True, slots=True)
class CaptionBlock:
    start: float
    end: float
    lines: tuple[str, ...]
    speaker: int = 0
    layout: str = "FULL_FACE"
    subtitle_y: int = 1360

    @property
    def text(self) -> str:
        return " ".join(self.lines)


def words_from_sentences(
    sentences: Sequence[Sentence],
    *,
    sample_rate: int,
    start_sec: float,
    end_sec: float,
) -> list[CaptionWord]:
    rate = max(1, int(sample_rate))
    words: list[CaptionWord] = []
    for sentence in sentences:
        for word in sentence.words:
            start = word.start_sample / rate
            end = word.end_sample / rate
            if end <= start_sec or start >= end_sec:
                continue
            text = word.word.strip()
            if not text:
                continue
            words.append(
                CaptionWord(
                    start=max(0.0, start - start_sec),
                    end=min(end_sec, end) - start_sec,
                    text=text,
                    speaker=sentence.speaker,
                )
            )
        if sentence.words:
            continue
        start = sentence.start_sample / rate
        end = sentence.end_sample / rate
        if end <= start_sec or start >= end_sec:
            continue
        tokens = sentence.text.split()
        if not tokens:
            continue
        span = max(0.001, end - start)
        weight = span / len(tokens)
        for index, token in enumerate(tokens):
            word_start = max(start, start_sec) + index * weight
            words.append(
                CaptionWord(
                    start=max(0.0, word_start - start_sec),
                    end=min(end_sec, word_start + weight) - start_sec,
                    text=token,
                    speaker=sentence.speaker,
                )
            )
    return sorted(
        (word for word in words if word.end > word.start),
        key=lambda item: item.start,
    )


def proportional_words(
    text: str,
    *,
    start: float,
    end: float,
    speaker: int = 0,
) -> list[CaptionWord]:
    tokens = [token for token in text.split() if token]
    if not tokens:
        return []
    span = max(0.001, end - start)
    weight = span / len(tokens)
    return [
        CaptionWord(
            start=start + index * weight,
            end=start + (index + 1) * weight,
            text=token,
            speaker=speaker,
        )
        for index, token in enumerate(tokens)
    ]


def wrap_words(
    tokens: Sequence[str],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
) -> list[str] | None:
    limit = max(1, int(max_chars))
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = token if not current else f"{current} {token}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = token
        if len(current) > limit:
            # Never truncate a word; give it its own overlong line.
            lines.append(current)
            current = ""
        if len(lines) > max_lines:
            return None
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        return None
    return lines


def _sentence_end(text: str) -> bool:
    return text.rstrip().endswith(SENTENCE_END)


def group_words(
    words: Sequence[CaptionWord],
    *,
    layout_boundaries: Sequence[float] = (),
    max_words: int = DEFAULT_MAX_WORDS,
    min_words: int = DEFAULT_MIN_WORDS,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
    max_gap: float = DEFAULT_MAX_GAP,
) -> tuple[list[CaptionBlock], list[str]]:
    warnings: list[str] = []
    limit = max(1, int(max_words))
    boundaries = sorted(float(value) for value in layout_boundaries)
    ordered = sorted(
        (word for word in words if word.text.strip() and word.end > word.start),
        key=lambda item: item.start,
    )
    chunks: list[list[CaptionWord]] = []
    current: list[CaptionWord] = []
    for word in ordered:
        if current:
            crosses = any(current[-1].start < value <= word.start for value in boundaries)
            gap = word.start - current[-1].end
            if crosses or gap > max_gap or _sentence_end(current[-1].text):
                chunks.append(current)
                current = []
        candidate = [*current, word]
        tokens = [item.text for item in candidate]
        if len(candidate) > limit or wrap_words(
            tokens, max_chars=max_chars, max_lines=max_lines
        ) is None:
            if current:
                chunks.append(current)
            current = [word]
            if wrap_words([word.text], max_chars=max_chars, max_lines=max_lines) is None:
                warnings.append(f"CAPTION_OVERLONG_WORD: {word.text}")
        else:
            current = candidate
    if current:
        chunks.append(current)

    merged: list[list[CaptionWord]] = []
    for chunk in chunks:
        if merged:
            previous = merged[-1]
            combined = previous + chunk
            crosses = any(
                previous[-1].start < value <= chunk[0].start for value in boundaries
            )
            sentence_break = _sentence_end(previous[-1].text)
            if (
                len(chunk) < max(1, int(min_words))
                and len(combined) <= limit
                and not crosses
                and not sentence_break
                and wrap_words(
                    [item.text for item in combined],
                    max_chars=max_chars,
                    max_lines=max_lines,
                )
                is not None
            ):
                merged[-1] = combined
                continue
        merged.append(chunk)

    # Rebalance short trailing chunks by shifting words from the left while
    # preserving sentence and layout boundaries.
    minimum = max(1, int(min_words))
    for position in range(len(merged) - 1, -1, -1):
        while len(merged[position]) < minimum:
            donor = position - 1
            moved = False
            while donor >= 0:
                if len(merged[donor]) <= minimum:
                    donor -= 1
                    continue
                crosses = any(
                    merged[donor][-1].start < value <= merged[donor + 1][0].start
                    for value in boundaries
                )
                if crosses or _sentence_end(merged[donor][-1].text):
                    break
                word = merged[donor].pop()
                merged[donor + 1].insert(0, word)
                moved = True
                break
            if not moved:
                break

    blocks = [
        CaptionBlock(
            start=round(chunk[0].start, 6),
            end=round(max(chunk[-1].end, chunk[0].start + MIN_CAPTION_SEC), 6),
            lines=tuple(
                wrap_words(
                    [item.text for item in chunk],
                    max_chars=max_chars,
                    max_lines=max_lines,
                )
                or [" ".join(item.text for item in chunk)]
            ),
            speaker=chunk[0].speaker,
        )
        for chunk in merged
    ]
    return blocks, warnings


def assign_layouts(
    blocks: Sequence[CaptionBlock],
    plan: ShortCompositionPlan,
    *,
    subtitle_y: dict[str, int],
) -> tuple[list[CaptionBlock], list[str]]:
    warnings: list[str] = []
    result: list[CaptionBlock] = []
    for block in blocks:
        segment = next(
            (
                item
                for item in plan.segments
                if item.rel_start - 1e-6 <= block.start < item.rel_end - 1e-6
            ),
            plan.segments[-1],
        )
        end = block.end
        if end > segment.rel_end + 1e-6:
            end = segment.rel_end
            warnings.append(f"CAPTION_TRIMMED_AT_LAYOUT: {block.text}")
        if end - block.start < MIN_CAPTION_SEC:
            warnings.append(f"CAPTION_DROPPED_AT_LAYOUT: {block.text}")
            continue
        result.append(
            replace(
                block,
                end=round(end, 6),
                layout=segment.layout,
                subtitle_y=subtitle_y[segment.layout],
            )
        )
    return result, warnings


def sanitize_blocks(
    blocks: Sequence[CaptionBlock],
    *,
    min_duration: float = MIN_CAPTION_SEC,
    gap: float = OVERLAP_GAP_SEC,
) -> tuple[list[CaptionBlock], list[str]]:
    warnings: list[str] = []
    ordered = sorted(
        (block for block in blocks if block.end > block.start),
        key=lambda item: (item.start, item.end),
    )
    result: list[CaptionBlock] = []
    for block in ordered:
        if not result:
            result.append(block)
            continue
        previous = result[-1]
        if block.start >= previous.end:
            result.append(block)
            continue
        end = round(block.start - gap, 6)
        if end - previous.start >= min_duration:
            result[-1] = replace(previous, end=end)
            warnings.append(f"CAPTION_OVERLAP_TRIMMED: {previous.text}")
            result.append(block)
        else:
            result[-1] = block
            warnings.append(f"CAPTION_SUPERSEDED: {previous.text}")
    return [
        block for block in result if block.end - block.start >= min_duration
    ], warnings


def caption_lines(blocks: Sequence[CaptionBlock]) -> list[CaptionLine]:
    return [
        CaptionLine(
            start=block.start,
            end=block.end,
            text=block.text,
            speaker=block.speaker,
        )
        for block in blocks
    ]


def _ass_time(seconds: float) -> str:
    total = max(0, int(round(float(seconds) * 100)))
    hours, remainder = divmod(total, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{centis:02d}"


def _ass_color(value: str, opacity: float = 0.0) -> str:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        text = "FFFFFF"
    red, green, blue = text[0:2], text[2:4], text[4:6]
    alpha = max(0, min(255, round(max(0.0, min(1.0, opacity)) * 255)))
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
    )


def build_short_ass(
    blocks: Sequence[CaptionBlock],
    *,
    font_family: str = "Arial",
    font_size: int = DEFAULT_FONT_SIZE,
    primary_color: str = "#FFFFFF",
    highlight_color: str = "#FFD400",
    outline_color: str = "#000000",
    outline_width: int = DEFAULT_OUTLINE,
    shadow: int = DEFAULT_SHADOW,
    uppercase: bool = False,
    wrap_style: int = 0,
) -> str:
    from videoflow.application.fonts import resolve_font_family

    family = resolve_font_family(font_family) or font_family
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {CANVAS_WIDTH}
PlayResY: {CANVAS_HEIGHT}
WrapStyle: {int(wrap_style)}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{family},{int(font_size)},{_ass_color(primary_color)},{_ass_color(highlight_color)},{_ass_color(outline_color)},{_ass_color(outline_color, 0.5)},-1,0,0,0,100,100,0,0,1,{int(outline_width)},{int(shadow)},5,140,140,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows: list[str] = []
    for block in sorted(blocks, key=lambda item: (item.start, item.end)):
        if block.end <= block.start:
            continue
        lines = [line for line in block.lines if line.strip()]
        if not lines:
            lines = [block.text]
        if uppercase:
            lines = [line.upper() for line in lines]
        body = "\\N".join(_escape(line) for line in lines)
        override = f"{{\\an5\\pos({CANVAS_WIDTH // 2},{int(block.subtitle_y)})}}"
        rows.append(
            f"Dialogue: 0,{_ass_time(block.start)},{_ass_time(block.end)},"
            f"Default,,0,0,0,,{override}{body}"
        )
    return header + "\n".join(rows) + "\n"


__all__ = [
    "CaptionBlock",
    "CaptionWord",
    "assign_layouts",
    "build_short_ass",
    "caption_lines",
    "group_words",
    "proportional_words",
    "sanitize_blocks",
    "words_from_sentences",
    "wrap_words",
]
