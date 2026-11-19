"""Recipe runner: validate a DAG, execute steps, checkpoint, and persist."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.adapters.llm import OpenAICompatibleLlm
from videoflow.application.step_outputs import write_step_outputs
from videoflow.core.context import PipelineContext
from videoflow.core.recipe import Recipe, RecipeStep
from videoflow.domain.errors import RecipeError, StepExecutionError, VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.engine.checkpoint import (
    CHECKPOINT_VERSION,
    read_json,
    restore_context,
    snapshot_context,
    source_fingerprint,
    step_dir,
    write_json,
)
from videoflow.exporters.common import write_text
from videoflow.runtime import allowed_roots
from videoflow.steps import get_step, requirements_by_type, step_types
from videoflow.steps.base import StepIO
from videoflow.steps.cache import cache_key
from videoflow.steps.ports import (
    apply_inputs,
    capture_outputs,
    input_fingerprint,
    validate_recipe_ports,
    write_context,
)

StepStatus = Literal["cached", "executed", "skipped"]


def _project_state_revision(output: Path) -> int:
    path = output / "project_state.json"
    if not path.is_file():
        return 0
    try:
        from videoflow.domain.state import ProjectState

        revision = ProjectState.model_validate_json(
            path.read_text(encoding="utf-8")
        ).revision
        return revision if revision > 1 else 0
    except (OSError, ValueError):
        return 0


def persist_project_state(context: PipelineContext) -> Path | None:
    """Write the timeline atomically without clobbering newer manual edits."""

    if context.state is None:
        return None
    destination = context.output / "project_state.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        try:
            from videoflow.domain.state import ProjectState

            current = ProjectState.model_validate_json(
                destination.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            current = None
        if current is not None and current.revision > context.state.revision:
            return destination
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        context.state.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, destination)
    return destination


@dataclass(frozen=True, slots=True)
class StepRun:
    id: str
    type: str
    status: StepStatus
    elapsed_ms: int
    fingerprint: str
    outputs: tuple[str, ...]
    progress: int = 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "progress": self.progress,
            "fingerprint": self.fingerprint,
            "outputs": list(self.outputs),
        }


@dataclass(frozen=True, slots=True)
class RecipeRunResult:
    recipe_id: str
    context: PipelineContext
    elapsed_seconds: float
    state_path: Path
    report_path: Path
    step_runs: tuple[StepRun, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "ok": True,
            "mode": "recipe",
            "recipe_id": self.recipe_id,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "state_path": str(self.state_path),
            "report_path": str(self.report_path),
            "step_runs": [run.to_dict() for run in self.step_runs],
            **self.context.summary(),
        }
        payload["shorts"] = list(self.context.shorts)
        return payload


class RecipeRunner:
    """Execute one recipe for one source file, with per-step checkpoints."""

    def __init__(
        self,
        recipe: Recipe,
        *,
        adapter: Any | None = None,
        llm_client: Any | None = None,
        asr_client: Any | None = None,
        cancel_event: Any | None = None,
    ) -> None:
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        self.recipe = recipe
        self.adapter = adapter
        self.llm_client = llm_client
        self.asr_client = asr_client
        self.cancel_event = cancel_event

    def _ensure_media_override(self, context: PipelineContext, recipe_step: RecipeStep) -> None:
        value = recipe_step.media_override.strip()
        if recipe_step.type == "ingest" or not value or recipe_step.inputs.get("media"):
            return
        path = resolve_allowed(Path(value), allowed_roots())
        if not path.is_file():
            raise RecipeError(f"{recipe_step.id}: media override is not a file: {path}")
        if context.media is not None and Path(context.media.source_path) == path:
            return
        adapter = self.adapter or FFmpegAdapter()
        media = adapter.probe(path)
        context.source = path
        context.media = media
        context.metadata["media_override"] = str(path)
        if context.pcm_path is None:
            context.work.mkdir(parents=True, exist_ok=True)
            wav = adapter.extract_pcm(
                path,
                context.work / "source.wav",
                sample_rate=media.audio_sample_rate,
            )
            context.pcm_path = Path(wav)
            context.pcm_digest = adapter.pcm_digest(wav)

    def _persist_step_outputs(
        self,
        context: PipelineContext,
        step: Any,
        recipe_step: RecipeStep,
        *,
        status: str,
        fingerprint: str,
        elapsed_ms: int = 0,
        files: Any = (),
        artifacts: dict[str, str] | None = None,
    ) -> None:
        write_step_outputs(
            context.output,
            step_id=recipe_step.id,
            step_type=step.type,
            status=status,
            fingerprint=fingerprint,
            ports=context.port_outputs.get(recipe_step.id, {}),
            port_specs=step.output_ports,
            hashes=context.port_hashes.get(recipe_step.id, {}),
            files=files,
            artifacts=artifacts,
            elapsed_ms=elapsed_ms,
        )

    def _merge_step_outputs(
        self,
        context: PipelineContext,
        step_context: PipelineContext,
        step: Any,
        recipe_step: RecipeStep,
    ) -> None:
        capture_outputs(step_context, step, recipe_step.id)
        for port in step.output_ports:
            write_context(
                context,
                port.context_key,
                step_context.port_outputs[recipe_step.id][port.id],
            )
        context.port_outputs[recipe_step.id] = step_context.port_outputs[
            recipe_step.id
        ]
        context.port_hashes[recipe_step.id] = step_context.port_hashes[
            recipe_step.id
        ]
        # Non-data bookkeeping stays visible to the runner: step hashes feed
        # checkpoint fingerprints and warnings feed the UI. Every domain value
        # crosses steps through a declared port above.
        context.hashes.update(step_context.hashes)
        context.cache_hits.extend(
            item for item in step_context.cache_hits if item not in context.cache_hits
        )
        context.cache_misses.extend(
            item
            for item in step_context.cache_misses
            if item not in context.cache_misses
        )
        for warning in step_context.warnings:
            if warning not in context.warnings:
                context.warnings.append(warning)

    def _copy_node_outputs(
        self,
        context: PipelineContext,
        step_context: PipelineContext,
        recipe_step: RecipeStep,
        step: Any,
        before: dict[str, str],
    ) -> None:
        if recipe_step.output_mode != "folder":
            return
        if not recipe_step.output_dir.strip():
            raise RecipeError(f"{recipe_step.id}: output folder is required")
        directory = resolve_allowed(Path(recipe_step.output_dir), allowed_roots())
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise RecipeError(f"{recipe_step.id}: output folder is not a directory")
        candidates: list[Path] = []
        seen: set[Path] = set()
        for key, value in step_context.artifacts.items():
            if before.get(key) == value:
                continue
            path = Path(value).expanduser()
            if path.is_file() and path.resolve() not in seen:
                seen.add(path.resolve())
                candidates.append(path)
        for value in step.cache_outputs(step_context):
            path = Path(value)
            if path.is_file() and path.resolve() not in seen:
                seen.add(path.resolve())
                candidates.append(path)
        copied: list[str] = []
        for path in candidates:
            if not path.is_file():
                continue
            try:
                relative = path.resolve().relative_to(step_context.output.resolve())
            except ValueError:
                relative = Path(recipe_step.id) / path.name
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            context.artifacts[f"{recipe_step.id}:{relative.as_posix()}"] = str(target)
            copied.append(str(target))
        if copied:
            context.metadata.setdefault("node_outputs", {})[
                recipe_step.id
            ] = copied

    def run(
        self,
        source: Path,
        output: Path,
        *,
        progress: Any | None = None,
        step_progress: Any | None = None,
        should_cancel: Any | None = None,
        log: Any | None = None,
        telemetry: Any | None = None,
        transcript_sentences: list[Any] | None = None,
        through: str | None = None,
        resume: bool = True,
        variables: dict[str, Any] | None = None,
        profile: str | None = None,
        job_id: str = "",
        seed_metadata: dict[str, Any] | None = None,
        write_report: bool = True,
        source_stamp: str | None = None,
        ai: Any | None = None,
    ) -> RecipeRunResult:
        from uuid import uuid4

        started = time.perf_counter()
        recipe = self.recipe.with_variables(variables, profile=profile)
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        validate_recipe_ports(recipe, through=through)
        source_path = Path(source).expanduser().resolve()
        if source_stamp is None:
            source_stamp = source_fingerprint(source_path)
        output_path = Path(output).expanduser().resolve()
        work = output_path / "work"
        exports = output_path / "exports"
        work.mkdir(parents=True, exist_ok=True)
        exports.mkdir(parents=True, exist_ok=True)
        context = PipelineContext(
            source=source_path,
            output=output_path,
            work=work,
            exports=exports,
            transcript=list(transcript_sentences or []),
            metadata={
                "run_id": str(uuid4()),
                "job_id": job_id,
                "recipe_id": recipe.id,
                "variables": dict(recipe.variables_resolved),
                "profile": profile or "",
            },
        )
        if seed_metadata:
            context.metadata.update(seed_metadata)
        order = self._order_through(recipe.topological_order(), through)
        llm = self.llm_client or self._build_llm(log)
        from videoflow.application.intelligence import build_intelligence

        if ai is None:
            ai = build_intelligence()
        step_llms: dict[str, Any] = {}
        total = len(order)
        step_runs: list[StepRun] = []
        research_groups: dict[tuple[str, ...], list[RecipeStep]] = {}
        for candidate in order:
            if candidate.type == "research.multi_agent":
                key = tuple(sorted(candidate.needs))
                research_groups.setdefault(key, []).append(candidate)
        handled_research: set[str] = set()

        for index, recipe_step in enumerate(order, start=1):
            if recipe_step.id in handled_research:
                continue
            research_group = research_groups.get(
                tuple(sorted(recipe_step.needs)), []
            )
            if (
                recipe_step.type == "research.multi_agent"
                and len(research_group) > 1
                and recipe_step.id == research_group[0].id
            ):
                group_runs = self._run_research_group(
                    research_group,
                    context,
                    source_path=source_path,
                    output_path=output_path,
                    source_stamp=source_stamp,
                    ai=ai,
                    llm=llm,
                    resume=resume,
                    job_id=job_id,
                    step_progress=step_progress,
                    should_cancel=should_cancel,
                    log=log,
                    telemetry=telemetry,
                )
                step_runs.extend(group_runs)
                handled_research.update(step.id for step in research_group)
                continue
            step = get_step(recipe_step.type)
            params = step.validate_params(recipe_step.params)
            step_llm = llm
            provider_id = str(getattr(params, "provider_id", "") or "")
            if provider_id:
                from videoflow.application.providers import list_providers

                capability = {
                    "transcribe": "asr",
                    "localization.dub": "tts",
                    "retakes.cull": "llm",
                    "decupage.llm": "llm",
                    "llm.cleanup": "llm",
                    "llm.timeline": "llm",
                    "llm.zoom": "llm",
                    "llm.style": "llm",
                }.get(step.type, "")
                provider = next(
                    (
                        item
                        for item in list_providers()
                        if str(item.get("id")) == provider_id
                    ),
                    None,
                )
                if provider is None:
                    raise RecipeError(
                        f"{recipe_step.id}: unknown provider {provider_id}"
                    )
                if capability and str(provider.get("capability")) != capability:
                    raise RecipeError(
                        f"{recipe_step.id}: provider {provider_id} is not a {capability} provider"
                    )
                if not bool(provider.get("configured", True)):
                    missing = ", ".join(
                        str(item) for item in provider.get("missing", [])
                    )
                    raise RecipeError(
                        f"{recipe_step.id}: provider {provider_id} is not configured"
                        + (f" (missing {missing})" if missing else "")
                    )
                values = {
                    "base_url": provider.get("base_url")
                    or getattr(params, "base_url", None),
                    "model": provider.get("model")
                    or getattr(params, "model", ""),
                    "api_key_env": provider.get("api_key_env")
                    or getattr(params, "api_key_env", ""),
                }
                params = params.model_copy(
                    update={
                        key: value
                        for key, value in values.items()
                        if hasattr(params, key)
                    }
                )
                if step.type in {
                    "retakes.cull",
                    "llm.cleanup",
                    "llm.timeline",
                    "llm.zoom",
                    "llm.style",
                }:
                    if provider_id not in step_llms:
                        client = self._llm_from_provider(provider, log)
                        if client is None:
                            raise RecipeError(
                                f"{recipe_step.id}: provider {provider_id} is not configured"
                            )
                        step_llms[provider_id] = client
                    step_llm = step_llms[provider_id]
            fingerprint = cache_key(
                {
                    "checkpoint": CHECKPOINT_VERSION,
                    "step_id": recipe_step.id,
                    "type": step.type,
                    "version": step.version,
                    "params": params.model_dump(mode="json"),
                    "source": context.pcm_digest or source_stamp,
                    "variables": dict(recipe.variables_resolved),
                    "upstream": {
                        dependency: context.hashes.get(dependency, "")
                        for dependency in recipe_step.needs
                    },
                    "inputs": input_fingerprint(context, recipe_step.inputs),
                    "media_override": recipe_step.media_override,
                    "output": {
                        "mode": recipe_step.output_mode,
                        "dir": recipe_step.output_dir,
                    },
                    "timeline_state_revision": (
                        _project_state_revision(output_path)
                        if step.type == "edit.timeline"
                        and bool(getattr(params, "replace_manual", False))
                        else 0
                    ),
                }
            )
            io = StepIO(
                stage=recipe_step.id,
                index=index,
                total=total,
                adapter=self.adapter,
                llm_client=step_llm,
                ai=ai,
                asr_client=self.asr_client,
                progress=progress,
                step_progress=step_progress,
                should_cancel=should_cancel,
                cancel_event=self.cancel_event,
                log=log,
            )
            directory = step_dir(output_path, recipe_step.id)
            manifest_path = directory / "manifest.json"
            snapshot_path = directory / "snapshot.json"

            if step.bypass:
                context.hashes[recipe_step.id] = fingerprint
                context.metadata.setdefault("step_progress", {})[recipe_step.id] = 100
                step_runs.append(
                    StepRun(
                        id=recipe_step.id,
                        type=step.type,
                        status="skipped",
                        elapsed_ms=0,
                        fingerprint=fingerprint,
                        outputs=(),
                        progress=100,
                    )
                )
                capture_outputs(context, step, recipe_step.id)
                self._persist_step_outputs(
                    context,
                    step,
                    recipe_step,
                    status="skipped",
                    fingerprint=fingerprint,
                )
                if step_progress is not None:
                    step_progress(recipe_step.id, 100, f"{step.title} bypassed")
                io.report(100, f"{step.title} bypassed")
                persist_project_state(context)
                continue

            if resume and step.is_cacheable(params):
                cached = self._load_checkpoint(
                    context, step, manifest_path, snapshot_path, fingerprint
                )
                if cached is not None:
                    context.hashes[recipe_step.id] = fingerprint
                    context.cache_hits.append(recipe_step.id)
                    step_runs.append(
                        StepRun(
                            id=recipe_step.id,
                            type=step.type,
                            status="cached",
                            elapsed_ms=0,
                            fingerprint=fingerprint,
                            outputs=cached,
                            progress=100,
                        )
                    )
                    context.metadata.setdefault("step_progress", {})[recipe_step.id] = 100
                    if step_progress is not None:
                        step_progress(recipe_step.id, 100, "Cached checkpoint reused")
                    if telemetry is not None:
                        telemetry.start(
                            recipe_step.id,
                            step.type,
                            step.title,
                            f"Reusing {step.title}",
                        )
                        telemetry.finish(recipe_step.id, "Checkpoint reused")
                    self._copy_node_outputs(context, context, recipe_step, step, {})
                    capture_outputs(context, step, recipe_step.id)
                    self._persist_step_outputs(
                        context,
                        step,
                        recipe_step,
                        status="cached",
                        fingerprint=fingerprint,
                        files=cached,
                    )
                    io.report(100, "Cached checkpoint reused")
                    persist_project_state(context)
                    continue

            context.cache_misses.append(recipe_step.id)
            if telemetry is not None:
                telemetry.start(
                    recipe_step.id,
                    step.type,
                    step.title,
                    f"Running {step.title}",
                )
            io.check_cancel()
            step_started = time.perf_counter()
            context.metadata.setdefault("step_progress", {})[recipe_step.id] = 0
            self._ensure_media_override(context, recipe_step)
            step_context = context.model_copy(deep=True)
            if recipe_step.inputs:
                apply_inputs(step_context, step, recipe_step.inputs)
            before_artifacts = dict(step_context.artifacts)
            try:
                step.run(step_context, params, io)
            except Exception as exc:
                if telemetry is not None:
                    telemetry.fail(recipe_step.id, str(exc))
                context.metadata["failed_step"] = recipe_step.id
                if isinstance(exc, VideoFlowError):
                    raise
                raise StepExecutionError(recipe_step.id, str(exc)) from exc
            elapsed_ms = int((time.perf_counter() - step_started) * 1000)
            self._copy_node_outputs(
                context, step_context, recipe_step, step, before_artifacts
            )
            self._merge_step_outputs(context, step_context, step, recipe_step)
            step_files = tuple(str(path) for path in step.cache_outputs(context))
            step_artifacts = {
                key: str(value)
                for key, value in step_context.artifacts.items()
                if before_artifacts.get(key) != value
            }
            self._persist_step_outputs(
                context,
                step,
                recipe_step,
                status="executed",
                fingerprint=fingerprint,
                elapsed_ms=elapsed_ms,
                files=step_files,
                artifacts=step_artifacts,
            )
            context.metadata.setdefault("step_progress", {})[recipe_step.id] = 100
            if step_progress is not None:
                step_progress(recipe_step.id, 100, f"{step.title} ready")
            persist_project_state(context)
            context.hashes[recipe_step.id] = fingerprint
            outputs = tuple(str(path) for path in step.cache_outputs(context))
            write_json(
                snapshot_path,
                {
                    "v": CHECKPOINT_VERSION,
                    "step_id": recipe_step.id,
                    "type": step.type,
                    "fingerprint": fingerprint,
                    "context": snapshot_context(context),
                },
            )
            write_json(
                manifest_path,
                {
                    "v": CHECKPOINT_VERSION,
                    "step_id": recipe_step.id,
                    "type": step.type,
                    "status": "succeeded",
                    "elapsed_ms": elapsed_ms,
                    "fingerprint": fingerprint,
                    "outputs": list(outputs),
                },
            )
            step_runs.append(
                StepRun(
                    id=recipe_step.id,
                    type=step.type,
                    status="executed",
                    elapsed_ms=elapsed_ms,
                    fingerprint=fingerprint,
                    outputs=outputs,
                    progress=100,
                )
            )
            if telemetry is not None:
                telemetry.finish(recipe_step.id, f"{step.title} ready")

        state_path = output_path / "project_state.json"
        persist_project_state(context)
        report_path = output_path / "run.json"
        result = RecipeRunResult(
            recipe_id=self.recipe.id,
            context=context,
            elapsed_seconds=time.perf_counter() - started,
            state_path=state_path,
            report_path=report_path,
            step_runs=tuple(step_runs),
        )
        report = result.to_dict()
        report["recipe"] = self.recipe.model_dump(mode="json")
        report["steps"] = [
            {"id": step.id, "type": step.type, "needs": step.needs}
            for step in self.recipe.steps
        ]
        report["through"] = through
        report["resume"] = resume
        report["hashes"] = dict(context.hashes)
        if write_report:
            write_text(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
        if progress is not None:
            progress("done", 100, "Finished")
        return result

    def _run_research_group(
        self,
        group: list[RecipeStep],
        context: PipelineContext,
        *,
        source_path: Path,
        output_path: Path,
        source_stamp: str,
        ai: Any,
        llm: Any | None,
        resume: bool,
        job_id: str,
        step_progress: Any | None,
        should_cancel: Any | None,
        log: Any | None,
        telemetry: Any | None,
    ) -> list[StepRun]:
        """Run independent scoped research agents concurrently.

        Each agent gets its own isolated recipe/context and writes its own
        checkpoint. The parent context receives the union of their files,
        hashes, ports, warnings, and agent metadata.
        """

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def run_one(step: RecipeStep):
            single = Recipe(
                schema_version=1,
                id=f"{self.recipe.id}.{step.id}",
                name=f"{self.recipe.name} · {step.id}",
                steps=[
                    step.model_copy(update={"needs": [], "inputs": {}})
                ],
            )
            runner = RecipeRunner(
                single,
                adapter=self.adapter,
                llm_client=llm,
                asr_client=self.asr_client,
                cancel_event=self.cancel_event,
            )
            return runner.run(
                source_path,
                output_path,
                step_progress=step_progress,
                should_cancel=should_cancel,
                log=log,
                telemetry=telemetry,
                resume=resume,
                job_id=job_id,
                source_stamp=source_stamp,
                ai=ai,
                seed_metadata={
                    "hilt_answers": context.metadata.get("hilt_answers", {}),
                    "variables": context.metadata.get("variables", {}),
                },
                write_report=False,
            )

        workers = min(len(group), max(1, min(8, os.cpu_count() or 1)))
        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_one, step): step for step in group}
            for future in as_completed(futures):
                results.append(future.result())
        by_id = {
            result.step_runs[0].id: result
            for result in results
            if result.step_runs
        }
        ordered_runs: list[StepRun] = []
        combined_agents: list[dict[str, Any]] = []
        for step in group:
            result = by_id.get(step.id)
            if result is None:
                continue
            child = result.context
            context.artifacts.update(child.artifacts)
            context.port_outputs.update(child.port_outputs)
            context.port_hashes.update(child.port_hashes)
            context.hashes.update(child.hashes)
            context.cache_hits.extend(
                item for item in child.cache_hits if item not in context.cache_hits
            )
            context.cache_misses.extend(
                item
                for item in child.cache_misses
                if item not in context.cache_misses
            )
            for warning in child.warnings:
                if warning not in context.warnings:
                    context.warnings.append(warning)
            agents = child.metadata.get("research_agents")
            if isinstance(agents, list):
                combined_agents.extend(
                    item for item in agents if isinstance(item, dict)
                )
            ordered_runs.extend(result.step_runs)
            for run in result.step_runs:
                context.hashes[run.id] = run.fingerprint
            context.metadata.setdefault("step_progress", {})[step.id] = 100
        if combined_agents:
            context.metadata["research_agents"] = combined_agents
        return ordered_runs

    def _load_checkpoint(
        self,
        context: PipelineContext,
        step: Any,
        manifest_path: Path,
        snapshot_path: Path,
        fingerprint: str,
    ) -> tuple[str, ...] | None:
        manifest = read_json(manifest_path)
        snapshot = read_json(snapshot_path)
        if manifest is None or snapshot is None:
            return None
        if manifest.get("v") != CHECKPOINT_VERSION:
            return None
        if manifest.get("fingerprint") != fingerprint:
            return None
        if manifest.get("status") != "succeeded":
            return None
        if snapshot.get("fingerprint") != fingerprint:
            return None
        try:
            restore_context(context, snapshot)
        except (ValueError, TypeError):
            return None
        outputs = tuple(str(path) for path in step.cache_outputs(context))
        if any(not Path(path).is_file() for path in outputs):
            return None
        return outputs

    def plan(
        self,
        *,
        variables: dict[str, Any] | None = None,
        profile: str | None = None,
        through: str | None = None,
    ) -> dict[str, Any]:
        recipe = self.recipe.with_variables(variables, profile=profile)
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        validate_recipe_ports(recipe, through=through)
        order = self._order_through(recipe.topological_order(), through)
        return {
            "ok": True,
            "recipe_id": recipe.id,
            "profile": profile or "",
            "variables": dict(recipe.variables_resolved),
            "steps": [
                {
                    "id": step.id,
                    "type": step.type,
                    "needs": list(step.needs),
                    "inputs": dict(step.inputs),
                    "params": dict(step.params),
                }
                for step in order
            ],
        }

    def _order_through(
        self, order: list[RecipeStep], through: str | None
    ) -> list[RecipeStep]:
        if through is None:
            return order
        by_id = {step.id: step for step in order}
        if through not in by_id:
            raise RecipeError(f"Unknown or disabled step: {through}")
        needed: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in needed:
                return
            needed.add(step_id)
            for dependency in by_id[step_id].needs:
                visit(dependency)

        visit(through)
        return [step for step in order if step.id in needed]

    def _llm_from_provider(
        self, provider: dict[str, object], log: Any | None
    ) -> Any | None:
        base_url = str(provider.get("base_url") or "").strip()
        model = str(provider.get("model") or "").strip()
        if not base_url or not model:
            return None
        from videoflow.application.secrets import get_secret
        from videoflow.application.settings import load_settings

        settings = load_settings().llm
        return OpenAICompatibleLlm(
            base_url=base_url,
            model=model,
            api_key=get_secret(str(provider.get("api_key_env") or "")),
            timeout=settings.timeout_seconds,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            retries=settings.retries,
        )

    def _build_llm(self, log: Any | None) -> Any | None:
        config = self.recipe.llm
        if config.provider == "none":
            return None
        base_url = config.base_url or os.environ.get("VIDEOWFLOW_LLM_BASE_URL")
        model = config.model or os.environ.get("VIDEOWFLOW_LLM_MODEL", "")
        if not base_url or not model:
            try:
                from videoflow.application.providers import first_provider

                provider = first_provider("llm") or {}
            except Exception:
                provider = {}
            base_url = base_url or str(provider.get("base_url") or "")
            model = model or str(provider.get("model") or "")
        if config.provider in {"auto", "opencode_v2", "deepseek"}:
            from videoflow.application.intelligence import (
                IntelligenceLlmAdapter,
                build_intelligence,
            )

            intelligence = build_intelligence()
            if config.provider == "auto":
                from videoflow.application.llm_factory import build_llm

                return build_llm()
            return IntelligenceLlmAdapter(
                intelligence, provider_id=config.provider
            )
        if config.provider in {"opencode", "opencode_cli"}:
            from videoflow.adapters.opencode import OpenCodeLlm

            return OpenCodeLlm(
                binary=os.environ.get("VIDEOWFLOW_OPENCODE_BIN", "opencode"),
                model=model or "default",
                timeout=config.timeout_seconds,
                log=log,
            )
        if not base_url or not model:
            if log is not None:
                log(
                    "llm",
                    "warning",
                    "LLM provider requested without base_url/model; continuing without it",
                )
            return None
        from videoflow.application.secrets import get_secret
        from videoflow.application.settings import load_settings

        llm_settings = load_settings().llm
        return OpenAICompatibleLlm(
            base_url=base_url,
            model=model,
            api_key=get_secret(config.api_key_env),
            timeout=config.timeout_seconds or llm_settings.timeout_seconds,
            temperature=llm_settings.temperature,
            max_tokens=llm_settings.max_tokens,
            retries=llm_settings.retries,
        )
