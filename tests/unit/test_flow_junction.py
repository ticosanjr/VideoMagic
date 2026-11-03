from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.flow import JunctionParams, JunctionStep
from videoflow.steps.ports import ports_for_type


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    work = output / "work"
    exports = output / "exports"
    for directory in (output, work, exports):
        directory.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    return PipelineContext(source=source, output=output, work=work, exports=exports)


def test_junction_exposes_many_inputs_and_one_output() -> None:
    inputs, outputs = ports_for_type("flow.junction")
    assert [port.id for port in inputs] == [f"in{index}" for index in range(1, 9)]
    assert [port.id for port in outputs] == ["out"]


def test_junction_select_merge_lists_and_merge_dicts(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.metadata["junction_in1"] = [1, 2]
    context.metadata["junction_in2"] = [3]
    step = JunctionStep()

    step.run(context, JunctionParams(mode="select", selected_input="in2"), StepIO())
    assert context.metadata["junction_out"] == [3]

    step.run(context, JunctionParams(mode="merge_lists"), StepIO())
    assert context.metadata["junction_out"] == [1, 2, 3]

    step.run(context, JunctionParams(mode="merge_dicts"), StepIO())
    assert context.metadata["junction_out"] == {"in1": [1, 2], "in2": [3]}
