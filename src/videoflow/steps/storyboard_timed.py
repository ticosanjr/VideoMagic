"""Timed storyboard units built from the narration word timestamps."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step

_STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das",
    "e", "em", "no", "na", "nos", "nas", "para", "por", "que", "com",
    "the", "and", "of", "to", "in", "is", "it", "for", "on", "with",
}


class TimedUnitsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script_path: str = Field(default="script/script.json", max_length=2000)
    transcript_path: str = Field(
        default="narration/transcript.json", max_length=2000
    )
    min_unit_seconds: float = Field(default=2.0, ge=0.5, le=60.0)
    max_unit_seconds: float = Field(default=14.0, ge=1.0, le=120.0)
    target_units: int = Field(default=0, ge=0, le=1000)


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _word_events(transcript: dict[str, Any], sample_rate: int) -> list[tuple[float, float, str]]:
    events: list[tuple[float, float, str]] = []
    for sentence in transcript.get("sentences", []) if isinstance(transcript, dict) else []:
        if not isinstance(sentence, dict):
            continue
        words = sentence.get("words") or []
        if isinstance(words, list) and words:
            for word in words:
                if not isinstance(word, dict):
                    continue
                start = float(word.get("start_sample") or 0) / sample_rate
                end = float(word.get("end_sample") or 0) / sample_rate
                text = str(word.get("word") or "").strip()
                if text and end >= start:
                    events.append((start, end, text))
            continue
        text = str(sentence.get("text") or "").strip()
        tokens = text.split()
        if not tokens:
            continue
        start = float(sentence.get("start_sample") or 0) / sample_rate
        end = float(sentence.get("end_sample") or 0) / sample_rate
        if end <= start:
            continue
        span = (end - start) / len(tokens)
        for index, token in enumerate(tokens):
            events.append((start + index * span, start + (index + 1) * span, token))
    return events


def _query(title: str, narration: str) -> str:
    words = re.findall(r"[0-9A-Za-zÀ-ÿ']+", f"{title} {narration}")
    useful = [word for word in words if word.casefold() not in _STOPWORDS]
    return " ".join((useful or words)[:14]) or title


def _layout(visual: str) -> str:
    value = visual.casefold()
    if any(token in value for token in ("lista", "list", "checklist", "passo")):
        return "full_screen"
    if any(token in value for token in ("close", "rosto", "face", "retrato")):
        return "presenter_close"
    if any(token in value for token in ("split", "lado", "duas colunas")):
        return "presenter_split"
    return "presenter_visual"


def _merge_units(
    units: list[dict[str, Any]],
    *,
    min_seconds: float,
    max_seconds: float,
    target: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for unit in units:
        if merged and (
            float(unit["duration_sec"]) < min_seconds
            or float(merged[-1]["duration_sec"]) < min_seconds
        ):
            previous = merged[-1]
            previous["end_sec"] = unit["end_sec"]
            previous["duration_sec"] = round(
                float(previous["end_sec"]) - float(previous["start_sec"]), 3
            )
            previous["narration"] = " ".join(
                item
                for item in (
                    str(previous.get("narration") or ""),
                    str(unit.get("narration") or ""),
                )
                if item
            )
            previous["visual"] = " ".join(
                dict.fromkeys(
                    item
                    for item in (
                        str(previous.get("visual") or ""),
                        str(unit.get("visual") or ""),
                    )
                    if item
                )
            )
            continue
        merged.append(unit)
    while target > 0 and len(merged) > target:
        index = min(
            range(len(merged) - 1),
            key=lambda item: float(merged[item]["duration_sec"]),
        )
        previous = merged[index]
        following = merged[index + 1]
        previous["end_sec"] = following["end_sec"]
        previous["duration_sec"] = round(
            float(previous["end_sec"]) - float(previous["start_sec"]), 3
        )
        previous["narration"] = " ".join(
            item
            for item in (
                str(previous.get("narration") or ""),
                str(following.get("narration") or ""),
            )
            if item
        )
        del merged[index + 1]
    for index, unit in enumerate(merged, start=1):
        unit["unit_id"] = f"UNIT-{index:04d}"
        unit["duration_sec"] = round(
            max(1.0, float(unit["end_sec"]) - float(unit["start_sec"])), 3
        )
    return merged


@register_step
class StoryboardTimedStep(BaseStep):
    type = "storyboard.timed"
    title = "Timed unit storyboard"
    description = (
        "Split the script into visual units using the narration word timestamps, "
        "so scene changes match the spoken track exactly."
    )
    status = "available"
    icon = "▤"
    color = "#22c55e"
    params_model = TimedUnitsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TimedUnitsParams.model_validate(params)
        script = _load(context.output / options.script_path, {})
        transcript = _load(context.output / options.transcript_path, {})
        sections = script.get("sections", []) if isinstance(script, dict) else []
        if not isinstance(sections, list) or not sections:
            raise IngestError("Timed storyboard requires the approved script.")
        sample_rate = int(transcript.get("sample_rate") or 48000)
        events = _word_events(transcript, sample_rate)
        units: list[dict[str, Any]] = []
        cursor = 0
        clock = 0.0
        for index, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue
            narration = str(section.get("narration") or "").strip()
            expected = max(1, len(narration.split()))
            slice_words = events[cursor : cursor + expected]
            cursor += expected
            if slice_words:
                start = slice_words[0][0]
                end = slice_words[-1][1]
            else:
                duration = float(section.get("duration_sec") or options.max_unit_seconds)
                start = clock
                end = clock + max(1.0, duration)
            clock = max(clock, end)
            duration = max(0.5, end - start)
            title = str(section.get("title") or f"Unit {index}")
            visual = str(section.get("visual") or "")
            units.append(
                {
                    "unit_id": f"UNIT-{len(units) + 1:04d}",
                    "section_id": section.get("id") or index,
                    "title": title,
                    "asset_query": _query(title, narration),
                    "layout": _layout(visual),
                    "start_sec": round(start, 3),
                    "end_sec": round(end, 3),
                    "duration_sec": round(duration, 3),
                    "narration": narration,
                    "visual": visual,
                }
            )
        units = _merge_units(
            units,
            min_seconds=options.min_unit_seconds,
            max_seconds=options.max_unit_seconds,
            target=options.target_units,
        )
        target = context.output / "storyboard" / "units.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"units": units, "count": len(units)}, indent=2, ensure_ascii=False
            )
            + "\n",
            encoding="utf-8",
        )
        markdown = context.output / "storyboard" / "units.md"
        lines = ["# Timed unit storyboard", ""]
        for unit in units:
            lines.extend(
                [
                    f"## {unit['unit_id']} — {unit['title']}",
                    f"- Time: {unit['start_sec']}–{unit['end_sec']}s",
                    f"- Layout: {unit['layout']}",
                    f"- Query: {unit['asset_query']}",
                    f"- Visual: {unit['visual']}",
                    "",
                ]
            )
        markdown.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        context.metadata["storyboard_units"] = units
        context.artifacts["storyboard_units"] = str(target)
        context.artifacts["storyboard_units_md"] = str(markdown)
        context.hashes["storyboard.timed"] = digest_payload(
            {
                "units": len(units),
                "duration": max((unit["end_sec"] for unit in units), default=0.0),
            }
        )
        io.report(100, f"{len(units)} timed unit(s) storyboarded")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("storyboard_units", "storyboard_units_md")
            if context.artifacts.get(key)
        )


__all__ = ["StoryboardTimedStep", "TimedUnitsParams"]
