"""Declarative headless MCP tools for OpenCode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.application.preset_rules import load_rulebook, save_rulebook
from videoflow.application.web_preview import preview_server
from videoflow.core.context import PipelineContext
from videoflow.domain.headless import BeatMap, PresetRule
from videoflow.domain.paths import resolve_allowed
from videoflow.engine.recipes.catalog import get_recipe, resolve_recipe_paths
from videoflow.mcp_server.context import ToolContext, error
from videoflow.runtime import allowed_roots, portable_home
from videoflow.steps.base import StepIO
from videoflow.steps.ports import validate_recipe_ports
from videoflow.steps.qa_safezone import SafeZoneParams, SafeZoneStep
from videoflow.steps.qa_visual import (
    analyze_frames,
    extract_window,
)
from videoflow.steps.registry import requirements_by_type, step_types
from videoflow.steps.style_reverse import StyleReverseParams, StyleReverseStep


def _job_context(ctx: ToolContext, job_id: str | None) -> PipelineContext:
    job = ctx.timeline_job(job_id)
    output = Path(job.output)
    state = ctx.state_for_job(job)
    media = state.media_info if state is not None else None
    source = Path(str(job.source))
    return PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=media,
        state=state,
        transcript=list(state.transcript) if state is not None else [],
        artifacts=dict((job.result or {}).get("artifacts", {})),
    )


def register_headless_tools(register: Any, ctx: ToolContext) -> None:
    """Register the eight declarative tools and their resource helpers."""

    @register
    def vf_beatmap_execute(
        manifest: dict[str, object],
        source: str | None = None,
        output: str | None = None,
        recipe_id: str = "",
        dry_run: bool = False,
    ) -> dict[str, object]:
        """Validate a beat map and execute its headless recipe in one call."""

        try:
            beat_map = BeatMap.model_validate(manifest)
            metadata = beat_map.metadata
            chosen = recipe_id.strip() or str(metadata.get("recipe") or "opencode_longform_studio")
            recipe = get_recipe(chosen)
            roots = allowed_roots()
            raw_source = source or str(metadata.get("source") or "")
            if not raw_source:
                return error("source_required", "Pass source or metadata.source")
            source_path = resolve_allowed(Path(raw_source), roots)
            output_path = resolve_allowed(
                Path(output) if output else source_path.with_name(f"{source_path.stem}-videoflow"),
                roots,
            )
            recipe = resolve_recipe_paths(recipe, roots)
            recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
            validate_recipe_ports(recipe)
            beat_path = output_path / "beat_map.json"
            beat_path.parent.mkdir(parents=True, exist_ok=True)
            beat_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            if dry_run:
                return {
                    "ok": True,
                    "dry_run": True,
                    "recipe_id": recipe.id,
                    "scenes": len(beat_map.scenes),
                    "beat_map": str(beat_path),
                }
            job = ctx.manager.start(
                source_path,
                output_path,
                {
                    "mode": "recipe",
                    "recipe": recipe.model_dump(mode="json"),
                    "resume": True,
                },
                queue=True,
            )
        except Exception as exc:  # noqa: BLE001 - MCP errors are data
            return exc.to_dict() if hasattr(exc, "to_dict") else error("beatmap_failed", str(exc))
        ctx.last.update({"source": source_path, "output": output_path, "job_id": str(job.job_id)})
        return {"ok": True, "job": job.to_dict(), "beat_map": str(beat_path)}

    @register
    def vf_preview_archetypes(
        manifest: dict[str, object] | None = None,
        job_id: str | None = None,
        duration_sec: float = 60.0,
        render: bool = False,
    ) -> dict[str, object]:
        """Group scenes by visual archetype for a short human preview."""

        try:
            if manifest is None and job_id is not None:
                path = Path(str(ctx.timeline_job(job_id).output)) / "beat_map.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
            beat_map = BeatMap.model_validate(manifest or {})
            groups: dict[str, list[dict[str, object]]] = {}
            for scene in beat_map.scenes:
                groups.setdefault(scene.archetype, []).append(
                    {
                        "id": scene.id,
                        "start_sec": scene.start_sec,
                        "end_sec": scene.end_sec,
                        "visual": scene.visual,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            return error("archetype_preview_failed", str(exc))
        return {
            "ok": True,
            "archetypes": groups,
            "sample_duration_sec": max(1.0, min(60.0, duration_sec)),
            "render_requested": render,
            "note": "Run opencode_longform_studio with draft=true to render samples.",
        }

    @register
    def vf_web_scene_preview(root: str) -> dict[str, object]:
        """Start a tokenised loopback server for a web scene directory."""

        try:
            url = preview_server.start(Path(root))
        except Exception as exc:  # noqa: BLE001
            return error("web_preview_failed", str(exc))
        return {"ok": True, "url": url, "root": str(Path(root).resolve())}

    @register
    def vf_audio_patch_line(
        job_id: str | None = None,
        sentence_id: int | None = None,
        start_sec: float | None = None,
        end_sec: float | None = None,
        text: str = "",
        voice: str = "",
        crossfade_ms: int = 80,
    ) -> dict[str, object]:
        """Plan a surgical voice patch; audio generation is done by the voice step."""

        if not text.strip():
            return error("text_required", "Pass the replacement text.")
        plan = {
            "job_id": job_id or ctx.last.get("job_id"),
            "sentence_id": sentence_id,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "text": text,
            "voice": voice,
            "crossfade_ms": max(0, min(1000, crossfade_ms)),
        }
        ctx.last["audio_patch"] = plan
        return {
            "ok": True,
            "patch": plan,
            "next": "Run voice.patch/voice.clone or apply the returned text in the Short editor.",
        }

    @register
    def vf_nle_roundtrip(
        job_id: str | None = None,
        direction: str = "pull",
        target: str = "fcpxml",
        path: str = "",
        apply: bool = False,
    ) -> dict[str, object]:
        """Run nle.sync_back and return the external/internal diff."""

        try:
            context = _job_context(ctx, job_id)
            from videoflow.steps.nle_sync import NleSyncParams, NleSyncStep

            step = NleSyncStep()
            step.run(
                context,
                NleSyncParams(format=target, path=path, apply=apply),
                StepIO(stage="nle.sync_back"),
            )
        except Exception as exc:  # noqa: BLE001
            return exc.to_dict() if hasattr(exc, "to_dict") else error("nle_sync_failed", str(exc))
        return {
            "ok": True,
            "direction": direction,
            "report": context.metadata.get("sync_back_report", {}),
        }

    @register
    def vf_qa_inspect_window(
        job_id: str | None = None,
        start_sec: float = 0.0,
        end_sec: float = 1.0,
        checks: list[str] | None = None,
    ) -> dict[str, object]:
        """Run visual and safe-zone QA for one time window."""

        try:
            context = _job_context(ctx, job_id)
            frames_dir = context.work / "qa" / "inspect"
            frames = extract_window(
                context.source, frames_dir, start_sec, max(0.1, end_sec - start_sec), 10
            )
            defects = [
                {"kind": kind, "at_sec": start_sec + local}
                for kind, local in analyze_frames(frames)
            ]
            SafeZoneStep().run(
                context,
                SafeZoneParams(platforms=["reels", "tiktok", "shorts"]),
                StepIO(stage="qa.safezone"),
            )
            safezone = context.metadata.get("safezone_report", {})
        except Exception as exc:  # noqa: BLE001
            return (
                exc.to_dict() if hasattr(exc, "to_dict") else error("qa_inspect_failed", str(exc))
            )
        return {
            "ok": True,
            "window": [start_sec, end_sec],
            "checks": checks or ["visual", "safezone"],
            "defects": defects,
            "frames": [str(path) for path in frames],
            "safezone": safezone,
        }

    @register
    def vf_preset_rules(
        channel_id: str,
        action: str = "list",
        rules: list[str] | None = None,
        text: str = "",
        rule_id: str = "",
    ) -> dict[str, object]:
        """Read or mutate a channel rulebook."""

        book = load_rulebook(channel_id)
        if action == "list":
            return {"ok": True, "rulebook": book.model_dump(mode="json")}
        if action == "add":
            for item in rules or ([text] if text else []):
                if item.strip():
                    book.rules.append(
                        PresetRule(id=f"rule-{len(book.rules) + 1}", text=item.strip())
                    )
        elif action == "delete":
            book.rules = [rule for rule in book.rules if rule.id != rule_id]
        elif action != "update":
            return error("invalid_action", "Use list, add, update, or delete.")
        path = save_rulebook(book)
        return {"ok": True, "rulebook": book.model_dump(mode="json"), "path": str(path)}

    @register
    def vf_style_clone(
        channel_id: str = "default",
        images: list[str] | None = None,
        reference_path: str = "",
        mode: str = "both",
    ) -> dict[str, object]:
        """Create a style preset from a URL/path/prints via style.reverse_engineer."""

        work = portable_home() / "mcp" / "style"
        context = PipelineContext(
            source=Path(reference_path or "."),
            output=work,
            work=work / "work",
            exports=work / "exports",
        )
        try:
            StyleReverseStep().run(
                context,
                StyleReverseParams(
                    images=images or [],
                    reference_path=reference_path,
                    mode=mode,
                    name=channel_id,
                ),
                StepIO(stage="style.reverse_engineer"),
            )
        except Exception as exc:  # noqa: BLE001
            return (
                exc.to_dict() if hasattr(exc, "to_dict") else error("style_clone_failed", str(exc))
            )
        return {"ok": True, "style_preset": context.metadata.get("style_preset", {})}
