# ruff: noqa: E501
"""Vertical short selection and subtitle generation.

Selection is deterministic by default. With an LLM client, the model proposes
sentence ids and the domain validates and conforms them. Culled ranges are
subtracted before duration checks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from videoflow.adapters import LlmClient
from videoflow.application.retakes import subtract_spans
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import InvalidRetakeIdsError
from videoflow.domain.state import LlmShortsResponse, Sentence

SHORT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}


def short_dimensions(aspect: str) -> tuple[int, int]:
    """Return the render size for a configured Short aspect."""

    return SHORT_DIMENSIONS.get(aspect, SHORT_DIMENSIONS["9:16"])


PROMPT = """\
Choose the most important, impactful, hooky, self-contained vertical clips from
this transcript. Prefer surprising insights, strong claims, concrete numbers,
emotional turns, mistakes, secrets, contrasts, and clear conclusions. Avoid
overlapping clips, avoid the intro and outro boilerplate, and make the clips
different from each other. Each clip must use consecutive sentence ids, have a
hook and a conclusion, be at least {minimum} seconds and at most {maximum}
seconds, and return at most {count} clips. Return only JSON:
{{"clips":[{{"title":"short title","sentence_ids":[ints]}}],"reasoning":"short reason"}}
Sentences:
"""


@dataclass(frozen=True, slots=True)
class ShortClip:
    title: str
    start_sample: int
    end_sample: int
    sentence_ids: tuple[int, ...]
    pieces: tuple[tuple[int, int], ...]
    score: float = 0.0

    @property
    def duration_samples(self) -> int:
        return sum(end - start for start, end in self.pieces)

    def to_dict(self, sample_rate: int) -> dict[str, object]:
        return {
            "title": self.title,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "start_sec": round(self.start_sample / sample_rate, 3),
            "end_sec": round(self.end_sample / sample_rate, 3),
            "duration_sec": round(self.duration_samples / sample_rate, 3),
            "sentence_ids": list(self.sentence_ids),
            "pieces": [list(piece) for piece in self.pieces],
            "score": round(self.score, 3),
        }


@dataclass(frozen=True, slots=True)
class CaptionLine:
    start: float
    end: float
    text: str
    words: tuple[tuple[float, float, str], ...] = ()


def select_shorts(
    sentences: Sequence[Sentence],
    *,
    min_samples: int,
    max_samples: int,
    count: int,
    min_clips: int = 1,
    selection_mode: str = "auto",
    sample_rate: int = 48000,
    cuts: Sequence[tuple[int, int]] = (),
    client: LlmClient | None = None,
    warnings: list[str] | None = None,
) -> list[ShortClip]:
    notes = warnings if warnings is not None else []
    if not sentences or count <= 0:
        return []
    llm_clips: list[ShortClip] = []
    if client is not None and selection_mode in {"auto", "llm"}:
        llm_clips = _from_llm(
            sentences,
            min_samples=min_samples,
            max_samples=max_samples,
            count=count,
            sample_rate=sample_rate,
            cuts=cuts,
            client=client,
            warnings=notes,
        )
        if not llm_clips:
            notes.append("LLM returned no usable shorts; using heuristic selection")
    elif selection_mode == "llm":
        notes.append(
            "LLM selection was requested but no client is configured; using heuristic selection"
        )

    heuristic = _heuristic(
        sentences,
        min_samples=min_samples,
        max_samples=max_samples,
        count=count,
        cuts=cuts,
    )
    selected = _merge_clips(llm_clips, heuristic, count) if llm_clips else heuristic
    selected.sort(key=lambda item: item.start_sample)
    if len(selected) < min_clips:
        notes.append(
            f"Only {len(selected)} shorts could be selected; configured minimum is {min_clips}"
        )
    return selected


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
        if caption.animation == "pop":
            override += "\\t(0,100,\\fscx110\\fscy110)\\t(100,220,\\fscx100\\fscy100)"
        override += "}"
        if line.words and caption.word_timing != "sentence":
            text = _karaoke_text(line, caption)
        else:
            text = _ass_text(_display_text(line.text, caption))
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
            lines.append(CaptionLine(start=output_start, end=output_end, text=text, words=words))
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


def slice_pieces(
    pieces: Sequence[tuple[int, int]], start_sample: int, end_sample: int
) -> list[tuple[int, int]]:
    """Trim an assembled Short and return source pieces for the new range."""

    total = sum(end - start for start, end in pieces)
    end_sample = min(end_sample, total)
    if start_sample < 0 or end_sample <= start_sample:
        return []
    cursor = 0
    trimmed: list[tuple[int, int]] = []
    for piece_start, piece_end in pieces:
        length = piece_end - piece_start
        overlap_start = max(start_sample, cursor)
        overlap_end = min(end_sample, cursor + length)
        if overlap_end > overlap_start:
            trimmed.append(
                (
                    piece_start + (overlap_start - cursor),
                    piece_start + (overlap_end - cursor),
                )
            )
        cursor += length
        if cursor >= end_sample:
            break
    return trimmed


def slugify(value: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return f"{index:02d}-{slug[:40] or 'short'}"


def _heuristic(
    sentences: Sequence[Sentence],
    *,
    min_samples: int,
    max_samples: int,
    count: int,
    cuts: Sequence[tuple[int, int]],
) -> list[ShortClip]:
    candidates: list[ShortClip] = []
    for start_index, sentence in enumerate(sentences):
        start = sentence.start_sample
        end_index = start_index
        while (
            end_index + 1 < len(sentences)
            and sentences[end_index + 1].end_sample - start <= max_samples
        ):
            end_index += 1
        end = min(sentences[end_index].end_sample, start + max_samples)
        pieces = tuple(subtract_spans([(start, end)], cuts))
        duration = sum(piece_end - piece_start for piece_start, piece_end in pieces)
        if duration < min_samples:
            continue
        text = " ".join(item.text for item in sentences[start_index : end_index + 1])
        score = _score_text(text, duration, min_samples, max_samples)
        candidates.append(
            ShortClip(
                title=text[:60].strip() or f"Short {len(candidates) + 1}",
                start_sample=start,
                end_sample=end,
                sentence_ids=tuple(item.id for item in sentences[start_index : end_index + 1]),
                pieces=pieces,
                score=score,
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    selected: list[ShortClip] = []
    for candidate in candidates:
        if any(_overlap(candidate, item) for item in selected):
            continue
        selected.append(candidate)
        if len(selected) >= count:
            break
    return selected


def _score_text(text: str, duration: int, minimum: int, maximum: int) -> float:
    lowered = text.casefold()
    score = 0.0
    markers = {
        "porque": 3.0,
        "mas": 1.5,
        "então": 1.5,
        "nunca": 2.5,
        "sempre": 1.5,
        "segredo": 3.0,
        "erro": 3.0,
        "maior": 2.0,
        "melhor": 2.0,
        "pior": 2.5,
        "descobri": 3.0,
        "imagina": 2.0,
        "você": 1.0,
        "resultado": 2.0,
        "problema": 2.0,
        "verdade": 2.0,
        "incrível": 2.5,
        "chocante": 3.0,
        "importante": 1.5,
        "principal": 1.5,
        "primeiro": 1.0,
        "último": 1.0,
        "como": 1.0,
        "por que": 2.0,
        "quanto": 1.5,
        "mil": 1.5,
        "milhão": 2.0,
        "%": 2.0,
        "but": 1.5,
        "because": 3.0,
        "never": 2.5,
        "secret": 3.0,
        "mistake": 3.0,
        "most": 2.0,
        "best": 2.0,
        "worst": 2.5,
        "discovered": 3.0,
        "imagine": 2.0,
        "result": 2.0,
        "problem": 2.0,
        "truth": 2.0,
        "incredible": 2.5,
        "shocking": 3.0,
        "how": 1.0,
        "why": 2.0,
        "million": 2.0,
    }
    score += sum(weight for marker, weight in markers.items() if marker in lowered)
    score += 4.0 if "?" in text else 0.0
    score += 2.0 if "!" in text else 0.0
    score += 2.0 if re.search(r"\d", text) else 0.0
    target = (minimum + maximum) / 2
    score += max(0.0, 3.0 - abs(duration - target) / max(1, target) * 3.0)
    return score


def _merge_clips(
    primary: Sequence[ShortClip],
    fallback: Sequence[ShortClip],
    count: int,
) -> list[ShortClip]:
    merged = list(primary)
    for candidate in fallback:
        if len(merged) >= count:
            break
        if any(_overlap(candidate, item) for item in merged):
            continue
        if any(candidate.sentence_ids == item.sentence_ids for item in merged):
            continue
        merged.append(candidate)
    return merged


def _overlap(left: ShortClip, right: ShortClip) -> bool:
    return left.start_sample < right.end_sample and right.start_sample < left.end_sample


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


def _from_llm(
    sentences: Sequence[Sentence],
    *,
    min_samples: int,
    max_samples: int,
    count: int,
    sample_rate: int,
    cuts: Sequence[tuple[int, int]],
    client: LlmClient,
    warnings: list[str],
) -> list[ShortClip]:
    by_id = {item.id: item for item in sentences}
    payload = [{"id": item.id, "text": item.text} for item in sentences]
    prompt = PROMPT.format(
        minimum=round(min_samples / sample_rate, 1),
        maximum=round(max_samples / sample_rate, 1),
        count=count,
    ) + json.dumps(payload, ensure_ascii=False)
    raw = client.complete_json(prompt, "videoflow.shorts")
    response = LlmShortsResponse.model_validate(raw)
    clips: list[ShortClip] = []
    for proposal in response.clips[:count]:
        unknown = [item for item in proposal.sentence_ids if item not in by_id]
        if unknown:
            raise InvalidRetakeIdsError(unknown)
        chosen = sorted(
            (by_id[item] for item in proposal.sentence_ids), key=lambda item: item.start_sample
        )
        start = chosen[0].start_sample
        end = min(chosen[-1].end_sample, start + max_samples)
        pieces = tuple(subtract_spans([(start, end)], cuts))
        duration = sum(piece_end - piece_start for piece_start, piece_end in pieces)
        if duration < min_samples:
            warnings.append(f"Dropped '{proposal.title}': {duration} samples after culls")
            continue
        clips.append(
            ShortClip(
                title=proposal.title,
                start_sample=start,
                end_sample=end,
                sentence_ids=tuple(item.id for item in chosen),
                pieces=pieces,
                score=_score_text(proposal.title, duration, min_samples, max_samples),
            )
        )
    return clips


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{centis:02d}"


def _ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def _display_text(text: str, style: CaptionStyle) -> str:
    return text.upper() if style.uppercase else text


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
