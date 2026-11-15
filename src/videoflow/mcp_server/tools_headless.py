"""Declarative headless MCP tools for OpenCode."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from videoflow.application.audio_patch import patch_audio
from videoflow.application.preset_rules import load_rulebook, save_rulebook
from videoflow.application.secrets import get_secret
from videoflow.application.settings import load_settings
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
        apply: bool = False,
        provider: str = "",
        base_url: str = "",
        model: str = "",
        binary: str = "",
        model_path: str = "",
        api_key_env: str = "VIDEOWFLOW_TTS_API_KEY",
    ) -> dict[str, object]:
        """Replace one spoken line with TTS and crossfade it into the master."""

        if not text.strip():
            return error("text_required", "Pass the replacement text.")
        if not apply:
            plan = {
                "job_id": job_id or ctx.last.get("job_id"),
                "sentence_id": sentence_id,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "text": text,
                "voice": voice,
                "crossfade_ms": max(0, min(1000, crossfade_ms)),
                "apply": False,
            }
            ctx.last["audio_patch"] = plan
            return {"ok": True, "patch": plan}
        try:
            context = _job_context(ctx, job_id)
            rate = context.media.audio_sample_rate if context.media is not None else 48000
            if sentence_id is not None:
                sentence = next(
                    (item for item in context.transcript if item.id == sentence_id),
                    None,
                )
                if sentence is None:
                    return error("sentence_not_found", f"Unknown sentence {sentence_id}")
                start = sentence.start_sample / rate
                end = sentence.end_sample / rate
            elif start_sec is not None and end_sec is not None:
                start, end = start_sec, end_sec
            else:
                return error("range_required", "Pass sentence_id or start_sec/end_sec.")
            settings = load_settings()
            kind = provider or settings.tts.provider
            if kind == "none":
                return error("tts_not_configured", "Configure a TTS provider first.")
            patch_dir = context.output / "audio" / "patches"
            patch_dir.mkdir(parents=True, exist_ok=True)
            suffix = ".wav" if kind == "piper" else ".mp3"
            generated = (
                patch_dir / f"line-{sentence_id if sentence_id is not None else 'range'}{suffix}"
            )
            if kind == "piper":
                from videoflow.adapters.tts import PiperTtsAdapter

                PiperTtsAdapter(
                    binary=binary or "piper",
                    model_path=model_path,
                ).synthesize(text, generated)
            else:
                from videoflow.adapters.tts import OpenAITtsAdapter

                endpoint = base_url or os.environ.get("VIDEOWFLOW_TTS_BASE_URL", "")
                if not endpoint:
                    return error(
                        "tts_base_url_required",
                        "Set VIDEOWFLOW_TTS_BASE_URL or pass base_url.",
                    )
                OpenAITtsAdapter(
                    base_url=endpoint,
                    model=model or settings.tts.model,
                    voice=voice or settings.tts.voice,
                    api_key=get_secret(api_key_env),
                ).synthesize(text, generated)
            plan = {
                "job_id": job_id or ctx.last.get("job_id"),
                "sentence_id": sentence_id,
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "text": text,
                "voice": voice or settings.tts.voice,
                "crossfade_ms": max(0, min(1000, crossfade_ms)),
                "generated": str(generated),
            }
            if apply:
                master = Path(
                    context.artifacts.get("audio_master") or context.output / "audio" / "master.wav"
                )
                plan["patched"] = patch_audio(
                    master,
                    generated,
                    start_sec=start,
                    end_sec=end,
                    output=context.output / "audio" / f"patched-{generated.stem}.wav",
                    crossfade_ms=max(0, min(1000, crossfade_ms)),
                    sample_rate=rate,
                )
        except Exception as exc:  # noqa: BLE001
            return (
                exc.to_dict() if hasattr(exc, "to_dict") else error("audio_patch_failed", str(exc))
            )
        ctx.last["audio_patch"] = plan
        return {"ok": True, "patch": plan}

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
