"""Legacy rack planning.

Execution belongs to the recipe engine; this module only plans which legacy rack
modules would need to run.
"""

from __future__ import annotations

from videoflow.domain.planning import RunPlan, plan_run


class PipelineRunner:
    """Plan a legacy rack run; execution is owned by the recipe engine."""

    def plan(
        self,
        status: dict[str, str],
        *,
        target: str | None = None,
        run_upstream: bool = False,
        enabled: dict[str, bool] | None = None,
    ) -> RunPlan:
        return plan_run(status, target=target, run_upstream=run_upstream, enabled=enabled)
