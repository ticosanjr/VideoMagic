from __future__ import annotations

from videoflow.application.preflight_plan import _compute_plan


def test_decupage_compute_plan_routes_remote_stages() -> None:
    gpu = {
        "available": True,
        "capabilities": ["asr", "forced_align", "render_nvenc"],
    }
    plan = _compute_plan("decupage", gpu, {"compute_policy": "auto"})
    stages = {item["stage"]: item for item in plan["stages"]}
    assert stages["audio.events"]["placement"] == "local"
    assert stages["transcribe"]["placement"] == "remote_gpu"
    assert stages["alignment.forced"]["placement"] == "remote_gpu"
    assert stages["decupage.llm"]["placement"] == "llm"
    assert stages["export.nle"]["placement"] == "remote_gpu"
    assert plan["degraded"] is False


def test_decupage_compute_plan_marks_local_fallback() -> None:
    plan = _compute_plan(
        "decupage",
        {"available": False, "capabilities": []},
        {"compute_policy": "auto"},
    )
    stages = {item["stage"]: item for item in plan["stages"]}
    assert stages["transcribe"]["placement"] == "local"
    assert stages["transcribe"]["degraded"] is True
    assert plan["degraded"] is True


def test_scene_and_short_stages_can_be_offloaded() -> None:
    gpu = {
        "available": True,
        "capabilities": ["scene_analyze", "short_render"],
    }
    scenes = _compute_plan("scenes", gpu, {"compute_policy": "auto"})
    scene_stages = {item["stage"]: item for item in scenes["stages"]}
    assert scene_stages["scene.detect"]["placement"] == "remote_gpu"
    assert scene_stages["scene.layout"]["placement"] == "remote_gpu"

    shorts = _compute_plan("shorts_compose", gpu, {"compute_policy": "auto"})
    short_stages = {item["stage"]: item for item in shorts["stages"]}
    assert short_stages["short.plan"]["placement"] == "llm"
    assert short_stages["short.render"]["placement"] == "remote_gpu"


def test_decupage_compute_plan_local_policy_never_uses_remote() -> None:
    plan = _compute_plan(
        "decupage",
        {"available": True, "capabilities": ["asr", "forced_align"]},
        {"compute_policy": "local_only"},
    )
    assert all(
        item["placement"] in {"local", "llm"} for item in plan["stages"]
    )
    assert plan["degraded"] is False
