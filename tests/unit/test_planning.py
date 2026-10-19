import pytest

from videoflow.domain.constants import MODULE_ORDER
from videoflow.domain.errors import (
    JobAlreadyRunningError,
    ModuleBypassedError,
    UpstreamDirtyError,
)
from videoflow.domain.planning import (
    CacheStatus,
    UnknownModuleError,
    plan_run,
)


def all_status(value: CacheStatus | str) -> dict[str, CacheStatus | str]:
    return {name: value for name in MODULE_ORDER}


def test_full_run_executes_everything_when_nothing_is_cached() -> None:
    plan = plan_run(all_status(CacheStatus.MISSING))
    assert plan.modules == MODULE_ORDER
    assert plan.skipped == ()


def test_full_run_skips_cached_and_bypassed_modules() -> None:
    status = all_status(CacheStatus.MISSING)
    status["ingest"] = CacheStatus.CACHED
    status["vad"] = CacheStatus.BYPASSED
    plan = plan_run(status)
    assert "ingest" not in plan.modules
    assert "vad" not in plan.modules
    assert plan.skipped == ("ingest", "vad")


def test_full_run_respects_disabled_modules() -> None:
    enabled = {name: name != "zooms" for name in MODULE_ORDER}
    plan = plan_run(all_status(CacheStatus.MISSING), enabled=enabled)
    assert "zooms" in plan.skipped
    assert "zooms" not in plan.modules


def test_single_module_run_is_allowed_when_upstream_is_cached() -> None:
    status = all_status(CacheStatus.CACHED)
    status["zooms"] = CacheStatus.DIRTY
    plan = plan_run(status, target="zooms")
    assert plan.modules == ("zooms",)
    assert "ingest" in plan.skipped


def test_single_cached_module_is_a_no_op() -> None:
    plan = plan_run(all_status(CacheStatus.CACHED), target="zooms")
    assert plan.modules == ()
    assert plan.skipped == ("zooms",)


def test_dirty_upstream_blocks_a_single_module_run() -> None:
    status = all_status(CacheStatus.CACHED)
    status["transcribe"] = CacheStatus.DIRTY
    status["zooms"] = CacheStatus.MISSING
    with pytest.raises(UpstreamDirtyError) as caught:
        plan_run(status, target="zooms")
    assert caught.value.ancestors == ("transcribe",)
    assert caught.value.to_dict()["target"] == "zooms"


def test_run_upstream_option_expands_the_plan_and_skips_cached_ancestors() -> None:
    status = all_status(CacheStatus.CACHED)
    status["transcribe"] = CacheStatus.DIRTY
    status["zooms"] = CacheStatus.MISSING
    plan = plan_run(status, target="zooms", run_upstream=True)
    assert plan.modules == ("transcribe", "zooms")
    assert "ingest" in plan.skipped


def test_run_upstream_includes_a_dirty_target_behind_clean_ancestors() -> None:
    status = all_status(CacheStatus.CACHED)
    status["vad"] = CacheStatus.DIRTY
    status["retakes"] = CacheStatus.MISSING
    plan = plan_run(status, target="retakes", run_upstream=True)
    assert plan.modules == ("vad", "retakes")


def test_bypassed_ancestors_do_not_block_a_single_module() -> None:
    status = all_status(CacheStatus.CACHED)
    status["vad"] = CacheStatus.BYPASSED
    status["zooms"] = CacheStatus.MISSING
    plan = plan_run(status, target="zooms")
    assert plan.modules == ("zooms",)


def test_disabled_ancestors_are_not_ancestors() -> None:
    status = all_status(CacheStatus.CACHED)
    status["vad"] = CacheStatus.DIRTY
    status["zooms"] = CacheStatus.MISSING
    enabled = {name: name != "vad" for name in MODULE_ORDER}
    plan = plan_run(status, target="zooms", enabled=enabled)
    assert plan.modules == ("zooms",)


def test_disabled_target_cannot_be_run_directly() -> None:
    enabled = {name: name != "zooms" for name in MODULE_ORDER}
    with pytest.raises(ModuleBypassedError):
        plan_run(all_status(CacheStatus.MISSING), target="zooms", enabled=enabled)


def test_bypassed_target_cannot_be_run_directly() -> None:
    status = all_status(CacheStatus.MISSING)
    status["zooms"] = CacheStatus.BYPASSED
    with pytest.raises(ModuleBypassedError):
        plan_run(status, target="zooms")


def test_unknown_module_is_reported() -> None:
    with pytest.raises(UnknownModuleError):
        plan_run(all_status(CacheStatus.CACHED), target="colour_grade")


def test_a_running_project_refuses_a_second_job() -> None:
    status = all_status(CacheStatus.CACHED)
    status["vad"] = CacheStatus.RUNNING
    with pytest.raises(JobAlreadyRunningError) as caught:
        plan_run(status)
    assert caught.value.to_dict()["code"] == "job_already_running"


def test_string_status_values_are_coerced() -> None:
    plan = plan_run({name: "dirty" for name in MODULE_ORDER})
    assert plan.modules == MODULE_ORDER


def test_missing_keys_default_to_missing() -> None:
    plan = plan_run({})
    assert plan.modules == MODULE_ORDER


def test_blocks_are_treated_as_needing_work() -> None:
    status = all_status(CacheStatus.CACHED)
    status["ingest"] = CacheStatus.BLOCKED
    plan = plan_run(status)
    assert plan.modules == ("ingest",)


def test_failed_modules_need_work() -> None:
    status = all_status(CacheStatus.CACHED)
    status["zooms"] = CacheStatus.FAILED
    plan = plan_run(status)
    assert plan.modules == ("zooms",)


def test_upstream_error_without_ancestors_reads_cleanly() -> None:
    error = UpstreamDirtyError("ingest", [])
    assert "none" in str(error)


def test_last_module_can_run_when_every_ancestor_is_cached() -> None:
    status = all_status(CacheStatus.CACHED)
    status["export"] = CacheStatus.DIRTY
    plan = plan_run(status, target="export")
    assert plan.modules == ("export",)
    assert "shorts" in plan.skipped


def test_module_enabled_map_round_trips() -> None:
    from videoflow.domain.config import ModuleEnabled

    assert ModuleEnabled().as_map()["ingest"] is True
