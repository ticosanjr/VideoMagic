"""Recipe runner: validate a DAG, execute steps, persist artifacts."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videoflow.adapters.llm import OpenAICompatibleLlm
from videoflow.core.context import PipelineContext
from videoflow.core.recipe import Recipe
from videoflow.domain.errors import StepExecutionError, VideoFlowError
from videoflow.exporters.common import write_text
from videoflow.steps import get_step, step_types
from videoflow.steps.base import StepIO


@dataclass(frozen=True, slots=True)
class RecipeRunResult:
    recipe_id: str
    context: PipelineContext
    elapsed_seconds: float
    state_path: Path
    report_path: Path

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "ok": True,
            "mode": "recipe",
            "recipe_id": self.recipe_id,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "state_path": str(self.state_path),
            "report_path": str(self.report_path),
            **self.context.summary(),
        }
        payload["shorts"] = list(self.context.shorts)
        return payload


class RecipeRunner:
    """Execute one recipe for one source file."""

    def __init__(
        self,
        recipe: Recipe,
        *,
        adapter: Any | None = None,
        llm_client: Any | None = None,
        asr_client: Any | None = None,
    ) -> None:
        recipe.validate_graph(step_types())
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
        should_cancel: Any | None = None,
        log: Any | None = None,
        telemetry: Any | None = None,
        transcript_sentences: list[Any] | None = None,
    ) -> RecipeRunResult:
        from uuid import uuid4

        started = time.perf_counter()
        source_path = Path(source).expanduser().resolve()
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
        order = self.recipe.topological_order()
        llm = self.llm_client or self._build_llm(log)
        total = len(order)
        for index, recipe_step in enumerate(order, start=1):
            step = get_step(recipe_step.type)
            io = StepIO(
                stage=recipe_step.id,
                index=index,
                total=total,
                adapter=self.adapter,
                llm_client=llm,
                asr_client=self.asr_client,
                progress=progress,
                should_cancel=should_cancel,
                log=log,
            )
            if telemetry is not None:
                telemetry.start(
                    recipe_step.id,
                    recipe_step.type,
                    step.title,
                    f"Running {step.title}",
                )
            io.check_cancel()
            try:
                params = step.validate_params(recipe_step.params)
                step.run(context, params, io)
            except Exception as exc:
                if telemetry is not None:
                    telemetry.fail(recipe_step.id, str(exc))
                context.metadata["failed_step"] = recipe_step.id
                if isinstance(exc, VideoFlowError):
                    raise
                raise StepExecutionError(recipe_step.id, str(exc)) from exc
            else:
                if telemetry is not None:
                    telemetry.finish(recipe_step.id, f"{step.title} ready")

        state_path = output_path / "project_state.json"
        if context.state is not None:
            write_text(state_path, context.state.model_dump_json(indent=2) + "\n")
        else:
            state_path = output_path / "project_state.json"
        report_path = output_path / "run.json"
        result = RecipeRunResult(
            recipe_id=self.recipe.id,
            context=context,
            elapsed_seconds=time.perf_counter() - started,
            state_path=state_path,
            report_path=report_path,
        )
        report = result.to_dict()
        report["recipe"] = self.recipe.model_dump(mode="json")
        report["steps"] = [
            {"id": step.id, "type": step.type, "needs": step.needs}
            for step in self.recipe.steps
        ]
        report["hashes"] = dict(context.hashes)
        write_text(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
        if progress is not None:
            progress("done", 100, "Finished")
        return result

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
