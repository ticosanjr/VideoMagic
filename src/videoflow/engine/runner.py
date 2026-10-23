"""Recipe runner: validate a DAG, execute steps, checkpoint, and persist."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from videoflow.adapters.llm import OpenAICompatibleLlm
from videoflow.core.context import PipelineContext
from videoflow.core.recipe import Recipe, RecipeStep
from videoflow.domain.errors import RecipeError, StepExecutionError, VideoFlowError
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
from videoflow.steps import get_step, requirements_by_type, step_types
from videoflow.steps.base import StepIO
from videoflow.steps.cache import cache_key

StepStatus = Literal["cached", "executed", "skipped"]


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
    ) -> None:
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        self.recipe = recipe
        self.adapter = adapter
        self.llm_client = llm_client
        self.asr_client = asr_client

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
    ) -> RecipeRunResult:
        from uuid import uuid4

        started = time.perf_counter()
        source_path = Path(source).expanduser().resolve()
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
            metadata={"run_id": str(uuid4())},
        )
        order = self._order_through(self.recipe.topological_order(), through)
        llm = self.llm_client or self._build_llm(log)
        total = len(order)
        step_runs: list[StepRun] = []

        for index, recipe_step in enumerate(order, start=1):
            step = get_step(recipe_step.type)
            params = step.validate_params(recipe_step.params)
            fingerprint = cache_key(
                {
                    "checkpoint": CHECKPOINT_VERSION,
                    "step_id": recipe_step.id,
                    "type": step.type,
                    "version": step.version,
                    "params": params.model_dump(mode="json"),
                    "source": context.pcm_digest or source_stamp,
                    "upstream": {
                        dependency: context.hashes.get(dependency, "")
                        for dependency in recipe_step.needs
                    },
                }
            )
            io = StepIO(
                stage=recipe_step.id,
                index=index,
                total=total,
                adapter=self.adapter,
                llm_client=llm,
                asr_client=self.asr_client,
                progress=progress,
                step_progress=step_progress,
                should_cancel=should_cancel,
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
                if step_progress is not None:
                    step_progress(recipe_step.id, 100, f"{step.title} bypassed")
                io.report(100, f"{step.title} bypassed")
                continue

            if resume:
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
                    io.report(100, "Cached checkpoint reused")
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
            try:
                step.run(context, params, io)
            except Exception as exc:
                if telemetry is not None:
                    telemetry.fail(recipe_step.id, str(exc))
                context.metadata["failed_step"] = recipe_step.id
                if isinstance(exc, VideoFlowError):
                    raise
                raise StepExecutionError(recipe_step.id, str(exc)) from exc
            elapsed_ms = int((time.perf_counter() - step_started) * 1000)
            context.metadata.setdefault("step_progress", {})[recipe_step.id] = 100
            if step_progress is not None:
                step_progress(recipe_step.id, 100, f"{step.title} ready")
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
        if context.state is not None:
            write_text(state_path, context.state.model_dump_json(indent=2) + "\n")
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
        write_text(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
        if progress is not None:
            progress("done", 100, "Finished")
        return result

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

    def _build_llm(self, log: Any | None) -> Any | None:
        config = self.recipe.llm
        if config.provider == "none":
            return None
        base_url = config.base_url or os.environ.get("VIDEOWFLOW_LLM_BASE_URL")
        model = config.model or os.environ.get("VIDEOWFLOW_LLM_MODEL", "")
        if config.provider == "opencode":
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
        return OpenAICompatibleLlm(
            base_url=base_url,
            model=model,
            api_key=os.environ.get(config.api_key_env),
            timeout=config.timeout_seconds,
        )
