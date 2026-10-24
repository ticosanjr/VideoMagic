"""Asset intelligence: shots, semantic matching, beats, and SFX planning."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.assets import list_assets
from videoflow.application.audio_analysis import detect_beats
from videoflow.application.video_analysis import detect_scene_changes, scene_intervals
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import require_media
from videoflow.steps.registry import register_step


def _terms(text: str) -> set[str]:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {item for item in cleaned.split() if len(item) > 3}


def _overlap(left: str, right: str) -> float:
    a = _terms(left)
    b = _terms(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _tfidf_scores(query: str, documents: list[str]) -> list[float]:
    query_terms = _terms(query)
    tokenized = [_terms(document) for document in documents]
    count = len(tokenized)
    df: dict[str, int] = {}
    for tokens in tokenized:
        for token in tokens:
            df[token] = df.get(token, 0) + 1
    idf = {token: math.log((count + 1) / (freq + 1)) + 1.0 for token, freq in df.items()}
    query_vector = {token: idf.get(token, 1.0) for token in query_terms}
    query_norm = math.sqrt(sum(value * value for value in query_vector.values())) or 1.0
    scores: list[float] = []
    for tokens in tokenized:
        doc_vector = {token: idf.get(token, 1.0) for token in tokens}
        doc_norm = math.sqrt(sum(value * value for value in doc_vector.values())) or 1.0
        dot = sum(query_vector.get(token, 0.0) * value for token, value in doc_vector.items())
        scores.append(dot / (query_norm * doc_norm))
    return scores


class ShotsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float = Field(default=0.35, ge=0.05, le=0.95)
    thumbnails: bool = True


@register_step
class ShotsStep(BaseStep):
    type = "assets.shots"
    title = "Detect shots"
    description = "Detect scene cuts and extract one thumbnail per shot."
    status = "available"
    icon = "▦"
    color = "#22c55e"
    requires = ("ingest",)
    produces = ("shots",)
    params_model = ShotsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ShotsParams.model_validate(params)
        media = require_media(context)
        spans = scene_intervals(
            detect_scene_changes(Path(context.source), threshold=options.threshold),
            sample_rate=media.audio_sample_rate,
        )
        directory = context.output / "shots"
        directory.mkdir(parents=True, exist_ok=True)
        shots: list[dict[str, Any]] = []
        for index, (start, end) in enumerate(spans or [(0, context.duration_samples())]):
            entry: dict[str, Any] = {
                "id": f"shot-{index + 1}",
                "start_sample": start,
                "end_sample": end,
            }
            if options.thumbnails:
                target = directory / f"{entry['id']}.png"
                try:
                    FFmpegAdapter().render_thumbnail(
                        Path(context.source),
                        target,
                        time_sec=((start + end) / 2) / max(1, media.audio_sample_rate),
                    )
                    entry["thumbnail"] = str(target)
                except Exception as exc:
                    context.warnings.append(f"Shot thumbnail failed: {exc}")
            shots.append(entry)
        target = context.output / "shots" / "shots.json"
        target.write_text(json.dumps({"shots": shots}, indent=2) + "\n", encoding="utf-8")
        context.artifacts["shots"] = str(target)
        context.metadata["scenes"] = shots
        io.report(100, f"{len(shots)} shot(s) detected")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("shots")
        return (Path(path),) if path else ()


class MatchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = ""
    max_per_short: int = Field(default=2, ge=1, le=5)
    min_score: float = Field(default=0.05, ge=0.0, le=1.0)


@register_step
class AssetMatchStep(BaseStep):
    type = "assets.match"
    title = "Match B-roll"
    description = "Match local assets to Shorts by semantic keyword overlap."
    status = "available"
    icon = "↔"
    color = "#f59e0b"
    requires = ("shorts.select",)
    produces = ("broll_matches",)
    params_model = MatchParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MatchParams.model_validate(params)
        assets = [
            item
            for item in list_assets(limit=2000)
            if item.get("kind") in {"video", "image"}
        ]
        plan: dict[str, list[dict[str, Any]]] = {}
        licenses: dict[str, dict[str, Any]] = {}
        documents = [
            f"{asset.get('name', '')} {' '.join(asset.get('tags', []))}"
            for asset in assets
        ]
        sentence_map = {sentence.id: sentence for sentence in context.transcript}
        sample_rate = (
            context.media.audio_sample_rate if context.media is not None else 48000
        )
        scenes = [
            (
                int(item.get("start_sample", 0)),
                int(item.get("end_sample", 0)),
                str(item.get("id", "")),
            )
            for item in context.metadata.get("scenes", [])
            if isinstance(item, dict)
        ]
        used: set[str] = set()
        for clip in context.selected_shorts:
            windows = self._windows(clip, scenes)
            entries = []
            for start, end, shot_id in windows:
                scene_text = " ".join(
                    sentence.text
                    for sentence in sentence_map.values()
                    if sentence.end_sample > start and sentence.start_sample < end
                )
                text = f"{clip.title} {scene_text} {options.query}".strip()
                scores = _tfidf_scores(text, documents)
                ranked = sorted(
                    zip(scores, assets, strict=False),
                    key=lambda item: item[0],
                    reverse=True,
                )
                for score, asset in ranked:
                    key = str(asset.get("id") or asset.get("path"))
                    if score < options.min_score or key in used:
                        continue
                    used.add(key)
                    relative_start = max(0.0, (start - clip.start_sample) / max(1, sample_rate))
                    entries.append(
                        {
                            "path": asset.get("path"),
                            "start_sec": round(relative_start, 3),
                            "duration_sec": round(min(5.0, (end - start) / max(1, sample_rate)), 3),
                            "provider": "local",
                            "license": asset.get("license", ""),
                            "attribution": str(asset.get("name") or ""),
                            "source_url": "",
                            "score": round(score, 4),
                            "shot_id": shot_id,
                        }
                    )
                    licenses[key] = {
                        "name": asset.get("name"),
                        "path": asset.get("path"),
                        "license": asset.get("license", ""),
                        "attribution": asset.get("name"),
                    }
                    break
                if len(entries) >= options.max_per_short:
                    break
            plan[clip.title] = entries
        context.metadata["broll_plan"] = plan
        context.metadata["broll_licenses"] = licenses
        context.output.mkdir(parents=True, exist_ok=True)
        target = context.output / "broll-matches.json"
        target.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        context.artifacts["broll_matches"] = str(target)
        license_target = context.output / "broll-licenses.json"
        license_target.write_text(
            json.dumps({"assets": licenses}, indent=2) + "\n", encoding="utf-8"
        )
        context.artifacts["broll_licenses"] = str(license_target)
        io.report(100, f"Matched B-roll for {len(plan)} Short(s)")

    @staticmethod
    def _windows(clip: Any, scenes: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
        """Return the shot windows covered by a clip, or one whole-clip window."""

        inside = [
            (start, end, shot_id)
            for start, end, shot_id in scenes
            if end > clip.start_sample and start < clip.end_sample
        ]
        if not inside:
            return [(clip.start_sample, clip.end_sample, "")]
        return [
            (max(start, clip.start_sample), min(end, clip.end_sample), shot_id)
            for start, end, shot_id in sorted(inside)
        ]

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("broll_matches")
        return (Path(path),) if path else ()


class BeatParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = ""
    tempo_bpm: float = Field(default=120.0, ge=40.0, le=220.0)


@register_step
class MusicBeatStep(BaseStep):
    type = "music.beat"
    title = "Music beats"
    description = "Write a deterministic beat grid for music/SFX placement."
    status = "available"
    icon = "♫"
    color = "#a78bfa"
    params_model = BeatParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = BeatParams.model_validate(params)
        duration = context.duration_samples() / (
            context.media.audio_sample_rate if context.media is not None else 48000
        )
        beats: list[float] = []
        source = "tempo"
        if options.path:
            try:
                beats = detect_beats(Path(options.path).expanduser())
                source = "audio"
            except Exception as exc:
                context.warnings.append(f"Beat detection fell back to tempo: {exc}")
        bpm = options.tempo_bpm
        if len(beats) > 1:
            intervals = [b - a for a, b in zip(beats, beats[1:], strict=False) if b > a]
            if intervals:
                bpm = round(60.0 / (sum(intervals) / len(intervals)), 2)
        if not beats:
            interval = 60.0 / options.tempo_bpm
            current = 0.0
            while current < duration:
                beats.append(round(current, 3))
                current += interval
        target = context.output / "music" / "beats.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"tempo_bpm": bpm, "source": source, "beats": beats}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["beats"] = str(target)
        context.metadata["beats"] = beats
        io.report(100, f"{len(beats)} beat(s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("beats")
        return (Path(path),) if path else ()


class SfxParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directory: str = ""
    max_per_short: int = Field(default=1, ge=1, le=5)


@register_step
class SfxPlanStep(BaseStep):
    type = "sfx.plan"
    title = "SFX plan"
    description = "Assign local sound effects to Short starts or beats."
    status = "available"
    icon = "♪"
    color = "#f59e0b"
    params_model = SfxParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SfxParams.model_validate(params)
        directory = (
            Path(options.directory).expanduser()
            if options.directory
            else context.output.parent / "sfx"
        )
        files = (
            sorted(directory.glob("*.wav")) + sorted(directory.glob("*.mp3"))
            if directory.is_dir()
            else []
        )
        plan: dict[str, list[dict[str, Any]]] = {}
        for index, clip in enumerate(context.selected_shorts):
            entries = []
            for offset in range(min(options.max_per_short, len(files))):
                path = files[(index + offset) % len(files)]
                entries.append({"path": str(path), "start_sec": 0.0, "kind": "sfx"})
            plan[clip.title] = entries
        target = context.output / "sfx" / "plan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        context.artifacts["sfx_plan"] = str(target)
        context.metadata["sfx_plan"] = plan
        io.report(100, f"{sum(len(v) for v in plan.values())} SFX cue(s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("sfx_plan")
        return (Path(path),) if path else ()
