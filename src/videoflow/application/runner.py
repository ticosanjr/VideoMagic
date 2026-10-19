"""Pipeline runner. Planning is implemented; execution is not."""

from __future__ import annotations

from videoflow.domain.planning import RunPlan, plan_run
from videoflow.domain.state import ProjectState


class PipelineRunner:
    """Owns one project run. ``execute`` is intentionally unimplemented."""

    def plan(
        self,
        status: dict[str, str],
        *,
        target: str | None = None,
        run_upstream: bool = False,
        enabled: dict[str, bool] | None = None,
    ) -> RunPlan:
        return plan_run(status, target=target, run_upstream=run_upstream, enabled=enabled)

    def execute(self, state: ProjectState, plan: RunPlan) -> ProjectState:
        raise NotImplementedError("pipeline execution is not implemented in this scaffold")
