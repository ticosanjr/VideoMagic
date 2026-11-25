# ruff: noqa: E501
"""Vertical Short caption building (ASS) and timing helpers."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path

from videoflow.domain.config import CaptionStyle
from videoflow.domain.state import Sentence

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "for",
    "from",
    "in",
    "is",
    "it",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "of",
    "on",
    "or",
    "os",
    "para",
    "por",
    "que",
    "the",
    "to",
    "um",
    "uma",
    "with",
}


@dataclass(frozen=True, slots=True)
class CaptionLine:
    start: float
    end: float
    text: str
    words: tuple[tuple[float, float, str], ...] = ()
    speaker: int = 0
    effect_fallback: bool = False


def caption_safe_zone(width: int, height: int, layout: str = "") -> dict[str, object]:
    """Return the delivery-safe caption box for a canvas and layout."""

    key = str(layout or "").strip().lower()
    vertical = {
        "full_face": 1340,
        "fullscreen_punchin": 1340,
        "full_screen": 1340,
        "split_broll": 960,
        "split_top_visual": 960,
        "split_screen_safe": 840,
        "split_screen": 840,
        "split_screen_50_50": 840,
    }
    if width == 1080 and height == 1920:
        return {
            "alignment": 5,
            "margin_l": 140,
            "margin_r": 140,
            "margin_v": 0,
            "pos": (width // 2, vertical.get(key, 1340)),
            "wrap_style": 0,
            "max_chars": 18,
            "short_safe": True,
        }
    if width == 1080 and height == 1350:
        return {
            "alignment": 2,
            "margin_l": 140,
            "margin_r": 140,
            "margin_v": 189,
            "pos": None,
            "wrap_style": 0,
            "max_chars": 18,
            "short_safe": True,
        }
    if width > height:
        return {
            "alignment": 2,
            "margin_l": 60,
            "margin_r": 60,
            "margin_v": 49,
            "pos": None,
            "wrap_style": 2,
            "max_chars": 42,
        }
    return {
        "alignment": 2,
        "margin_l": 60,
        "margin_r": 60,
        "margin_v": _adaptive_margin_v(CaptionStyle(), width, height),
        "pos": None,
        "wrap_style": 2,
        "max_chars": 24,
    }


def build_ass(
    events: Sequence[tuple[float, float, str]],
    *,
    style: CaptionStyle | None = None,
    width: int = 1080,
    height: int = 1920,
    layout: str = "",
) -> str:
    lines = [
        CaptionLine(start=start, end=end, text=text) for start, end, text in events if end > start
    ]
    return build_ass_lines(
        lines,
        style=style,
        width=width,
        height=height,
        layout=layout,
    )


def _adaptive_margin_v(caption: CaptionStyle, width: int, height: int) -> int:
    """Keep captions above social chrome and near the lower third in 16:9."""

    if height > width:
        return max(0, round(height * 0.22))
    if width > height:
        return max(0, round(height * 0.045))
    return max(0, round(height * 0.10))


def _same_caption_text(left: str, right: str) -> bool:
    return " ".join(left.casefold().split()) == " ".join(right.casefold().split())


def _similar_caption_text(left: str, right: str) -> bool:
    first = " ".join(left.casefold().split())
    second = " ".join(right.casefold().split())
    if not first or not second:
        return False
    return SequenceMatcher(None, first, second).ratio() >= 0.85


def _inside_ranges(sample: int, ranges: Sequence[tuple[int, int]]) -> bool:
    return any(start <= sample < end for start, end in ranges)


def filter_caption_sentences(
    sentences: Sequence[Sentence],
    *,
    discard_ids: set[int] | None = None,
    kept_source_ranges: Sequence[tuple[int, int]] = (),
) -> list[Sentence]:
    """Drop discarded sentences and words outside the kept source ranges.

    A word survives only when its midpoint falls inside a kept range. When a
    sentence loses words, its text and bounds are rebuilt from the survivors so
    a removed take can never reappear in the captions. An empty range list
    means "no timeline filter" and keeps every non-discarded sentence.
    """

    discarded = set(discard_ids or ())
    ranges = sorted(
        (int(start), int(end))
        for start, end in kept_source_ranges
        if int(end) > int(start)
    )
    result: list[Sentence] = []
    for sentence in sentences:
        if sentence.id in discarded:
            continue
        if not sentence.words:
            midpoint = (sentence.start_sample + sentence.end_sample) // 2
            if ranges and not _inside_ranges(midpoint, ranges):
                continue
            result.append(sentence)
            continue
        kept = [
            word
            for word in sentence.words
            if not ranges
            or _inside_ranges(
                (word.start_sample + word.end_sample) // 2,
                ranges,
            )
        ]
        if not kept:
            continue
        result.append(
            sentence.model_copy(
                update={
                    "start_sample": kept[0].start_sample,
                    "end_sample": kept[-1].end_sample,
                    "text": " ".join(word.word for word in kept),
                    "words": kept,
                }
            )
        )
    return result


def _normalize_caption_lines(lines: Sequence[CaptionLine]) -> list[CaptionLine]:
    """Sort events and guarantee that two captions never overlap.

    A repeated adjacent event is merged; any other overlap trims the earlier
    event 15 ms before the next one starts.
    """

    ordered = sorted(
        (line for line in lines if line.end > line.start),
        key=lambda line: (line.start, line.end),
    )
    result: list[CaptionLine] = []
    for line in ordered:
        if not result:
            result.append(line)
            continue
        previous = result[-1]
        if _same_caption_text(previous.text, line.text) and (
            line.start <= previous.end + 0.05
        ):
            result[-1] = replace(previous, end=max(previous.end, line.end))
            continue
        if line.start >= previous.end:
            result.append(line)
            continue
        if line.start <= previous.start:
            if line.end > previous.end:
                result[-1] = line
            continue
        end = line.start - 0.015
        if end > previous.start:
            result[-1] = replace(previous, end=end)
        result.append(line)
    return result


def build_ass_lines(
    lines: Sequence[CaptionLine],
    *,
    style: CaptionStyle | None = None,
    width: int = 1080,
    height: int = 1920,
    layout: str = "",
) -> str:
    caption = style or CaptionStyle()
    lines = _normalize_caption_lines(lines)
    zone = caption_safe_zone(width, height, layout)
    margin_v = int(zone["margin_v"])
    from videoflow.application.fonts import resolve_font_family

    font_family = resolve_font_family(caption.font_family) or caption.font_family
    bold = -1 if caption.font_weight == "bold" else 0
    italic = -1 if caption.italic else 0
    border_style = 3 if caption.background_opacity > 0 else 1
    outline = caption.background_padding if border_style == 3 else caption.outline_width
    if border_style == 3:
        back_color = _ass_color(caption.background_color, caption.background_opacity)
    else:
        back_color = _ass_color(caption.shadow_color, caption.shadow_opacity)
    shadow = caption.shadow_offset if caption.shadow_opacity > 0 else 0
    margin_l = int(zone["margin_l"])
    margin_r = int(zone["margin_r"])
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: {int(zone["wrap_style"])}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_family},{caption.font_size},{_ass_color(caption.primary_color)},{_ass_color(caption.highlight_color)},{_ass_color(caption.outline_color)},{back_color},{bold},{italic},0,0,100,100,0,0,{border_style},{outline},{shadow},{int(zone["alignment"])},{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows: list[str] = []
    zone_pos = zone["pos"]
    if isinstance(zone_pos, tuple):
        x, y = int(zone_pos[0]), int(zone_pos[1])
        custom_position = True
    else:
        x = round(caption.position_x * width)
        y = round(caption.position_y * height)
        custom_position = (
            abs(caption.position_x - 0.5) > 1e-6
            or abs(caption.position_y - 0.78) > 1e-6
        )
    for line in lines:
        if line.end <= line.start:
            continue
        override = f"{{\\an{int(zone['alignment'])}"
        if custom_position:
            override += f"\\pos({x},{y})"
        if caption.speaker_colors and line.speaker < len(caption.speaker_colors):
            override += f"\\c{_ass_color(caption.speaker_colors[line.speaker])}"
        if caption.effect == "pop":
            override += "\\t(0,100,\\fscx110\\fscy110)\\t(100,220,\\fscx100\\fscy100)"
        override += "}"
        if caption.effect != "static":
            text = _karaoke_text(line, caption)
        else:
            text = _sentence_text(line.text, caption)
        text = _wrap_ass_markup(
            text,
            caption,
            width,
            max_chars=int(zone["max_chars"]),
        )
        rows.append(
            f"Dialogue: 0,{_ass_time(line.start)},{_ass_time(line.end)},Default,,0,0,0,,{override}{text}"
        )
    seen: set[tuple[str, str, str]] = set()
    unique: list[str] = []
    for row in rows:
        parts = row.split(",", 9)
        key = (parts[1], parts[2], parts[9]) if len(parts) >= 10 else ()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(row)
    return header + "\n".join(unique) + "\n"


def caption_lines(
    sentences: Sequence[Sentence],
    pieces: Sequence[tuple[int, int]],
    *,
    sample_rate: int,
    word_timing: str = "word",
    effect: str = "static",
    max_words: int = 6,
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
                if word.end_sample > piece_start
                and word.start_sample < piece_end
                and piece_start
                <= (word.start_sample + word.end_sample) // 2
                < piece_end
            ]
            requires_words = effect != "static"
            fallback = False
            if word_timing == "sentence":
                raw_words = []
            if raw_words and word_timing != "sentence":
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
            elif requires_words:
                words = _proportional_words(sentence.text, output_start, output_end)
                text = " ".join(word[2] for word in words)
                fallback = True
                if not warned:
                    notes.append(
                        "Captions used proportional word timings for the requested effect"
                    )
                    warned = True
            elif word_timing == "proportional":
                words = _proportional_words(sentence.text, output_start, output_end)
                text = " ".join(word[2] for word in words)
            else:
                words = ()
                text = sentence.text
                if word_timing == "word" and not warned:
                    notes.append(
                        "Captions fell back to sentence timing because the transcript has no word timings"
                    )
                    warned = True
            lines.extend(
                _split_caption_blocks(
                    CaptionLine(
                        start=output_start,
                        end=output_end,
                        text=text,
                        words=words,
                        speaker=sentence.speaker,
                        effect_fallback=fallback,
                    ),
                    max_words,
                )
            )
        cursor += piece_duration
    return _merge_caption_lines(lines)


def _split_caption_blocks(line: CaptionLine, max_words: int) -> list[CaptionLine]:
    """Split one timed sentence into stable 4-6 word caption blocks."""

    limit = max(0, int(max_words))
    if limit <= 0:
        return [line]
    tokens = [item[2] for item in line.words] if line.words else line.text.split()
    if len(tokens) <= limit:
        return [line]
    if line.words:
        chunks = [
            list(line.words[index : index + limit])
            for index in range(0, len(line.words), limit)
        ]
        if len(chunks) > 1 and len(chunks[-1]) < 4:
            take = min(4 - len(chunks[-1]), max(0, len(chunks[-2]) - 4))
            if take:
                chunks[-1] = chunks[-2][-take:] + chunks[-1]
                chunks[-2] = chunks[-2][:-take]
        return [
            CaptionLine(
                start=chunk[0][0],
                end=chunk[-1][1],
                text=" ".join(item[2] for item in chunk),
                words=tuple(chunk),
                speaker=line.speaker,
                effect_fallback=line.effect_fallback,
            )
            for chunk in chunks
            if chunk
        ]
    chunks = [tokens[index : index + limit] for index in range(0, len(tokens), limit)]
    if len(chunks) > 1 and len(chunks[-1]) < 4:
        take = min(4 - len(chunks[-1]), max(0, len(chunks[-2]) - 4))
        if take:
            chunks[-1] = chunks[-2][-take:] + chunks[-1]
            chunks[-2] = chunks[-2][:-take]
    weights = [max(1, len(" ".join(chunk))) for chunk in chunks]
    total = sum(weights)
    cursor = line.start
    blocks: list[CaptionLine] = []
    for index, (chunk, weight) in enumerate(zip(chunks, weights, strict=True)):
        end = line.end if index == len(chunks) - 1 else cursor + (line.end - line.start) * weight / total
        blocks.append(
            CaptionLine(
                start=cursor,
                end=end,
                text=" ".join(chunk),
                speaker=line.speaker,
                effect_fallback=line.effect_fallback,
            )
        )
        cursor = end
    return blocks


def _merge_caption_lines(lines: Sequence[CaptionLine]) -> list[CaptionLine]:
    """Merge adjacent duplicate text created when a sentence crosses a cut."""

    merged: list[CaptionLine] = []
    for line in lines:
        if line.end <= line.start:
            continue
        if merged:
            previous = merged[-1]
            exact = previous.text.strip() == line.text.strip()
            similar = _similar_caption_text(previous.text, line.text)
            within_window = line.start - previous.start < 2.0
            if (exact and line.start <= previous.end + 0.10) or (
                similar and within_window and line.start >= previous.start
            ):
                merged[-1] = CaptionLine(
                    start=previous.start,
                    end=max(previous.end, line.end),
                    text=previous.text,
                    words=previous.words or line.words,
                    speaker=previous.speaker,
                    effect_fallback=previous.effect_fallback or line.effect_fallback,
                )
                continue
            if exact and previous.end > line.start:
                continue
        merged.append(line)
    return merged


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
    if not style.keyword_highlight_enabled:
        return _ass_text(value)
    keywords = style.keyword_words or _auto_keywords(value)
    if not keywords:
        return _ass_text(value)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(word) for word in keywords) + r")\b",
        re.IGNORECASE,
    )
    parts: list[str] = []
    cursor = 0
    for match in pattern.finditer(value):
        parts.append(_ass_text(value[cursor : match.start()]))
        parts.append(
            f"{{\\c&H{_ass_rgb(style.keyword_color)}&}}"
            f"{_ass_text(match.group(0))}"
            f"{{\\c&H{_ass_rgb(style.primary_color)}&}}"
        )
        cursor = match.end()
    parts.append(_ass_text(value[cursor:]))
    return "".join(parts)


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
    tag = "kf" if style.effect == "karaoke_sweep" else "k"
    words = line.words or _proportional_words(line.text, line.start, line.end)
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


def _wrap_ass_markup(
    text: str,
    style: CaptionStyle,
    width: int,
    *,
    max_chars: int = 0,
) -> str:
    r"""Insert explicit ``\N`` breaks outside ASS override tags."""

    if max_chars <= 0:
        max_chars = max(
            8,
            int(style.max_width * width / max(1.0, style.font_size * 0.55)),
        )
    tokens = re.findall(r"\{[^}]*\}|[^\s]+|\s+", text)
    lines: list[str] = []
    current = ""
    current_len = 0
    for token in tokens:
        if token.startswith("{"):
            current += token
            continue
        if token.isspace():
            if current and not current.endswith(" "):
                current += " "
            continue
        if current_len and current_len + len(token) > max_chars:
            lines.append(current.rstrip())
            current = token
            current_len = len(token)
        else:
            current += token
            current_len += len(token)
    if current.strip():
        lines.append(current.rstrip())
    return "\\N".join(lines)


def shift_ass_text(text: str, offset_sec: float) -> str:
    """Shift every Dialogue timestamp by ``offset_sec`` seconds."""

    if abs(offset_sec) < 1e-6:
        return text
    pattern = re.compile(
        r"^(Dialogue:\s*[^,]*,\s*)(\d+:\d{2}:\d{2}\.\d{2})(\s*,\s*)(\d+:\d{2}:\d{2}\.\d{2})"
    )

    def repl(match: re.Match[str]) -> str:
        start = _ass_seconds(match.group(2)) + offset_sec
        end = _ass_seconds(match.group(4)) + offset_sec
        return f"{match.group(1)}{_ass_time(start)}{match.group(3)}{_ass_time(end)}"

    return "\n".join(pattern.sub(repl, line) for line in text.splitlines()) + (
        "\n" if text.endswith("\n") else ""
    )


def shift_ass_file(path: Path, offset_sec: float, target: Path | None = None) -> Path:
    source = Path(path)
    destination = (
        Path(target) if target is not None else source.with_name(f"{source.stem}.shifted.ass")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        shift_ass_text(source.read_text(encoding="utf-8-sig", errors="replace"), offset_sec),
        encoding="utf-8",
    )
    return destination


def _ass_seconds(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def merge_ass_files(paths: Sequence[Path], target: Path) -> Path:
    """Combine ASS files so one FFmpeg pass can burn titles and captions."""

    existing = [Path(path) for path in paths if Path(path).is_file()]
    if not existing:
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("", encoding="utf-8")
        return destination
    script_info: list[str] = []
    styles: list[str] = []
    events: list[str] = []
    seen_styles: set[str] = set()
    seen_events: set[str] = set()
    for path in existing:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        section = ""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped
                if section == "[Script Info]":
                    continue
                continue
            if section == "[Script Info]" and stripped:
                if not any(item.startswith(("PlayResX", "PlayResY")) for item in script_info):
                    script_info.append(stripped)
            elif section == "[V4+ Styles]" and stripped.startswith("Style:"):
                name = stripped.split(",", 1)[0]
                if name not in seen_styles:
                    seen_styles.add(name)
                    styles.append(stripped)
            elif (
                section == "[Events]"
                and stripped.startswith("Dialogue:")
                and stripped not in seen_events
            ):
                seen_events.add(stripped)
                events.append(stripped)
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        *script_info,
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
    ]
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(header).rstrip() + "\n", encoding="utf-8")
    return destination
