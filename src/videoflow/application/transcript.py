"""Normalise overlapping ASR segments into clean utterances.

Whisper often emits sliding windows: a segment may start with the tail of the
previous sentence and then repeat the passage from its beginning. Retake
grouping needs complete sentences, so we merge the word streams, remove the
duplicate overlap, and split on punctuation or long pauses.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from videoflow.domain.state import Sentence, WordTiming

_SENTENCE_END = re.compile(r"[.!?…]$")
_TOKEN = re.compile(r"[^\wÀ-ÿ]+", re.UNICODE)
_PUNCTUATION_PREFIX = ".,!?;:%)]}"
_OPEN_ENDINGS = ("(", "[", "{", "-", "/", "—")


def _normal(word: str) -> str:
    return _TOKEN.sub("", word.casefold())


def _pseudo_words(sentence: Sentence) -> list[WordTiming]:
    tokens = sentence.text.split()
    if not tokens:
        return []
    count = max(1, len(tokens))
    span = max(1, sentence.end_sample - sentence.start_sample)
    output: list[WordTiming] = []
    for index, token in enumerate(tokens):
        start = sentence.start_sample + round(span * index / count)
        end = sentence.start_sample + round(span * (index + 1) / count)
        output.append(
            WordTiming(
                word=token,
                start_sample=start,
                end_sample=max(start + 1, end),
                probability=0.5,
            )
        )
    return output


def _flatten(
    sentences: Sequence[Sentence],
    *,
    sample_rate: int = 48000,
    overlap_gap_seconds: float = 0.25,
    cuts: list[tuple[int, int]] | None = None,
) -> tuple[list[WordTiming], list[int]]:
    merged: list[WordTiming] = []
    origins: list[int] = []
    previous_end: int | None = None
    for sentence in sorted(sentences, key=lambda item: (item.start_sample, item.id)):
        words = list(sentence.words) or _pseudo_words(sentence)
        words = [word for word in words if word.word.strip()]
        if not words:
            continue
        source_ids = [sentence.id] * len(words)
        if (
            not merged
            or previous_end is None
            or (sentence.start_sample - previous_end) / sample_rate
            > overlap_gap_seconds
        ):
            merged.extend(words)
            origins.extend(source_ids)
            previous_end = sentence.end_sample
            continue
        limit = min(len(merged), len(words), 40)
        overlap = 0
        for size in range(limit, 0, -1):
            if [_normal(word.word) for word in merged[-size:]] == [
                _normal(word.word) for word in words[:size]
            ]:
                overlap = size
                break
        # Prefer the later occurrence. In a retake the second segment is the
        # final take; keeping the earlier words would leave the aborted audio
        # in a gap and repeat the phrase. Ordinary sliding-window overlap is
        # also safe here because the later segment carries the same words with
        # their true timings.
        if overlap:
            earlier_start = merged[-overlap].start_sample
            later_start = words[0].start_sample
            if cuts is not None and later_start > earlier_start:
                cuts.append((earlier_start, later_start))
        for index in range(overlap):
            existing = merged[-overlap + index]
            incoming = words[index]
            if _SENTENCE_END.search(existing.word) and not _SENTENCE_END.search(
                incoming.word
            ):
                words[index] = incoming.model_copy(
                    update={"word": existing.word}
                )
        if overlap:
            del merged[-overlap:]
            del origins[-overlap:]
        merged.extend(words)
        origins.extend(source_ids)
        previous_end = max(previous_end, sentence.end_sample)
    return merged, origins


def _join(words: Sequence[WordTiming]) -> str:
    text = ""
    for word in words:
        token = word.word.strip()
        if not token:
            continue
        if not text:
            text = token
        elif (
            token.startswith(tuple(_PUNCTUATION_PREFIX))
            or token in {"%", "..."}
            or text.endswith(_OPEN_ENDINGS)
        ):
            text += token
        else:
            text += " " + token
    return text.strip()


def normalize_transcript(
    sentences: Sequence[Sentence],
    *,
    sample_rate: int = 48000,
    pause_seconds: float = 1.2,
    cuts: list[tuple[int, int]] | None = None,
    boundary_ids: set[int] | None = None,
) -> list[Sentence]:
    """Return complete, non-overlapping sentences with word timings.

    ``cuts`` receives source ranges where an earlier occurrence of an overlap
    was replaced by the later take. The timeline removes those ranges, so the
    aborted phrase does not survive as a high-energy "unknown" gap.

    ``boundary_ids`` are sentences already discarded by a human. A normalized
    sentence keeps the id of its first source sentence, and a boundary is never
    crossed while merging: a discarded take cannot absorb the next good take
    (or be renumbered into its id).
    """

    merged, origins = _flatten(sentences, sample_rate=sample_rate, cuts=cuts)
    if not merged:
        return []
    boundaries = set(boundary_ids or ())
    minimum_words = 4
    output: list[Sentence] = []
    current: list[WordTiming] = []
    current_origins: list[int] = []
    used: set[int] = set()
    next_id = max((sentence.id for sentence in sentences), default=-1) + 1

    def flush() -> None:
        nonlocal current, current_origins, next_id
        if not current:
            return
        text = _join(current)
        if text:
            preferred = current_origins[0]
            if preferred in used:
                preferred = next_id
                next_id += 1
            used.add(preferred)
            output.append(
                Sentence(
                    id=preferred,
                    start_sample=current[0].start_sample,
                    end_sample=current[-1].end_sample,
                    text=text,
                    words=list(current),
                )
            )
        current = []
        current_origins = []

    for index, word in enumerate(merged):
        origin = origins[index]
        if current_origins and (
            (current_origins[-1] in boundaries) != (origin in boundaries)
        ):
            flush()
        current.append(word)
        current_origins.append(origin)
        next_gap = 0.0
        next_word = ""
        if index + 1 < len(merged):
            next_gap = (
                merged[index + 1].start_sample - word.end_sample
            ) / sample_rate
            next_word = merged[index + 1].word.lstrip("\"'“‘([ ")
        ends = bool(_SENTENCE_END.search(word.word))
        pauses = (
            next_gap >= pause_seconds
            and len(current) >= minimum_words
            and bool(next_word[:1].isupper())
        )
        if (ends or pauses) and current_origins[0] not in boundaries:
            flush()
    flush()
    return output


def _load_scene_manifest(state: Any, project_dir: Path | None = None) -> Any:
    from videoflow.domain.scenes import ScenesManifest

    for payload in (
        state.pipeline.metadata.get("scenes_manifest"),
        None,
    ):
        if isinstance(payload, dict):
            try:
                return ScenesManifest.model_validate(payload)
            except ValueError:
                pass
    artifact = str(state.pipeline.artifacts.get("scenes_manifest") or "")
    candidates: list[Path] = []
    if artifact:
        candidate = Path(artifact).expanduser()
        if not candidate.is_absolute() and project_dir is not None:
            candidate = project_dir / candidate
        candidates.append(candidate)
    if project_dir is not None and project_dir.is_dir():
        candidates.extend(
            sorted(
                project_dir.rglob("scenes_manifest.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return ScenesManifest.model_validate(payload)
        except (OSError, ValueError):
            continue
    return None


def build_editorial_map(
    state: Any,
    *,
    project_dir: str | Path = "",
) -> dict[str, Any]:
    """Return 15–30 s edited-timeline blocks with speech, layout, and keyframe."""

    from videoflow.application.time_map import (
        TimeMapError,
        source_range_to_timeline,
        timeline_to_source_sec,
    )

    media = state.media_info
    rate = media.audio_sample_rate if media is not None else 48_000
    discarded = set(state.pipeline.discard_sentence_ids)
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for sentence in sorted(state.transcript, key=lambda item: (item.start_sample, item.id)):
        if sentence.id in discarded:
            continue
        start = sentence.start_sample / max(1, rate)
        end = sentence.end_sample / max(1, rate)
        try:
            ranges = source_range_to_timeline(state, start, end)
        except (TimeMapError, ValueError):
            continue
        if not ranges:
            continue
        items.append(
            {
                "sentence_id": sentence.id,
                "text": sentence.text,
                "edited_start_sec": min(item[0] for item in ranges),
                "edited_end_sec": max(item[1] for item in ranges),
            }
        )
    items.sort(key=lambda item: (item["edited_start_sec"], item["sentence_id"]))
    blocks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in items:
        if not current:
            current = [item]
            continue
        if item["edited_end_sec"] - current[0]["edited_start_sec"] <= 30.0:
            current.append(item)
        else:
            blocks.append(current)
            current = [item]
    if current:
        blocks.append(current)

    root = Path(project_dir).expanduser() if str(project_dir or "").strip() else None
    manifest = _load_scene_manifest(state, root)
    if manifest is None:
        warnings.append("scenes_manifest missing; layout is UNKNOWN and B-roll is blocked.")
    scenes = list(getattr(manifest, "scenes", []) or [])
    result: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        start = round(min(item["edited_start_sec"] for item in block), 3)
        end = round(max(item["edited_end_sec"] for item in block), 3)
        layout = "UNKNOWN"
        protected = True
        scene_id = ""
        keyframe_path = ""
        hints: list[str] = []
        if scenes:
            try:
                source_mid = timeline_to_source_sec(state, (start + end) / 2)
            except (TimeMapError, ValueError):
                source_mid = None
            if source_mid is not None:
                scene = next(
                    (
                        item
                        for item in scenes
                        if item.start_sec <= source_mid <= item.end_sec
                    ),
                    None,
                )
                if scene is not None:
                    layout = scene.layout_type
                    scene_id = scene.scene_id
                    keyframe_path = scene.keyframe_path
                    hints = list(scene.editing_hints)
                    protected = layout in {
                        "SCREEN_SHARE_PIP",
                        "SCREEN_SHARE_FULL",
                        "DUAL_CANVAS_OBS",
                    } or "PROTECT_FROM_BROLL" in hints
        result.append(
            {
                "block_id": f"EM_{index:04d}",
                "edited_start_sec": start,
                "edited_end_sec": end,
                "duration_sec": round(max(0.0, end - start), 3),
                "text": " ".join(item["text"].strip() for item in block if item["text"].strip()),
                "sentence_ids": [item["sentence_id"] for item in block],
                "layout_type": layout,
                "scene_id": scene_id,
                "protected_from_broll": protected,
                "editing_hints": hints,
                "keyframe_path": keyframe_path,
            }
        )
    return {
        "ok": True,
        "count": len(result),
        "blocks": result,
        "warnings": warnings,
        "time_basis": "edited",
    }
