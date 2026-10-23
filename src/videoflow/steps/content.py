"""Content-cycle steps.

Implemented steps do real work. Planned steps are intentionally no-ops; the
runner marks them as skipped so a recipe can model the full workflow without
pretending a missing engine ran.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.audio import audio_filters
from videoflow.application.titles import render_titles_ass
from videoflow.core.context import PipelineContext
from videoflow.domain.config import AudioEnhanceConfig
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, EmptyParams, StepIO
from videoflow.steps.registry import register_step


class _BypassStep(BaseStep):
    status = "planned"
    icon = "○"
    color = "#71717a"
    params_model = EmptyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        io.report(100, "Bypassed")


@register_step
class IdeaStep(_BypassStep):
    type = "content.idea"
    title = "Idea / angle"
    description = "Planned: topic, hook, audience, and angle selection."
    icon = "✦"


@register_step
class ResearchStep(_BypassStep):
    type = "content.research"
    title = "Research / references"
    description = "Planned: trend, keyword, competitor, and source research."
    icon = "⌕"


@register_step
class ScriptStep(_BypassStep):
    type = "content.script"
    title = "Script / outline"
    description = "Planned: outline, script, hook variants, and CTA."
    icon = "✎"


@register_step
class StoryboardStep(BaseStep):
    type = "storyboard.plan"
    title = "Storyboard / shot list"
    description = "Write a JSON storyboard from the validated timeline and transcript."
    status = "available"
    icon = "▤"
    color = "#22c55e"
    requires = ("edit.timeline",)
    params_model = EmptyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        if context.state is None:
            raise IngestError("Storyboard requires a validated timeline.")
        media = context.media
        fps = (media.fps_num / media.fps_den) if media is not None else 30.0
        state = context.state
        payload = {
            "ok": True,
            "duration_sec": round(
                max((clip.timeline_out_frame for clip in state.video_segments), default=0)
                / max(0.001, fps),
                3,
            ),
            "scenes": [
                {
                    "id": clip.clip_id,
                    "start_sec": round(clip.timeline_in_frame / fps, 3),
                    "end_sec": round(clip.timeline_out_frame / fps, 3),
                    "transition": clip.transition_out.type if clip.transition_out else None,
                    "keyframes": len(clip.transform.keyframes),
                }
                for clip in state.video_segments
            ],
            "captions": [
                {
                    "id": sentence.id,
                    "text": sentence.text,
                    "speaker": sentence.speaker,
                }
                for sentence in state.transcript
            ],
            "shorts": list(context.shorts),
            "broll_plan": context.metadata.get("broll_plan", {}),
        }
        context.output.mkdir(parents=True, exist_ok=True)
        target = context.output / "storyboard.json"
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["storyboard"] = str(target)
        io.report(100, "Storyboard ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("storyboard")
        return (Path(path),) if path else ()


class AssetIndexParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_dir: str = ""
    tags: list[str] = Field(default_factory=list)


@register_step
class AssetIndexStep(BaseStep):
    type = "assets.index"
    title = "Index assets"
    description = "Scan a local folder into the asset library index."
    status = "available"
    icon = "▦"
    color = "#22c55e"
    params_model = AssetIndexParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AssetIndexParams.model_validate(params)
        if not options.asset_dir:
            io.report(100, "Asset indexing skipped")
            return
        from videoflow.application.assets import scan_directory

        records = scan_directory(Path(options.asset_dir), tags=options.tags)
        target = context.output / "assets-index.json"
        target.write_text(
            json.dumps({"ok": True, "assets": records}, indent=2) + "\n",
            encoding="utf-8",
        )
        context.metadata["assets_index"] = records
        context.artifacts["assets_index"] = str(target)
        io.report(100, f"Indexed {len(records)} assets")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("assets_index")
        return (Path(path),) if path else ()


class AudioMasterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    highpass_hz: int = Field(default=80, ge=20, le=500)
    denoise: bool = True
    denoise_db: int = Field(default=12, ge=0, le=40)
    noise_floor_db: int = Field(default=-30, ge=-80, le=0)
    loudnorm: bool = True
    target_lufs: float = Field(default=-16.0, ge=-30.0, le=-5.0)
    true_peak_db: float = Field(default=-1.5, ge=-9.0, le=0.0)
    sample_rate: int = Field(default=48000, ge=8000, le=192000)


@register_step
class AudioMasterStep(BaseStep):
    type = "audio.master"
    title = "Audio master"
    description = "High-pass, denoise, and normalise the dialogue bed with EBU R128 loudness."
    status = "available"
    icon = "♫"
    color = "#a78bfa"
    requires = ("ingest",)
    produces = ("audio_master",)
    params_model = AudioMasterParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AudioMasterParams.model_validate(params)
        if context.media is None:
            raise IngestError("Audio master requires ingested media.")
        filters = audio_filters(
            AudioEnhanceConfig(
                enabled=True,
                highpass_hz=options.highpass_hz,
                denoise=options.denoise,
                denoise_db=options.denoise_db,
                noise_floor_db=options.noise_floor_db,
                loudnorm=options.loudnorm,
                target_lufs=options.target_lufs,
                true_peak_db=options.true_peak_db,
            )
        )
        target = context.output / "audio" / "master.wav"
        FFmpegAdapter().master_audio(
            context.source,
            target,
            filters=filters,
            sample_rate=options.sample_rate,
        )
        context.artifacts["audio_master"] = str(target)
        context.metadata["audio_master_filters"] = filters
        filters_path = context.output / "audio" / "master-filters.json"
        filters_path.write_text(
            json.dumps({"filters": filters}, indent=2) + "\n", encoding="utf-8"
        )
        context.artifacts["audio_master_filters"] = str(filters_path)
        io.report(100, "Audio master ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("audio_master")
        return (Path(path),) if path else ()


class AudioQaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_lufs: float = Field(default=-16.0, ge=-30.0, le=-5.0)
    tolerance_lu: float = Field(default=2.0, ge=0.0, le=10.0)
    max_true_peak_db: float = Field(default=-1.0, ge=-20.0, le=0.0)


@register_step
class AudioQaStep(BaseStep):
    type = "audio.qa"
    title = "Audio QA"
    description = "Measure EBU R128 integrated loudness and true peak for delivery."
    status = "available"
    icon = "◉"
    color = "#22c55e"
    requires = ("ingest",)
    produces = ("audio_qa",)
    params_model = AudioQaParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AudioQaParams.model_validate(params)
        master = context.artifacts.get("audio_master")
        source = Path(master) if master else Path(context.source)
        measurement = FFmpegAdapter().measure_loudness(source)
        lufs = float(measurement["integrated_lufs"])
        peak = float(measurement["true_peak_dbfs"])
        passed = (
            abs(lufs - options.target_lufs) <= options.tolerance_lu
            and peak <= options.max_true_peak_db
        )
        payload = {
            "ok": True,
            "source": str(source),
            "integrated_lufs": lufs,
            "true_peak_dbfs": peak,
            "target_lufs": options.target_lufs,
            "max_true_peak_db": options.max_true_peak_db,
            "passed": passed,
        }
        target = context.output / "audio" / "qa.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["audio_qa"] = str(target)
        context.metadata["audio_qa"] = payload
        if not passed:
            context.warnings.append(
                f"Audio QA out of spec: {lufs:.1f} LUFS, peak {peak:.1f} dBFS"
            )
        io.report(100, f"{lufs:.1f} LUFS · peak {peak:.1f} dBFS")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("audio_qa")
        return (Path(path),) if path else ()


class ColorGradeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lut_path: str = ""
    brightness: float = Field(default=0.0, ge=-1.0, le=1.0)
    contrast: float = Field(default=1.0, ge=0.1, le=4.0)
    saturation: float = Field(default=1.0, ge=0.0, le=4.0)
    gamma: float = Field(default=1.0, ge=0.1, le=4.0)


@register_step
class ColorGradeStep(BaseStep):
    type = "color.grade"
    title = "Color / LUT"
    description = "Apply a .cube LUT and deterministic eq grade to the MP4 preview/render."
    status = "available"
    icon = "◐"
    color = "#22c55e"
    produces = ("color_grade",)
    params_model = ColorGradeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ColorGradeParams.model_validate(params)
        filters: list[str] = []
        lut = Path(options.lut_path).expanduser() if options.lut_path else None
        if lut is not None:
            if not lut.is_file():
                raise IngestError(f"LUT does not exist: {lut}")
            escaped = str(lut).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            filters.append(f"lut3d='{escaped}'")
        if (
            options.brightness != 0.0
            or options.contrast != 1.0
            or options.saturation != 1.0
            or options.gamma != 1.0
        ):
            filters.append(
                "eq="
                f"brightness={options.brightness}:"
                f"contrast={options.contrast}:"
                f"saturation={options.saturation}:"
                f"gamma={options.gamma}"
            )
        target = context.output / "color" / "filters.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"filters": filters, "lut": str(lut) if lut else ""}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["color_filters"] = str(target)
        context.metadata["color_filters"] = filters
        io.report(100, f"{len(filters)} color filter(s) planned")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("color_filters")
        return (Path(path),) if path else ()


class TitlesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_lower_thirds: int = Field(default=40, ge=1, le=500)
    intro_title: str = ""
    outro_title: str = ""


@register_step
class TitlesStep(BaseStep):
    type = "titles.plan"
    title = "Titles / graphics"
    description = "Plan title cards and speaker lower thirds from the timeline and Shorts."
    status = "available"
    icon = "T"
    color = "#22c55e"
    requires = ("edit.timeline",)
    produces = ("titles",)
    params_model = TitlesParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TitlesParams.model_validate(params)
        if context.state is None:
            raise IngestError("Titles require a validated timeline.")
        media = context.media
        fps = (media.fps_num / media.fps_den) if media is not None else 30.0
        transcript = context.state.transcript
        rate = media.audio_sample_rate if media is not None else 48000
        lower_thirds: list[dict[str, object]] = []
        previous_speaker: int | None = None
        for sentence in transcript:
            if sentence.speaker == previous_speaker:
                continue
            previous_speaker = sentence.speaker
            lower_thirds.append(
                {
                    "start_sec": round(sentence.start_sample / max(1, rate), 3),
                    "end_sec": round(
                        min(
                            sentence.end_sample / max(1, rate),
                            sentence.start_sample / max(1, rate) + 3.0,
                        ),
                        3,
                    ),
                    "speaker": sentence.speaker,
                    "text": f"Speaker {sentence.speaker + 1}",
                }
            )
            if len(lower_thirds) >= options.max_lower_thirds:
                break
        title_cards: list[dict[str, object]] = []
        if options.intro_title:
            title_cards.append(
                {
                    "kind": "intro",
                    "start_sec": 0.0,
                    "duration_sec": 2.0,
                    "text": options.intro_title,
                }
            )
        for index, short in enumerate(context.shorts):
            title_cards.append(
                {
                    "kind": "short",
                    "index": index,
                    "text": str(short.get("title") or f"Short {index + 1}"),
                }
            )
        if options.outro_title:
            duration = max(
                (clip.timeline_out_frame for clip in context.state.video_segments),
                default=0,
            ) / max(0.001, fps)
            title_cards.append(
                {
                    "kind": "outro",
                    "start_sec": round(max(0.0, duration - 2.0), 3),
                    "duration_sec": 2.0,
                    "text": options.outro_title,
                }
            )
        payload = {
            "ok": True,
            "lower_thirds": lower_thirds,
            "title_cards": title_cards,
        }
        target = context.output / "titles.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["titles"] = str(target)
        media = context.media
        ass_path = render_titles_ass(
            payload,
            context.output / "titles.ass",
            width=media.width if media is not None else 1920,
            height=media.height if media is not None else 1080,
        )
        context.artifacts["titles_ass"] = str(ass_path)
        context.metadata["titles"] = payload
        io.report(100, f"{len(lower_thirds)} lower third(s), {len(title_cards)} title card(s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("titles")
        return (Path(path),) if path else ()


class ThumbnailParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants: int = Field(default=1, ge=1, le=5)
    title: str = ""


@register_step
class ThumbnailStep(BaseStep):
    type = "thumbnail.generate"
    title = "Thumbnail / cover"
    description = "Render one or more thumbnail candidates from the source."
    status = "available"
    icon = "▣"
    color = "#22c55e"
    requires = ("ingest",)
    params_model = ThumbnailParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ThumbnailParams.model_validate(params)
        if context.media is None:
            raise IngestError("Thumbnail requires ingested media.")
        duration = (
            context.media.duration_frames
            * context.media.fps_den
            / max(1, context.media.fps_num)
        )
        fractions = [0.5, 0.35, 0.65, 0.2, 0.8]
        targets: list[str] = []
        adapter = FFmpegAdapter()
        for index in range(options.variants):
            target = context.output / "thumbnails" / f"thumbnail-{index + 1}.png"
            adapter.render_thumbnail(
                Path(context.source),
                target,
                time_sec=max(0.0, duration * fractions[index % len(fractions)]),
            )
            targets.append(str(target))
            context.artifacts[f"thumbnail_{index + 1}"] = str(target)
            io.report(
                int((index + 1) / options.variants * 100),
                f"Thumbnail {index + 1}/{options.variants}",
            )
        context.artifacts["thumbnail"] = targets[0]
        context.metadata["thumbnails"] = targets
        if options.title:
            context.metadata["thumbnail_title"] = options.title

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        paths = [Path(path) for path in context.metadata.get("thumbnails", [])]
        return tuple(paths)


@register_step
class PublishStep(_BypassStep):
    type = "publish.webhook"
    title = "Publish / webhook"
    description = "Planned: scheduled delivery and webhook publishing."
    icon = "↗"


class AnalyticsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv_path: str = ""


@register_step
class AnalyticsStep(BaseStep):
    type = "analytics.import"
    title = "Analytics / feedback"
    description = "Import retention/CTR metrics from CSV into a normalized JSON report."
    status = "available"
    icon = "▥"
    color = "#22c55e"
    params_model = AnalyticsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AnalyticsParams.model_validate(params)
        rows: list[dict[str, str]] = []
        if options.csv_path:
            path = Path(options.csv_path).expanduser()
            if not path.is_file():
                raise IngestError(f"Analytics CSV does not exist: {path}")
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = [dict(row) for row in csv.DictReader(handle)]
        columns = sorted({key for row in rows for key in row})
        numeric: dict[str, float] = {}
        for column in columns:
            values: list[float] = []
            for row in rows:
                try:
                    values.append(float(str(row.get(column, "")).strip()))
                except ValueError:
                    continue
            if values and len(values) == len(rows):
                numeric[column] = round(sum(values) / len(values), 4)
        payload = {
            "ok": True,
            "source": options.csv_path,
            "row_count": len(rows),
            "columns": columns,
            "averages": numeric,
            "rows": rows[:500],
        }
        target = context.output / "analytics.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["analytics"] = str(target)
        context.metadata["analytics"] = payload
        io.report(100, f"Imported {len(rows)} analytics row(s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("analytics")
        return (Path(path),) if path else ()


@register_step
class ReviewStep(BaseStep):
    type = "review.queue"
    title = "Review / approval"
    description = "Write a deterministic review checklist for the current run."
    status = "available"
    icon = "✓"
    color = "#22c55e"
    params_model = EmptyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        state = context.state
        checks = [
            {
                "id": "timeline",
                "label": "Timeline has picture and dialogue",
                "ok": bool(state and state.video_segments and state.audio_segments),
            },
            {
                "id": "captions",
                "label": "Transcript is present",
                "ok": bool(context.transcript or (state and state.transcript)),
            },
            {
                "id": "shorts",
                "label": "At least one Short was selected",
                "ok": bool(context.shorts),
            },
            {
                "id": "thumbnail",
                "label": "Thumbnail candidate exists",
                "ok": "thumbnail" in context.artifacts,
            },
            {
                "id": "audio_master",
                "label": "Audio master exists",
                "ok": "audio_master" in context.artifacts,
            },
            {
                "id": "titles",
                "label": "Title plan exists",
                "ok": "titles" in context.artifacts,
            },
        ]
        payload = {
            "ok": True,
            "approved": False,
            "checks": checks,
            "pending": [check["id"] for check in checks if not check["ok"]],
        }
        target = context.output / "review.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["review"] = str(target)
        context.metadata["review"] = payload
        io.report(100, f"{len(checks) - len(payload['pending'])}/{len(checks)} checks ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("review")
        return (Path(path),) if path else ()
