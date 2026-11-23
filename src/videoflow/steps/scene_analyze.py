"""Scene intelligence step: manifest, layouts, hints, and keyframes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.scene_intel.io import read_json
from videoflow.application.scene_intel.pipeline import (
    analyze_scene_project,
    load_scene_cache,
    resolve_topology,
)
from videoflow.application.scene_intel.proxy import file_sha256, scene_workspace
from videoflow.application.scene_intel.remote import analyze_scene_remote
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class SceneAnalyzeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_path: str = ""
    decupage_plan_path: str = ""
    source_topology: Literal["auto", "single_16x9", "dual_canvas", "dual_file"] = "auto"
    threshold: float = Field(default=3.0, ge=0.5, le=10.0)
    min_scene_len_sec: float = Field(default=1.5, ge=0.25, le=30.0)
    keyframe_size: int = Field(default=544, ge=128, le=1080)
    compute_policy: Literal["auto", "local", "local_gpu", "remote", "remote_only"] = "auto"
    allow_slow_cpu_fallback: bool = False
    force: bool = False


def _decupage_plan(context: PipelineContext, override: str) -> dict[str, Any] | None:
    if override:
        payload = read_json(Path(override).expanduser())
        if payload:
            return payload
    raw = context.metadata.get("decupage_plan")
    if isinstance(raw, dict) and raw:
        return raw
    artifact = context.artifacts.get("decupage_plan")
    if artifact and Path(artifact).is_file():
        payload = read_json(Path(artifact))
        if payload:
            return payload
    return None


def _asus(context: PipelineContext) -> list[dict[str, Any]]:
    raw = context.metadata.get("asus")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


@register_step
class SceneAnalyzeStep(BaseStep):
    type = "scene.analyze"
    title = "Analyze scenes"
    description = (
        "Detect scene cuts, classify layouts, extract keyframes, and cache the "
        "scene manifest by video SHA-256."
    )
    status = "available"
    icon = "◫"
    color = "#0ea5e9"
    requires = ("ingest",)
    produces = ("scenes_manifest", "scenes_supercontext")
    params_model = SceneAnalyzeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SceneAnalyzeParams.model_validate(params)
        media = require_media(context)
        source = (
            Path(options.video_path).expanduser()
            if options.video_path
            else Path(context.source)
        )
        if not source.is_file():
            raise IngestError(f"Scene source does not exist: {source}")
        plan = _decupage_plan(context, options.decupage_plan_path)
        asus = _asus(context)
        io.report(5, "Computing video fingerprint")
        video_id = file_sha256(source)
        workspace_root = Path(context.output) / "scenes"
        workspace = scene_workspace(workspace_root, video_id)
        topology = resolve_topology(media, options.source_topology)
        result = None
        placement = "cache"
        degraded = False
        reason = ""
        if not options.force:
            result = load_scene_cache(
                workspace,
                media,
                threshold=options.threshold,
                min_scene_len_sec=options.min_scene_len_sec,
                topology=topology,
                keyframe_size=options.keyframe_size,
                decupage_plan=plan,
                asus=asus,
                video_id=video_id,
            )

        def local_run():  # type: ignore[no-untyped-def]
            return analyze_scene_project(
                source,
                workspace_root,
                media=media,
                threshold=options.threshold,
                min_scene_len_sec=options.min_scene_len_sec,
                source_topology=options.source_topology,
                decupage_plan=plan,
                asus=asus,
                force=options.force,
                keyframe_size=options.keyframe_size,
                video_id=video_id,
            )

        def remote_run():  # type: ignore[no-untyped-def]
            from videoflow.application.compute import router_from_settings

            return analyze_scene_remote(
                router_from_settings(),
                source,
                workspace,
                media,
                threshold=options.threshold,
                min_scene_len_sec=options.min_scene_len_sec,
                source_topology=topology,
                keyframe_size=options.keyframe_size,
                video_id=video_id,
                decupage_plan=plan,
                asus=asus,
            )

        if result is None and options.compute_policy in {"local", "local_gpu"}:
            result = local_run()
            placement = "local"
        elif result is None:
            try:
                from videoflow.application.compute import (
                    guard_remote_policy,
                    router_from_settings,
                )

                router = router_from_settings()
                guard_remote_policy(
                    router,
                    "scene_analyze",
                    compute_policy=options.compute_policy,
                    allow_slow_cpu_fallback=options.allow_slow_cpu_fallback,
                    error_cls=IngestError,
                )
                if options.compute_policy == "remote_only":
                    decision = router.decide("scene_analyze")
                    if not decision.is_remote:
                        raise IngestError(
                            "Remote scene analysis requested but unavailable: "
                            f"{decision.reason}"
                        )
                    result = remote_run()
                    placement = decision.execution_node
                else:
                    outcome = router.execute(
                        "scene_analyze",
                        remote_run,
                        local_run,
                        compute_policy=options.compute_policy,
                        allow_slow_cpu_fallback=options.allow_slow_cpu_fallback,
                    )
                    result = outcome["value"]
                    placement = str(outcome.get("execution_node") or "local")
                    degraded = bool(outcome.get("degraded"))
                    reason = str(outcome.get("degraded_reason") or "")
            except IngestError:
                raise
            except Exception as exc:  # noqa: BLE001 - local fallback is the contract
                if options.compute_policy == "remote_only":
                    raise IngestError(
                        f"Remote scene analysis unavailable: {exc}"
                    ) from exc
                result = local_run()
                placement = "local"
                degraded = True
                reason = f"compute router failed: {exc}"
        assert result is not None
        payload = result.manifest.model_dump(mode="json")
        context.metadata["scenes_manifest"] = payload
        context.metadata["scenes_summary"] = result.summary()
        context.metadata["scenes_supercontext"] = result.supercontext
        context.metadata["scenes_compute"] = {
            "placement": placement,
            "degraded": degraded,
            "degraded_reason": reason,
            "engine": result.engine,
            "cache_hit": result.cache_hit,
            "elapsed_sec": round(result.elapsed_sec, 3),
        }
        context.artifacts["scenes_manifest"] = str(result.workspace.manifest)
        context.artifacts["scenes_supercontext"] = str(result.workspace.supercontext)
        context.artifacts["scenes_keyframes"] = str(result.workspace.keyframes)
        context.hashes["scene.analyze"] = digest_payload(payload)
        context.cache_hits = list(context.cache_hits)
        context.cache_misses = list(context.cache_misses)
        if result.cache_hit:
            context.cache_hits.append("scene.analyze")
        else:
            context.cache_misses.append("scene.analyze")
        for warning in result.warnings:
            if warning not in context.warnings:
                context.warnings.append(warning)
        if degraded and reason:
            message = f"Scene analysis ran locally: {reason}"
            if message not in context.warnings:
                context.warnings.append(message)
            io.emit("warning", message, module="scene.analyze")
        summary = result.summary()
        io.emit(
            "info",
            (
                f"{summary['scene_count']} scene(s) via {summary['engine']} "
                f"({summary['layout_counts']})"
            ),
            module="scene.analyze",
        )
        if summary["warnings"]:
            for warning in summary["warnings"]:
                io.emit("warning", warning, module="scene.analyze")
        io.report(100, f"{summary['scene_count']} scene(s) analyzed")


__all__ = ["SceneAnalyzeParams", "SceneAnalyzeStep"]
