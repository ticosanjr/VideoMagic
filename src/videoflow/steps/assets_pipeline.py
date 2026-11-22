"""Asset discovery, harvest, license audit, and unit assignment."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domains.media import (
    AssetCandidate,
    download_asset,
    license_blockers,
    mark_approved,
    search_assets,
    write_ledger,
)
from videoflow.domains.media.assets import scan_directory
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class DiscoverParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    units_path: str = Field(default="storyboard/units.json", max_length=2000)
    providers: list[str] = Field(
        default_factory=lambda: ["pexels", "openverse", "wikimedia", "internet_archive"]
    )
    media: Literal["all", "video", "image", "audio"] = "all"
    max_units: int = Field(default=40, ge=1, le=400)
    max_per_unit: int = Field(default=2, ge=1, le=5)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


@register_step
class AssetsDiscoverStep(BaseStep):
    type = "assets.discover"
    title = "Discover assets"
    description = (
        "Search licensed providers for every storyboard unit and write a "
        "candidate manifest with explicit license metadata."
    )
    status = "available"
    icon = "⌕"
    color = "#f59e0b"
    params_model = DiscoverParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = DiscoverParams.model_validate(params)
        path = context.output / options.units_path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        units = payload.get("units") if isinstance(payload, dict) else []
        if not isinstance(units, list) or not units:
            units = [
                {
                    "unit_id": f"UNIT-{index + 1:04d}",
                    "title": str(item.get("context_block_id") or f"Block {index + 1}"),
                    "asset_query": str(item.get("text") or "")[:240],
                }
                for index, item in enumerate(context.metadata.get("narrative_beats", []))
                if isinstance(item, dict)
            ]
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        warnings: list[str] = []
        for index, unit in enumerate(units[: options.max_units], start=1):
            if not isinstance(unit, dict):
                continue
            query = str(unit.get("asset_query") or unit.get("title") or "").strip()
            if not query:
                continue
            io.report(
                int((index - 1) / max(1, len(units[: options.max_units])) * 100),
                f"Searching assets for {unit.get('unit_id') or index}",
            )
            try:
                found = search_assets(
                    query,
                    providers=options.providers,
                    media=options.media,
                    limit=options.max_per_unit,
                    allow_external_services=options.allow_external_services,
                    allowed_external_hosts=options.allowed_external_hosts,
                )
            except Exception as exc:  # noqa: BLE001 - one query must not stop discovery
                warnings.append(f"{unit.get('unit_id') or index}: {exc}")
                continue
            for candidate in found:
                if candidate.asset_id in seen:
                    continue
                seen.add(candidate.asset_id)
                item = candidate.to_dict()
                item["unit_id"] = str(unit.get("unit_id") or "")
                item["query"] = query
                candidates.append(item)
        target = context.output / "assets" / "candidates.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"candidates": candidates, "count": len(candidates), "warnings": warnings},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        context.metadata["asset_candidates"] = candidates
        context.artifacts["asset_candidates"] = str(target)
        context.hashes["assets.discover"] = digest_payload(
            {"assets": len(candidates), "warnings": warnings}
        )
        io.report(100, f"{len(candidates)} candidate(s) discovered")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("asset_candidates")
        return (Path(path),) if path else ()


class HarvestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates_path: str = Field(default="assets/candidates.json", max_length=2000)
    max_assets: int = Field(default=40, ge=1, le=400)
    clip_seconds: int = Field(default=15, ge=1, le=120)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)
    register_library: bool = True


def _suffix(candidate: AssetCandidate) -> str:
    suffix = Path(urlparse(candidate.download_url).path).suffix.casefold()
    if suffix in {".mp4", ".mov", ".m4v", ".webm"}:
        return suffix
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix
    if suffix in {".mp3", ".wav", ".m4a", ".flac", ".ogg"}:
        return suffix
    return ".mp4" if candidate.kind == "video" else ".jpg" if candidate.kind == "image" else ".bin"


@register_step
class AssetsHarvestStep(BaseStep):
    type = "assets.harvest"
    title = "Harvest assets"
    description = (
        "Download selected candidates, including short fair-use YouTube excerpts, "
        "and write the license ledger."
    )
    status = "available"
    icon = "⇩"
    color = "#f59e0b"
    params_model = HarvestParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = HarvestParams.model_validate(params)
        path = context.output / options.candidates_path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        raw_candidates = payload.get("candidates") if isinstance(payload, dict) else []
        if not isinstance(raw_candidates, list):
            raw_candidates = []
        directory = context.output / "assets" / "harvested"
        directory.mkdir(parents=True, exist_ok=True)
        candidates: list[AssetCandidate] = []
        warnings: list[str] = []
        for index, raw in enumerate(raw_candidates[: options.max_assets], start=1):
            if not isinstance(raw, dict):
                continue
            candidate = AssetCandidate.from_dict(raw)
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", candidate.asset_id)[:80]
            target = directory / f"{safe}{_suffix(candidate)}"
            io.report(
                int((index - 1) / max(1, len(raw_candidates[: options.max_assets])) * 100),
                f"Downloading {candidate.title[:50]}",
            )
            try:
                candidate = download_asset(
                    candidate,
                    target,
                    allow_external_services=options.allow_external_services,
                    allowed_external_hosts=options.allowed_external_hosts,
                    clip_seconds=options.clip_seconds,
                )
                candidates.append(candidate)
            except Exception as exc:  # noqa: BLE001 - keep the rest of the harvest
                warnings.append(f"{candidate.title}: {exc}")
        ledger_path = write_ledger(context.output, candidates)
        manifest = {
            "assets": [candidate.to_dict() for candidate in candidates],
            "count": len(candidates),
            "warnings": warnings,
            "ledger": str(ledger_path),
        }
        manifest_path = context.output / "assets" / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if options.register_library and candidates:
            scan_directory(directory, tags=["harvested"])
        context.metadata["assets_manifest"] = manifest
        context.artifacts["assets_manifest"] = str(manifest_path)
        context.artifacts["assets_licenses"] = str(ledger_path)
        context.hashes["assets.harvest"] = digest_payload(
            {"assets": len(candidates), "warnings": warnings}
        )
        io.report(100, f"{len(candidates)} asset(s) harvested")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("assets_manifest", "assets_licenses")
            if context.artifacts.get(key)
        )


class AuditParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_path: str = Field(default="assets/manifest.json", max_length=2000)


@register_step
class AssetsLicenseAuditStep(BaseStep):
    type = "assets.license_audit"
    title = "Audit asset licenses"
    description = (
        "Rebuild the license ledger from the harvested manifest and list assets "
        "that need human approval before export."
    )
    status = "available"
    icon = "⚖"
    color = "#f59e0b"
    params_model = AuditParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AuditParams.model_validate(params)
        path = context.output / options.manifest_path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        raw = payload.get("assets") if isinstance(payload, dict) else []
        candidates = [
            AssetCandidate.from_dict(item)
            for item in (raw if isinstance(raw, list) else [])
            if isinstance(item, dict)
        ]
        ledger_path = write_ledger(context.output, candidates)
        blockers = license_blockers(
            context.output,
            state=context.state,
            scope="timeline" if context.state is not None else "workspace",
        )
        context.metadata["license_blockers"] = blockers
        context.artifacts["assets_licenses"] = str(ledger_path)
        context.hashes["assets.license_audit"] = digest_payload(
            {"assets": len(candidates), "blockers": len(blockers)}
        )
        io.report(
            100,
            f"{len(candidates)} asset(s); {len(blockers)} need license review",
        )

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("assets_licenses")
        return (Path(path),) if path else ()


class AssignParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    units_path: str = Field(default="storyboard/units.json", max_length=2000)
    manifest_path: str = Field(default="assets/manifest.json", max_length=2000)


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


@register_step
class AssetsAssignStep(BaseStep):
    type = "assets.assign"
    title = "Assign assets"
    description = (
        "Place approved harvested assets into units and write the NLE B-roll "
        "plan; a gate approval marks fair-use/CC items approved in the ledger."
    )
    status = "available"
    icon = "↔"
    color = "#f59e0b"
    params_model = AssignParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AssignParams.model_validate(params)
        units_payload = _load_json(context.output / options.units_path, {})
        manifest_payload = _load_json(context.output / options.manifest_path, {})
        units = units_payload.get("units") if isinstance(units_payload, dict) else []
        assets = manifest_payload.get("assets") if isinstance(manifest_payload, dict) else []
        if not isinstance(units, list):
            units = []
        if not isinstance(assets, list):
            assets = []
        gate = context.metadata.get("gate_assets_review")
        if isinstance(gate, dict) and gate.get("approved"):
            approval_id = str(gate.get("interaction_id") or "assets-review")
            mark_approved(
                context.output,
                approval_id=approval_id,
                reviewer=str(gate.get("responded_by") or "human"),
            )
        by_unit: dict[str, list[dict[str, Any]]] = {}
        for item in assets:
            if (
                not isinstance(item, dict)
                or not item.get("downloaded_path")
                or str(item.get("kind") or "") not in {"video", "image"}
            ):
                continue
            by_unit.setdefault(str(item.get("unit_id") or ""), []).append(item)
        assignments: list[dict[str, Any]] = []
        broll: dict[str, list[dict[str, Any]]] = {}
        for unit in units:
            if not isinstance(unit, dict):
                continue
            unit_id = str(unit.get("unit_id") or "")
            selected = by_unit.get(unit_id, [])
            if not selected:
                assignments.append(
                    {"unit_id": unit_id, "asset": None, "layout": unit.get("layout")}
                )
                continue
            asset = selected[0]
            start = float(unit.get("start_sec") or 0.0)
            duration = float(unit.get("duration_sec") or 4.0)
            cue = {
                "path": asset["downloaded_path"],
                "start_sec": start,
                "duration_sec": min(duration, float(asset.get("duration_sec") or duration)),
                "provider": asset.get("provider", ""),
                "license": asset.get("license", ""),
                "license_status": asset.get("license_status", "unknown"),
                "attribution": asset.get("creator", "") or asset.get("title", ""),
                "source_url": asset.get("page_url", ""),
                "unit_id": unit_id,
            }
            broll.setdefault(unit_id, []).append(cue)
            assignments.append(
                {"unit_id": unit_id, "layout": unit.get("layout"), "asset": asset, "cue": cue}
            )
        assignments_path = context.output / "assets" / "assignments.json"
        assignments_path.write_text(
            json.dumps({"assignments": assignments}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        broll_path = context.output / "broll.json"
        broll_path.write_text(
            json.dumps(broll, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        context.metadata["asset_assignments"] = assignments
        context.artifacts["assets_assignments"] = str(assignments_path)
        context.artifacts["broll"] = str(broll_path)
        context.hashes["assets.assign"] = digest_payload(
            {"units": len(units), "assigned": len(broll)}
        )
        io.report(100, f"{len(broll)} unit(s) assigned")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("assets_assignments", "broll")
            if context.artifacts.get(key)
        )
