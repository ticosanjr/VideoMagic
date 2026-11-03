from __future__ import annotations

from pathlib import Path

from videoflow.application.step_outputs import (
    jsonable,
    load_step_outputs,
    save_step_outputs,
    step_output_port,
    summarize_step_outputs,
    write_step_outputs,
)
from videoflow.steps.base import PortSpec


class Sample:
    def model_dump(self, mode: str = "python") -> dict[str, object]:
        return {"mode": mode, "ok": True}


def test_step_outputs_roundtrip_and_save(tmp_path: Path) -> None:
    output = tmp_path / "out"
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video")
    write_step_outputs(
        output,
        step_id="ingest",
        step_type="ingest",
        status="executed",
        fingerprint="abc",
        ports={"media": {"path": str(media)}, "sample": Sample()},
        port_specs=[
            PortSpec("media", "Media", "media", "media"),
            PortSpec("sample", "Sample", "json", "sample"),
        ],
        hashes={"media": "h1", "sample": "h2"},
        files=[str(media)],
        artifacts={"clip": str(media)},
        elapsed_ms=12,
    )
    payload = load_step_outputs(output, "ingest")
    assert payload is not None
    summary = summarize_step_outputs(payload)
    assert summary["step_id"] == "ingest"
    assert [item["id"] for item in summary["ports"]] == ["media", "sample"]
    assert summary["ports"][0]["size_bytes"] > 0
    assert summary["files"][0]["name"] == "clip.mp4"
    port = step_output_port(payload, "sample")
    assert port is not None
    assert port["value"] == {"mode": "json", "ok": True}

    target = tmp_path / "saved"
    saved = save_step_outputs(output, "ingest", target)
    assert len(saved) == 2
    assert (target / "ingest-outputs.json").is_file()
    assert (target / "clip.mp4").read_bytes() == b"video"


def test_jsonable_handles_paths_and_unknown_values(tmp_path: Path) -> None:
    assert jsonable(tmp_path) == str(tmp_path)
    assert jsonable({"a": (1, 2)}) == {"a": [1, 2]}
    assert jsonable(object()).startswith("<object object at")
    assert load_step_outputs(tmp_path, "missing") is None
    assert summarize_step_outputs({})["ports"] == []
