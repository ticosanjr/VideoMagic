"""Reverse-engineer a style preset from reference images or a video."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import StylePreset
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class StyleReverseParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    images: list[str] = Field(default_factory=list)
    reference_path: str = ""
    mode: str = Field(default="both", pattern="^(light|dark|both)$")
    palette_count: int = Field(default=6, ge=2, le=12)
    name: str = Field(default="reference", max_length=120)


@register_step
class StyleReverseStep(BaseStep):
    type = "style.reverse_engineer"
    status = "partial"
    icon = "🎨"
    color = "#8b5cf6"
    title = "Reverse-engineer style"
    description = "Extract palette, typography hints, and safe zones from references."
    requires = ()
    produces = ("style_preset",)
    params_model = StyleReverseParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = StyleReverseParams.model_validate(params)
        files = [Path(item).expanduser() for item in options.images]
        if options.reference_path:
            files.append(Path(options.reference_path).expanduser())
        palette: list[str] = []
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover
            Image = None  # type: ignore[assignment]
        if Image is not None:
            counter: Counter[tuple[int, int, int]] = Counter()
            for path in files:
                if not path.is_file():
                    continue
                try:
                    with Image.open(path) as image:
                        small = image.convert("RGB").resize((64, 64))
                        for count, color in small.getcolors(maxcolors=64 * 64) or []:
                            counter[tuple(color)] += count
                except OSError:
                    continue
            palette = [
                f"#{red:02x}{green:02x}{blue:02x}"
                for (red, green, blue), _ in counter.most_common(options.palette_count)
            ]
        safezones = {
            "reels": {"bottom": 0.18, "right": 0.14},
            "tiktok": {"bottom": 0.20, "right": 0.16},
            "shorts": {"bottom": 0.16, "right": 0.14},
        }
        preset = StylePreset(
            name=options.name,
            palette=palette,
            typography={"family": "", "weight": "bold", "case": "upper"},
            cut_rhythm={"mode": "reference", "min_cut_sec": 1.2, "max_cut_sec": 4.0},
            safe_zones=safezones,
            source=",".join(str(path) for path in files if path.is_file()),
        )
        path = context.work / "style_preset.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(preset.model_dump_json(indent=2) + "\n", encoding="utf-8")
        context.metadata["style_preset"] = preset.model_dump(mode="json")
        context.artifacts["style_preset"] = str(path)
        io.report(100, f"Style preset with {len(palette)} colour(s)")
