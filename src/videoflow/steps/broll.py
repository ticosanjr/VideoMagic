"""Plan local or stock B-roll overlays for selected Shorts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.broll_providers import (
    BrollAsset,
    LocalBrollProvider,
    PexelsBrollProvider,
)
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class BrollParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["local", "pexels"] = "local"
    asset_dir: str = ""
    api_key_env: str = "PEXELS_API_KEY"
    query: str = ""
    max_per_short: int = Field(default=1, ge=1, le=5)
    start_fraction: float = Field(default=0.2, ge=0.0, le=0.9)
    duration_sec: float = Field(default=2.0, gt=0.0, le=30.0)


@register_step
class BrollStep(BaseStep):
    type = "broll.plan"
    title = "B-roll plan"
    description = (
        "Assign local assets or Pexels stock clips to selected Shorts as full-frame cutaways."
    )
    requires = ("shorts.select",)
    produces = ("broll_plan",)
    params_model = BrollParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = BrollParams.model_validate(params)
        if not context.selected_shorts:
            io.report(100, "No Shorts selected")
            return
        provider = self._provider(options, context)
        if provider is None:
            context.metadata["broll_plan"] = {}
            io.report(100, "B-roll disabled")
            return
        plan: dict[str, list[dict[str, Any]]] = {}
        used: set[str] = set()
        total = max(1, len(context.selected_shorts))
        for index, clip in enumerate(context.selected_shorts):
            query = f"{clip.title} {options.query}".strip()
            try:
                candidates = provider.search(query, limit=options.max_per_short * 3)
            except Exception as exc:
                context.warnings.append(f"B-roll search failed for {clip.title}: {exc}")
                candidates = []
            chosen: list[BrollAsset] = []
            for asset in candidates:
                key = str(asset.path or asset.url)
                if key in used:
                    continue
                chosen.append(asset)
                used.add(key)
                if len(chosen) >= options.max_per_short:
                    break
            entries = []
            for offset, asset in enumerate(chosen):
                path = asset.path
                if path is None and asset.url:
                    suffix = Path(asset.url.split("?")[0]).suffix or ".mp4"
                    target = (
                        context.output
                        / "broll-cache"
                        / f"{clip.sentence_ids[0] if clip.sentence_ids else index}-{offset}{suffix}"
                    )
                    try:
                        path = provider.download(asset, target)
                    except Exception as exc:
                        context.warnings.append(f"B-roll download failed: {exc}")
                        continue
                if path is None:
                    continue
                entries.append(
                    {
                        "path": str(path),
                        "start_sec": round(
                            max(
                                0.0,
                                clip.duration_samples
                                / (context.media.audio_sample_rate if context.media else 48000)
                                * options.start_fraction,
                            )
                            + offset * options.duration_sec,
                            3,
                        ),
                        "duration_sec": options.duration_sec,
                        "provider": asset.provider,
                        "attribution": asset.attribution,
                        "license": asset.license,
                        "source_url": asset.source_url,
                    }
                )
            plan[clip.title] = entries
            io.report(int((index + 1) / total * 100), f"Planned B-roll {index + 1}/{total}")
        context.metadata["broll_plan"] = plan
        (context.output / "broll.json").write_text(
            json.dumps({"ok": True, "shorts": plan}, indent=2) + "\n",
            encoding="utf-8",
        )
        context.hashes["broll"] = digest_payload(plan)
        io.report(100, f"{sum(len(items) for items in plan.values())} B-roll overlays planned")

    def _provider(self, options: BrollParams, context: PipelineContext):
        if options.provider == "local":
            if not options.asset_dir:
                context.warnings.append("B-roll skipped: no local asset directory configured")
                return None
            return LocalBrollProvider(Path(options.asset_dir))
        api_key = os.environ.get(options.api_key_env, "")
        if not api_key:
            context.warnings.append(
                f"B-roll skipped: {options.api_key_env} is not set for the Pexels provider"
            )
            return None
        return PexelsBrollProvider(api_key)
