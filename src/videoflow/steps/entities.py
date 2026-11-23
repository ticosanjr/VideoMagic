"""Apply human entity corrections to the narrative manifest."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.files import read_json_or
from videoflow.application.narrative import PROPER, extract_entities
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step

_MAPPING = re.compile(r"\s*(?:->|=>|\|)\s*")


class EntityApplyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corrections_path: str = Field(default="entities/corrections.json", max_length=2000)
    narrative_path: str = Field(default="narrative/entities.json", max_length=2000)
    output_stem: str = Field(default="entities-corrected", max_length=120)


def _mappings(answers: dict[str, Any]) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for key in ("people_corrections", "visual_corrections", "metric_corrections"):
        text = str(answers.get(key) or "")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = _MAPPING.split(line, maxsplit=1)
            if len(parts) != 2:
                continue
            source, target = parts[0].strip(), parts[1].strip()
            if source and target:
                mappings[source] = target
    return mappings


def _replace(value: Any, mappings: dict[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for source, target in sorted(mappings.items(), key=lambda item: -len(item[0])):
            result = result.replace(source, target)
        return result
    if isinstance(value, list):
        return [_replace(item, mappings) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, mappings) for key, item in value.items()}
    return value


class EntityExtractParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocks_path: str = Field(default="narrative/blocks.json", max_length=2000)
    script_path: str = Field(default="script/edition.md", max_length=2000)
    provider_id: str = ""
    max_entities: int = Field(default=200, ge=1, le=2000)
    language: str = Field(default="pt", max_length=20)
    known_entities: list[str] = Field(default_factory=list, max_length=500)


_SINGLE_NAME = re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b")
_QUOTED = re.compile(r"[\"“]([^\"”]{3,90})[\"”]")
_NAME_STOPWORDS = {
    "a",
    "as",
    "o",
    "os",
    "um",
    "uma",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "para",
    "com",
    "sem",
    "que",
    "se",
    "e",
    "ou",
    "mas",
    "ao",
    "aos",
    "às",
    "the",
    "this",
    "that",
    "these",
    "those",
    "and",
    "but",
    "first",
    "second",
    "third",
    "next",
    "then",
    "court",
    "case",
    "report",
    "image",
    "video",
    "document",
    "fonte",
    "caso",
    "relatório",
    "imagem",
    "vídeo",
    "documento",
}


def _block_items(payload: Any) -> list[dict[str, Any]]:
    items = payload.get("blocks") if isinstance(payload, dict) else payload
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _script_names(text: str) -> list[str]:
    names = {
        match.group(0).strip()
        for match in PROPER.finditer(text)
        if match.group(0).strip()
    }
    for match in _SINGLE_NAME.finditer(text):
        candidate = match.group(0).strip()
        if candidate and candidate.casefold() not in _NAME_STOPWORDS:
            names.add(candidate)
    return sorted(names, key=len, reverse=True)


def _canonical_name(raw: str, names: list[str]) -> str:
    value = raw.strip()
    lowered = value.casefold()
    for name in names:
        candidate = name.casefold()
        if lowered and (lowered in candidate or candidate in lowered):
            return name
    best = value
    best_ratio = 0.0
    for name in names:
        ratio = SequenceMatcher(None, lowered, name.casefold()).ratio()
        if ratio > best_ratio:
            best, best_ratio = name, ratio
    return best if best_ratio >= 0.72 else value


def _add_block_range(entry: dict[str, Any], block: dict[str, Any]) -> None:
    block_id = str(block.get("context_block_id") or "")
    if block_id and block_id not in entry["block_ids"]:
        entry["block_ids"].append(block_id)
    start = float(block.get("start_sec") or 0.0)
    end = float(block.get("end_sec") or 0.0)
    current_start = entry.get("start_sec")
    current_end = entry.get("end_sec")
    entry["start_sec"] = start if current_start is None else min(float(current_start), start)
    entry["end_sec"] = end if current_end is None else max(float(current_end), end)


def _entry(
    name: str,
    *,
    kind: str = "",
    raw_mentions: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "canonical_name": name,
        "name": name,
        "kind": kind,
        "raw_mentions": list(raw_mentions or []),
        "block_ids": [],
        "start_sec": None,
        "end_sec": None,
        "search_query": f"{name} official photo" if kind != "metric" else "",
    }
    return payload


def _deterministic_entities(
    blocks: list[dict[str, Any]],
    names: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    people: dict[str, dict[str, Any]] = {}
    objects: dict[str, dict[str, Any]] = {}
    metrics: dict[str, dict[str, Any]] = {}
    for block in blocks:
        text = str(block.get("text") or "")
        found = extract_entities(text, [])
        lowered = text.casefold()
        for name in names:
            if name.casefold() in lowered:
                raw = name
            else:
                tokens = [
                    token
                    for token in re.findall(r"[A-Za-zÀ-ÿ]{4,}", name)
                    if token.casefold() in lowered
                ]
                raw = tokens[0] if tokens else ""
            if not raw:
                continue
            entry = people.setdefault(
                name.casefold(), _entry(name, kind="person")
            )
            if raw not in entry["raw_mentions"]:
                entry["raw_mentions"].append(raw)
            _add_block_range(entry, block)
        for person in found.get("people", []):
            raw = str(person.get("raw_mention") or "").strip()
            if not raw:
                continue
            canonical = _canonical_name(raw, names)
            entry = people.setdefault(
                canonical.casefold(), _entry(canonical, kind="person")
            )
            if raw not in entry["raw_mentions"]:
                entry["raw_mentions"].append(raw)
            _add_block_range(entry, block)
        for location in found.get("locations", []):
            name = str(location.get("location_name") or "").strip()
            if not name:
                continue
            entry = objects.setdefault(
                name.casefold(), _entry(name, kind="location")
            )
            _add_block_range(entry, block)
        for metric in found.get("data_metrics", []):
            raw = str(metric.get("raw_value") or "").strip()
            if not raw:
                continue
            entry = metrics.setdefault(
                raw.casefold(),
                {
                    "raw_value": raw,
                    "formatted_display": str(
                        metric.get("formatted_display") or raw
                    ),
                    "chart_type": str(metric.get("chart_type") or "kinetic_counter"),
                    "block_ids": [],
                    "start_sec": None,
                    "end_sec": None,
                },
            )
            _add_block_range(entry, block)
    return people, objects, metrics


def _merge_model_entities(
    people: dict[str, dict[str, Any]],
    objects: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    payload: dict[str, Any],
    by_block: dict[str, dict[str, Any]],
    names: list[str],
) -> None:
    def ranges(entry: dict[str, Any], item: dict[str, Any]) -> None:
        for block_id in item.get("block_ids") or []:
            block = by_block.get(str(block_id))
            if block:
                _add_block_range(entry, block)

    for item in payload.get("people") or []:
        if not isinstance(item, dict):
            continue
        raw = str(
            item.get("canonical_name") or item.get("name") or ""
        ).strip()
        if not raw:
            continue
        canonical = _canonical_name(raw, names)
        entry = people.setdefault(
            canonical.casefold(), _entry(canonical, kind="person")
        )
        for mention in item.get("raw_mentions") or []:
            mention_text = str(mention).strip()
            if mention_text and mention_text not in entry["raw_mentions"]:
                entry["raw_mentions"].append(mention_text)
        ranges(entry, item)
    for item in payload.get("objects_locations_events") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("object") or "").strip()
        if not name:
            continue
        kind = str(item.get("kind") or "object").strip()
        entry = objects.setdefault(name.casefold(), _entry(name, kind=kind))
        ranges(entry, item)
    for item in payload.get("data_metrics") or []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("raw_value") or item.get("value") or "").strip()
        if not raw:
            continue
        entry = metrics.setdefault(
            raw.casefold(),
            {
                "raw_value": raw,
                "formatted_display": str(item.get("formatted_display") or raw),
                "chart_type": str(item.get("chart_type") or "kinetic_counter"),
                "block_ids": [],
                "start_sec": None,
                "end_sec": None,
            },
        )
        ranges(entry, item)


def _sorted(values: dict[str, dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    items = list(values.values())
    items.sort(
        key=lambda item: (
            float(item.get("start_sec") or 0.0),
            str(item.get("canonical_name") or item.get("name") or item.get("raw_value") or ""),
        )
    )
    return items[:limit]


@register_step
class EntityExtractStep(BaseStep):
    type = "entities.extract"
    title = "Extract entities"
    description = (
        "Read context blocks and the edition script, resolve phonetic names, and "
        "write people, objects/locations/events, and metric manifests with "
        "timeline ranges."
    )
    status = "available"
    icon = "⌕"
    color = "#a78bfa"
    requires = ("transcribe",)
    produces = ("entities",)
    params_model = EntityExtractParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = EntityExtractParams.model_validate(params)
        blocks = _block_items(read_json_or(context.output / options.blocks_path, {}))
        script_path = context.output / options.script_path
        try:
            script = script_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            script = ""
        names = _script_names(script)
        for entity in options.known_entities:
            value = str(entity).strip()
            if value and value not in names:
                names.append(value)
        names.sort(key=len, reverse=True)
        if not names:
            names = _script_names("\n".join(str(item.get("text") or "") for item in blocks))
        people, objects, metrics = _deterministic_entities(blocks, names)
        object_hints = [
            *[_quoted.strip() for _quoted in _QUOTED.findall(script) if _quoted.strip()],
            *[str(item).strip() for item in options.known_entities if str(item).strip()],
        ]
        for phrase in object_hints:
            name = " ".join(phrase.split())
            if not name:
                continue
            entry = objects.setdefault(name.casefold(), _entry(name, kind="event"))
            for block in blocks:
                if name.casefold() in str(block.get("text") or "").casefold():
                    _add_block_range(entry, block)
                    break
        if io.llm_client is not None and blocks:
            prompt = (
                "Extract visually relevant entities from the transcript blocks. "
                "Use only facts present in the blocks and edition script. Return "
                'one JSON object: {"people":[{"canonical_name":"",'
                '"raw_mentions":[],"block_ids":[]}],'
                '"objects_locations_events":[{"name":"","kind":"object|location|event",'
                '"block_ids":[]}],'
                '"data_metrics":[{"raw_value":"","formatted_display":"",'
                '"chart_type":"kinetic_counter","block_ids":[]}]} . '
                "Resolve phonetically misspelled names against the edition script. "
                f"Language: {options.language}.\n\nBLOCKS:\n"
                + json.dumps(
                    [
                        {
                            "context_block_id": item.get("context_block_id"),
                            "start_sec": item.get("start_sec"),
                            "end_sec": item.get("end_sec"),
                            "text": item.get("text"),
                        }
                        for item in blocks
                    ],
                    ensure_ascii=False,
                )[:50000]
                + "\n\nEDITION SCRIPT:\n"
                + script[:30000]
            )
            try:
                payload = io.llm_client.complete_json(prompt, "videoflow.entities")
                if isinstance(payload, dict):
                    _merge_model_entities(
                        people,
                        objects,
                        metrics,
                        payload,
                        {
                            str(item.get("context_block_id")): item
                            for item in blocks
                        },
                        names,
                    )
            except Exception as exc:  # noqa: BLE001 - deterministic pass remains
                context.warnings.append(f"Entity model fallback: {exc}")
        result = {
            "people": _sorted(people, options.max_entities),
            "objects_locations_events": _sorted(objects, options.max_entities),
            "data_metrics": _sorted(metrics, options.max_entities),
        }
        result["counts"] = {
            "people": len(result["people"]),
            "objects_locations_events": len(result["objects_locations_events"]),
            "data_metrics": len(result["data_metrics"]),
        }
        json_path = context.output / "narrative" / "entities.json"
        markdown_path = context.output / "narrative" / "entities.md"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        lines = ["# Entity manifest", ""]
        for title, key in (
            ("People", "people"),
            ("Objects, locations, and events", "objects_locations_events"),
            ("Data metrics", "data_metrics"),
        ):
            lines.extend([f"## {title}", ""])
            for item in result[key]:
                name = (
                    item.get("canonical_name")
                    or item.get("name")
                    or item.get("raw_value")
                )
                start = item.get("start_sec")
                end = item.get("end_sec")
                lines.append(f"- `{name}` · {start}s → {end}s")
            lines.append("")
        markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        context.metadata["narrative_entities"] = result
        context.artifacts["narrative_entities"] = str(json_path)
        context.artifacts["narrative_entities_md"] = str(markdown_path)
        context.hashes["entities.extract"] = digest_payload(result["counts"])
        io.report(
            100,
            f"{result['counts']['people']} people, "
            f"{result['counts']['objects_locations_events']} objects/events, "
            f"{result['counts']['data_metrics']} metrics",
        )

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("narrative_entities", "narrative_entities_md")
            if context.artifacts.get(key)
        )


@register_step
class EntityApplyStep(BaseStep):
    type = "entities.apply"
    title = "Apply entity corrections"
    description = (
        "Apply human phonetic, name, object, and metric corrections to the "
        "narrative entity manifest and write a reviewable before/after report."
    )
    status = "available"
    icon = "✎"
    color = "#a78bfa"
    params_model = EntityApplyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = EntityApplyParams.model_validate(params)
        corrections = read_json_or(context.output / options.corrections_path, {})
        answers = corrections.get("answers", {}) if isinstance(corrections, dict) else {}
        mappings = _mappings(answers if isinstance(answers, dict) else {})
        manifest = read_json_or(context.output / options.narrative_path, {})
        if not manifest:
            manifest = context.metadata.get("narrative_entities", {})
        corrected = _replace(manifest, mappings)
        payload = {
            "corrections": mappings,
            "corrected_count": len(mappings),
            "manifest": corrected,
        }
        json_path = context.output / "narrative" / f"{options.output_stem}.json"
        markdown_path = context.output / "narrative" / f"{options.output_stem}.md"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(corrected, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        lines = ["# Entity corrections", ""]
        if mappings:
            for source, target in sorted(mappings.items()):
                lines.append(f"- `{source}` → `{target}`")
        else:
            lines.append("No corrections were supplied.")
        markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        context.metadata["entity_corrections"] = payload
        context.metadata["narrative_entities_corrected"] = corrected
        context.artifacts["entities_corrected"] = str(json_path)
        context.artifacts["entities_corrected_md"] = str(markdown_path)
        context.hashes["entities.apply"] = digest_payload(payload)
        io.report(100, f"{len(mappings)} entity correction(s) applied")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("entities_corrected", "entities_corrected_md")
            if context.artifacts.get(key)
        )
