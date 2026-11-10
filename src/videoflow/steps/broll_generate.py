"""Generate synthetic B-roll images and register them for matching."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.asset_providers import (
    AssetCandidate,
    read_ledger,
    write_ledger_from_payload,
)
from videoflow.application.assets import scan_directory
from videoflow.application.image_gen import generate_image
from videoflow.application.images import images_dir, save_image
from videoflow.application.secrets import get_secret
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class GenerateBrollParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai_compatible"] = "openai_compatible"
    base_url: str = ""
    model: str = "flux1-schnell"
    api_key_env: str = "VIDEOFLOW_IMAGE_API_KEY"
    prompt: str = ""
    negative_prompt: str = ""
    count: int = Field(default=1, ge=1, le=5)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    seed: int | None = None
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=lambda: ["generated", "b-roll"])


def _prompt_for(context: PipelineContext, explicit: str) -> str:
    if explicit.strip():
        return explicit.strip()
    titles = [clip.title for clip in context.selected_shorts]
    entities: list[str] = []
    beats = context.metadata.get("narrative_beats") or []
    if isinstance(beats, list):
        for block in beats[:4]:
            if not isinstance(block, dict):
                continue
            extracted = block.get("extracted_entities") or {}
            if not isinstance(extracted, dict):
                continue
            for key in ("people", "physical_objects", "locations"):
                for item in extracted.get(key) or []:
                    if not isinstance(item, dict):
                        continue
                    value = (
                        item.get("canonical_name")
                        or item.get("raw_mention")
                        or item.get("object")
                        or item.get("location_name")
                    )
                    if value:
                        entities.append(str(value))
    subject = ", ".join(dict.fromkeys([*titles, *entities])) or "editorial b-roll"
    return f"cinematic editorial b-roll of {subject}, clean composition, natural light"


@register_step
class GenerateBrollStep(BaseStep):
    type = "broll.generate"
    title = "Generate B-roll"
    description = (
        "Generate synthetic B-roll images through an OpenAI-compatible image "
        "endpoint, register them in the asset library, and write license records."
    )
    status = "partial"
    icon = "✦"
    color = "#f59e0b"
    requires = ("shorts.select",)
    produces = ("generated_broll",)
    params_model = GenerateBrollParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = GenerateBrollParams.model_validate(params)
        base_url = options.base_url.strip()
        if not base_url:
            context.warnings.append("B-roll generation skipped: no image endpoint configured.")
            io.report(100, "B-roll generation skipped")
            return
        prompt = _prompt_for(context, options.prompt)
        api_key = get_secret(options.api_key_env)
        generated: list[dict[str, object]] = []
        for index in range(options.count):
            io.report(int(index / options.count * 80), f"Generating B-roll {index + 1}")
            seed = None if options.seed is None else options.seed + index
            try:
                data = generate_image(
                    f"{prompt} {options.negative_prompt}".strip(),
                    base_url=base_url,
                    model=options.model,
                    api_key=api_key,
                    seed=seed,
                    width=options.width,
                    height=options.height,
                    allow_external_services=options.allow_external_services,
                    allowed_external_hosts=tuple(options.allowed_external_hosts),
                )
            except (IngestError, OSError) as exc:
                context.warnings.append(f"B-roll generation failed: {exc}")
                continue
            saved = save_image(f"generated-{uuid4().hex[:10]}.png", data)
            generated.append(
                {
                    "path": str(saved["file"]),
                    "name": str(saved["name"]),
                    "sha256": str(saved.get("sha256") or ""),
                    "prompt": prompt,
                    "seed": seed,
                    "model": options.model,
                    "provider": "generated",
                }
            )
        if not generated:
            context.warnings.append("B-roll generation produced no images.")
            io.report(100, "No B-roll images generated")
            return
        scan_directory(images_dir(), tags=options.tags, recursive=False)
        self._write_ledger(context.output, generated)
        context.metadata["generated_broll"] = generated
        target = context.output / "assets" / "generated-broll.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"assets": generated}, indent=2) + "\n", encoding="utf-8"
        )
        context.artifacts["generated_broll"] = str(target)
        io.report(100, f"{len(generated)} generated B-roll image(s)")

    def _write_ledger(
        self, output: Path, generated: list[dict[str, object]]
    ) -> None:
        payload = read_ledger(output)
        records = [
            item for item in payload.get("assets", []) if isinstance(item, dict)
        ]
        for item in generated:
            candidate = AssetCandidate(
                asset_id=f"generated-{str(item['sha256'])[:12]}",
                provider="generated",
                title=str(item["prompt"])[:120],
                page_url=str(item["path"]),
                download_url=str(item["path"]),
                kind="image",
                license="generated",
                license_status="cleared",
                allowed_commercial=True,
                attribution_required=False,
                sha256=str(item["sha256"]),
                downloaded_path=str(item["path"]),
                retrieved_at=time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
                metadata={
                    "model": item["model"],
                    "seed": item["seed"],
                    "prompt": item["prompt"],
                },
            )
            records.append(candidate.to_dict())
        blockers = [
            record
            for record in records
            if record.get("license_status") in {"unknown", "cc_review"}
            or (
                record.get("license_status") == "fair_use_review"
                and not record.get("approved")
            )
        ]
        payload["assets"] = records
        payload["blockers"] = blockers
        payload["counts"] = {
            status: sum(
                1 for record in records if record.get("license_status") == status
            )
            for status in sorted(
                {str(record.get("license_status") or "unknown") for record in records}
            )
        }
        write_ledger_from_payload(output, payload)
