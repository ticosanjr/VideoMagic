# ruff: noqa: E501
"""Vertical Short caption building (ASS) and timing helpers."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from videoflow.domain.config import CaptionStyle
from videoflow.domain.state import Sentence

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "com", "da", "das", "de",
    "do", "dos", "e", "em", "for", "from", "in", "is", "it", "na", "nas", "no",
    "nos", "o", "of", "on", "or", "os", "para", "por", "que", "the", "to",
    "um", "uma", "with",
}


@dataclass(frozen=True, slots=True)
class CaptionLine:
    start: float
    end: float
    text: str
    words: tuple[tuple[float, float, str], ...] = ()
    speaker: int = 0

def build_ass(
    events: Sequence[tuple[float, float, str]],
    *,
    style: CaptionStyle | None = None,
    width: int = 1080,
    height: int = 1920,
) -> str:
    lines = [
        CaptionLine(start=start, end=end, text=text) for start, end, text in events if end > start
    ]
    return build_ass_lines(lines, style=style, width=width, height=height)

def build_ass_lines(
    lines: Sequence[CaptionLine],
    *,
    style: CaptionStyle | None = None,
    width: int = 1080,
    height: int = 1920,
) -> str:
    caption = style or CaptionStyle()
    bold = -1 if caption.font_weight == "bold" else 0
    italic = -1 if caption.italic else 0
    border_style = 3 if caption.background_opacity > 0 else 1
    outline = caption.background_padding if border_style == 3 else caption.outline_width
    if border_style == 3:
        back_color = _ass_color(caption.background_color, caption.background_opacity)
    else:
        back_color = _ass_color(caption.shadow_color, caption.shadow_opacity)
    shadow = caption.shadow_offset if caption.shadow_opacity > 0 else 0
    margin_lr = max(0, round((1.0 - caption.max_width) * width / 2))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{caption.font_family},{caption.font_size},{_ass_color(caption.primary_color)},{_ass_color(caption.highlight_color)},{_ass_color(caption.outline_color)},{back_color},{bold},{italic},0,0,100,100,0,0,{border_style},{outline},{shadow},{caption.alignment},{margin_lr},{margin_lr},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows: list[str] = []
    x = round(caption.position_x * width)
    y = round(caption.position_y * height)
    for line in lines:
        if line.end <= line.start:
            continue
        override = f"{{\\an{caption.alignment}\\pos({x},{y})"
        if caption.speaker_colors and line.speaker < len(caption.speaker_colors):
            override += f"\\c{_ass_color(caption.speaker_colors[line.speaker])}"
        if caption.animation == "pop":
            override += "\\t(0,100,\\fscx110\\fscy110)\\t(100,220,\\fscx100\\fscy100)"
        override += "}"
        if line.words and caption.word_timing != "sentence":
            text = _karaoke_text(line, caption)
        else:
            text = _ass_text(_sentence_text(line.text, caption))
        rows.append(
            f"Dialogue: 0,{_ass_time(line.start)},{_ass_time(line.end)},Default,,0,0,0,,{override}{text}"
        )
    return header + "\n".join(rows) + "\n"

def caption_lines(
    sentences: Sequence[Sentence],
    pieces: Sequence[tuple[int, int]],
    *,
    sample_rate: int,
    word_timing: str = "engine",
    warnings: list[str] | None = None,
) -> list[CaptionLine]:
    """Map sentences and word timings onto the concatenated short timeline."""

    lines: list[CaptionLine] = []
    notes = warnings if warnings is not None else []
    warned = False
    cursor = 0
    for piece_start, piece_end in pieces:
        piece_duration = piece_end - piece_start
        for sentence in sentences:
            start = max(piece_start, sentence.start_sample)
            end = min(piece_end, sentence.end_sample)
            if end <= start:
                continue
            output_start = (cursor + (start - piece_start)) / sample_rate
            output_end = (cursor + (end - piece_start)) / sample_rate
            raw_words = [
                word
                for word in sentence.words
                if word.end_sample > piece_start and word.start_sample < piece_end
            ]
            if word_timing == "sentence":
                raw_words = []
            if raw_words:
                words = tuple(
                    (
                        (cursor + (max(piece_start, word.start_sample) - piece_start))
                        / sample_rate,
                        (cursor + (min(piece_end, word.end_sample) - piece_start)) / sample_rate,
                        word.word,
                    )
                    for word in raw_words
                    if min(piece_end, word.end_sample) > max(piece_start, word.start_sample)
                )
                text = " ".join(word[2] for word in words)
            elif word_timing == "proportional":
                words = _proportional_words(sentence.text, output_start, output_end)
                text = " ".join(word[2] for word in words)
            else:
                words = ()
                text = sentence.text
                if word_timing == "engine" and not warned:
                    notes.append(
                        "Captions fell back to sentence timing because the transcript has no word timings"
                    )
                    warned = True
            lines.append(
                CaptionLine(
                    start=output_start,
                    end=output_end,
                    text=text,
                    words=words,
                    speaker=sentence.speaker,
                )
            )
        cursor += piece_duration
    return lines

def sentence_events(
    sentences: Sequence[Sentence],
    pieces: Sequence[tuple[int, int]],
    *,
    sample_rate: int,
) -> list[tuple[float, float, str]]:
    """Map sentences onto the concatenated output timeline."""

    events: list[tuple[float, float, str]] = []
    cursor = 0
    for piece_start, piece_end in pieces:
        for sentence in sentences:
            start = max(piece_start, sentence.start_sample)
            end = min(piece_end, sentence.end_sample)
            if end <= start:
                continue
            output_start = cursor + (start - piece_start)
            output_end = cursor + (end - piece_start)
            events.append((output_start / sample_rate, output_end / sample_rate, sentence.text))
        cursor += piece_end - piece_start
    return events

def slugify(value: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return f"{index:02d}-{slug[:40] or 'short'}"

def _proportional_words(
    text: str,
    start: float,
    end: float,
) -> tuple[tuple[float, float, str], ...]:
    tokens = text.split()
    if not tokens or end <= start:
        return ()
    weights = [max(1, len(token)) for token in tokens]
    total = sum(weights)
    words: list[tuple[float, float, str]] = []
    cursor = start
    for index, (token, weight) in enumerate(zip(tokens, weights, strict=True)):
        word_end = end if index == len(tokens) - 1 else cursor + (end - start) * weight / total
        words.append((cursor, word_end, token))
        cursor = word_end
    return tuple(words)

def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{centis:02d}"

def _ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")

def _display_text(text: str, style: CaptionStyle) -> str:
    value = text
    for source, target in style.brand_vocabulary.items():
        if source.strip():
            value = re.sub(
                rf"\b{re.escape(source)}\b",
                target,
                value,
                flags=re.IGNORECASE,
            )
    value = value.upper() if style.uppercase else value
    return _censor_text(value, style)

def _sentence_text(text: str, style: CaptionStyle) -> str:
    value = _display_text(text, style)
    if style.keyword_highlight_enabled:
        keywords = style.keyword_words or _auto_keywords(value)
        if keywords:
            pattern = re.compile(
                r"\b(" + "|".join(re.escape(word) for word in keywords) + r")\b",
                re.IGNORECASE,
            )
            value = pattern.sub(
                lambda match: f"{{\\c&H{_ass_rgb(style.keyword_color)}&}}"
                f"{match.group(0)}{{\\c&H{_ass_rgb(style.primary_color)}&}}",
                value,
            )
    if style.emoji_enabled and style.emoji_map:
        for word, emoji in sorted(style.emoji_map.items(), key=lambda item: -len(item[0])):
            if word.strip():
                value = re.sub(
                    rf"\b{re.escape(word)}\b",
                    f"{word} {emoji}",
                    value,
                    count=1,
                    flags=re.IGNORECASE,
                )
    return value

def _auto_keywords(text: str) -> list[str]:
    words = [
        word
        for word in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", text.casefold())
        if word not in _STOPWORDS
    ]
    return [word for word, _count in Counter(words).most_common(3)]

def _ass_rgb(value: str) -> str:
    red = value[1:3]
    green = value[3:5]
    blue = value[5:7]
    return f"{blue}{green}{red}".upper()

def _censor_text(text: str, style: CaptionStyle) -> str:
    if not style.censor_enabled or not style.censor_words:
        return text
    terms = sorted(
        (re.escape(word) for word in style.censor_words if word.strip()),
        key=len,
        reverse=True,
    )
    if not terms:
        return text
    pattern = re.compile(r"\b(" + "|".join(terms) + r")\b", re.IGNORECASE)
    return pattern.sub(style.censor_replacement, text)

def _karaoke_text(line: CaptionLine, style: CaptionStyle) -> str:
    tag = "kf" if style.animation == "sweep" else "k"
    words = line.words
    parts: list[str] = []
    if words and words[0][0] > line.start:
        gap = max(1, round((words[0][0] - line.start) * 100))
        parts.append(f"{{\\{tag}{gap}}}")
    for index, (start, _end, word) in enumerate(words):
        next_start = words[index + 1][0] if index + 1 < len(words) else line.end
        duration = max(1, round((next_start - start) * 100))
        suffix = " " if index + 1 < len(words) else ""
        parts.append(f"{{\\{tag}{duration}}}{_ass_text(_display_text(word, style))}{suffix}")
    return "".join(parts)

def _ass_color(value: str, opacity: float = 1.0) -> str:
    red = int(value[1:3], 16)
    green = int(value[3:5], 16)
    blue = int(value[5:7], 16)
    alpha = round((1.0 - max(0.0, min(1.0, opacity))) * 255)
    return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"
