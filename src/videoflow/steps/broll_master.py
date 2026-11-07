"""Entity-matched B-roll planning for the long-form master timeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.assets import list_assets
from videoflow.application.broll_providers import LocalBrollProvider
from videoflow.core.context import PipelineContext
from videoflow.steps.assets_intel import _tfidf_scores
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class BrollMasterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["local"] = "local"
    asset_dir: str = ""
    max_per_block: int = Field(default=2, ge=1, le=5)
    min_score: float = Field(default=0.05, ge=0.0, le=1.0)
    duration_sec: float = Field(default=3.0, gt=0.0, le=30.0)
    query: str = ""


def _fallback_blocks(context: PipelineContext) -> list[dict[str, Any]]:
    rate = (
        context.media.audio_sample_rate if context.media is not None else 48_000
    )
    sentences = context.transcript
    if not sentences:
        return []
    blocks: list[dict[str, Any]] = []
    current = []
    words = 0
    for sentence in sentences:
        current.append(sentence)
        words += len(sentence.text.split())
        if words >= 100:
            blocks.append(
                {
                    "context_block_id": f"block_{len(blocks) + 1:03d}",
                    "start_sample": min(item.start_sample for item in current),
                    "end_sample": max(item.end_sample for item in current),
                    "start_sec": round(
                        min(item.start_sample for item in current) / rate, 3
                    ),
                    "end_sec": round(
                        max(item.end_sample for item in current) / rate, 3
                    ),
                    "text": " ".join(item.text for item in current),
                    "extracted_entities": {},
                }
            )
            current = []
            words = 0
    if current:
        blocks.append(
            {
                "context_block_id": f"block_{len(blocks) + 1:03d}",
                "start_sample": min(item.start_sample for item in current),
                "end_sample": max(item.end_sample for item in current),
                "start_sec": round(min(item.start_sample for item in current) / rate, 3),
                "end_sec": round(max(item.end_sample for item in current) / rate, 3),
                "text": " ".join(item.text for item in current),
                "extracted_entities": {},
            }
        )
    return blocks


@register_step
class BrollMasterStep(BaseStep):
    type = "broll.plan_master"
    title = "B-roll plan (master)"
    description = (
        "Match local assets to narrative context blocks and write a long-form "
        "B-roll plan for the timeline sidecars."
    )
    status = "available"
    icon = "▦"
    color = "#f59e0b"
    requires = ("edit.timeline",)
    produces = ("broll_plan",)
    params_model = BrollMasterParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = BrollMasterParams.model_validate(params)
        blocks = list(context.metadata.get("narrative_beats") or [])
        if not blocks:
            blocks = _fallback_blocks(context)
        assets: list[dict[str, Any]] = []
        if options.asset_dir:
            try:
                provider = LocalBrollProvider(Path(options.asset_dir))
                assets = [
                    {
                        "path": str(asset.path),
                        "name": Path(str(asset.path)).stem,
                        "tags": [],
                        "license": asset.license,
                    }
                    for asset in provider.search("", limit=2000)
                    if asset.path is not None
                ]
            except Exception as exc:  # noqa: BLE001 - keep the plan empty
                context.warnings.append(f"Master B-roll assets unavailable: {exc}")
        if not assets:
            assets = [
                item
                for item in list_assets(limit=2000)
                if item.get("kind") in {"video", "image"}
            ]
        documents = [
            f"{item.get('name', '')} {' '.join(item.get('tags', []))}"
            for item in assets
        ]
        used: set[str] = set()
        plan: dict[str, list[dict[str, Any]]] = {}
        for block in blocks:
            block_id = str(block.get("context_block_id", ""))
            query = f"{block.get('text', '')} {options.query}".strip()
            entries: list[dict[str, Any]] = []
            if assets and documents:
                scores = _tfidf_scores(query, documents)
                ranked = sorted(
                    zip(scores, assets, strict=False),
                    key=lambda item: item[0],
                    reverse=True,
                )
                for score, asset in ranked:
                    key = str(asset.get("path") or asset.get("id") or "")
                    if key in used or score < options.min_score:
                        continue
                    used.add(key)
                    entries.append(
                        {
                            "path": asset.get("path"),
                            "start_sec": block.get("start_sec", 0.0),
                            "duration_sec": options.duration_sec,
                            "provider": "local",
                            "license": asset.get("license", ""),
                            "attribution": str(asset.get("name") or ""),
                            "score": round(float(score), 4),
                            "context_block_id": block_id,
                        }
                    )
                    if len(entries) >= options.max_per_block:
                        break
            plan[block_id] = entries
        directory = context.output / "broll"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "broll-master.json"
        target.write_text(
            json.dumps({"blocks": plan}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        # Export sidecars read broll.json; keep a flat list there as well.
        (context.output / "broll.json").write_text(
            json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        context.metadata["broll_plan"] = plan
        context.artifacts["broll_plan"] = str(target)
        context.hashes["broll.plan_master"] = digest_payload(
            {"blocks": len(plan), "assets": len(assets)}
        )
        io.report(100, f"B-roll planned for {len(plan)} block(s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("broll_plan")
        return (Path(path),) if path else ()
