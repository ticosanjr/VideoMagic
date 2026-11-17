"""Headless MCP surface, recipes, sync, render gate, and self-heal."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from videoflow.application.render_gate import RenderGate
from videoflow.application.sync import onset_offset_ms, shift_sentences
from videoflow.application.web_preview import PreviewServer
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import SelfHealRequiredError
from videoflow.domain.headless import BeatMap
from videoflow.domain.state import Sentence, WordTiming
from videoflow.engine.recipes.catalog import get_recipe
from videoflow.mcp_server.registry import RESOURCE_SPECS, TOOL_SPECS
from videoflow.steps.base import BaseStep, EmptyParams, StepIO
from videoflow.steps.ports import validate_recipe_ports
from videoflow.steps.registry import register_step, requirements_by_type, step_types
from videoflow.steps.self_heal import SelfHealParams, SelfHealStep


def _context(tmp: Path) -> PipelineContext:
    output = tmp / "out"
    work = output / "work"
    work.mkdir(parents=True)
    source = tmp / "source.mp4"
    source.write_bytes(b"fixture")
    return PipelineContext(
        source=source,
        output=output,
        work=work,
        exports=output / "exports",
    )


def test_mcp_surface_has_13_core_tools_and_13_resources() -> None:
    assert len(TOOL_SPECS) == 13
    assert len(RESOURCE_SPECS) == 13
    assert {spec.name for spec in TOOL_SPECS} >= {
        "vf_project",
        "vf_style",
        "vf_catalog_search",
        "vf_exec",
        "vf_job",
        "vf_ingest",
        "vf_qa",
        "vf_render",
    }


@pytest.mark.parametrize(
    "recipe_id",
    (
        "opencode_longform_studio",
        "opencode_reels_from_raw",
        "opencode_shorts_batch_from_long",
        "opencode_clone_style",
    ),
)
def test_headless_recipes_validate(recipe_id: str) -> None:
    recipe = get_recipe(recipe_id)
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    validate_recipe_ports(recipe)
    assert recipe.steps


def test_beat_map_round_trip() -> None:
    beat_map = BeatMap.model_validate(
        {
            "project_id": "demo",
            "scenes": [{"id": "s1", "start_sec": 0.0, "end_sec": 2.0, "visual": "hook"}],
        }
    )
    assert beat_map.scenes[0].archetype == "talking_head"


def test_sync_offset_and_shift() -> None:
    sentence = Sentence(
        id=0,
        start_sample=200,
        end_sample=500,
        text="hello",
        words=[WordTiming(word="hello", start_sample=200, end_sample=500, probability=0.9)],
    )
    offset = onset_offset_ms([sentence], [(0, 500)], 1000)
    assert offset == 200
    shifted = shift_sentences([sentence], -200, 1000)
    assert shifted[0].start_sample == 0
    assert shifted[0].words[0].start_sample == 0


def test_render_gate_serialises_workers(tmp_path: Path) -> None:
    gate = RenderGate(path=tmp_path / "render.lock")
    active = 0
    peak = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal active, peak
        with gate.hold("test", "job"):
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak == 1


def test_preview_server_serves_only_token_prefix(tmp_path: Path) -> None:
    scene = tmp_path / "scene"
    scene.mkdir()
    (scene / "index.html").write_text("<h1>scene</h1>", encoding="utf-8")
    server = PreviewServer()
    url = server.start(scene)
    try:
        body = urllib.request.urlopen(url + "index.html", timeout=2).read()
        assert b"scene" in body
        base = url.rsplit("/", 2)[0]
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/index.html", timeout=2)
    finally:
        server.stop()


@register_step
class _SelfHealProbe(BaseStep):
    type = "test.self_heal_probe"
    title = "Self-heal probe"
    params_model = EmptyParams
    calls = 0

    def run(self, context: PipelineContext, params: EmptyParams, io: StepIO) -> None:
        type(self).calls += 1


def test_self_heal_success_writes_metadata(tmp_path: Path) -> None:
    context = _context(tmp_path)
    step = SelfHealStep()
    step.run(
        context,
        SelfHealParams(target_step="test.self_heal_probe", max_attempts=1),
        StepIO(),
    )
    assert context.metadata["self_heal"]["ok"] is True


def test_self_heal_exhaustion_writes_repair_report(tmp_path: Path) -> None:
    context = _context(tmp_path)
    step = SelfHealStep()
    with pytest.raises(SelfHealRequiredError) as exc:
        step.run(
            context,
            SelfHealParams(
                target_step="transcribe",
                target_params={"mode": "srt", "srt_path": str(tmp_path / "missing.srt")},
                max_attempts=1,
            ),
            StepIO(),
        )
    report = json.loads((context.work / "self_heal_report.json").read_text())
    assert report["step"] == "transcribe"
    assert exc.value.report["code"]
