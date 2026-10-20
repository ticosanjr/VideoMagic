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
from videoflow.domain.errors import InvalidRetakeIdsError
from videoflow.domain.state import LlmShortsResponse, Sentence

PROMPT = """\
Choose self-contained vertical clips from this transcript.
Each clip must have a hook and a conclusion and use consecutive sentence ids.
Minimum {minimum} seconds, maximum {maximum} seconds, at most {count} clips.
Return only JSON:
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
        }


def select_shorts(
    sentences: Sequence[Sentence],
    *,
    min_samples: int,
    max_samples: int,
    count: int,
    sample_rate: int = 48000,
    cuts: Sequence[tuple[int, int]] = (),
    client: LlmClient | None = None,
    warnings: list[str] | None = None,
) -> list[ShortClip]:
    notes = warnings if warnings is not None else []
    if not sentences or count <= 0:
        return []
    if client is not None:
        clips = _from_llm(
            sentences,
            min_samples=min_samples,
            max_samples=max_samples,
            count=count,
            sample_rate=sample_rate,
            cuts=cuts,
            client=client,
            warnings=notes,
        )
        if clips:
            return clips
        notes.append("LLM returned no usable shorts; using deterministic selection")
    return _deterministic(
        sentences,
        min_samples=min_samples,
        max_samples=max_samples,
        count=count,
        cuts=cuts,
        warnings=notes,
    )


def build_ass(
    events: Sequence[tuple[float, float, str]],
    *,
    font_size: int = 72,
) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows: list[str] = []
    for start, end, text in events:
        if end <= start:
            continue
        rows.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{_ass_text(text)}"
        )
    return header + "\n".join(rows) + "\n"


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


def _deterministic(
    sentences: Sequence[Sentence],
    *,
    min_samples: int,
    max_samples: int,
    count: int,
    cuts: Sequence[tuple[int, int]],
    warnings: list[str],
) -> list[ShortClip]:
    clips: list[ShortClip] = []
    index = 0
    while index < len(sentences) and len(clips) < count:
        start = sentences[index].start_sample
        end_index = index
        while (
            end_index + 1 < len(sentences)
            and sentences[end_index + 1].end_sample - start <= max_samples
        ):
            end_index += 1
        end = min(sentences[end_index].end_sample, start + max_samples)
        ids = tuple(item.id for item in sentences[index : end_index + 1])
        pieces = tuple(subtract_spans([(start, end)], cuts))
        if sum(piece_end - piece_start for piece_start, piece_end in pieces) >= min_samples:
            title = sentences[index].text[:60].strip() or f"Short {len(clips) + 1}"
            clips.append(
                ShortClip(
                    title=title,
                    start_sample=start,
                    end_sample=end,
                    sentence_ids=ids,
                    pieces=pieces,
                )
            )
            index = end_index + 1
        else:
            index += 1
    if not clips:
        warnings.append("No window reached the minimum duration")
    return clips


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
