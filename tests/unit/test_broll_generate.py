from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from videoflow.core.context import PipelineContext
from videoflow.steps import broll_generate as generate_module
from videoflow.steps.base import StepIO
from videoflow.steps.broll_generate import GenerateBrollParams, GenerateBrollStep


def test_generate_broll_writes_assets_and_license(tmp_path: Path, monkeypatch) -> None:
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
    )
    context.selected_shorts = [SimpleNamespace(title="Court evidence")]

    target = tmp_path / "images" / "generated.png"

    def fake_save(name: str, data: bytes):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"file": str(target), "name": target.name, "sha256": "abc123"}

    monkeypatch.setattr(
        generate_module,
        "generate_image",
        lambda *args, **kwargs: b"\x89PNG\r\n\x1a\nimage",
    )
    monkeypatch.setattr(generate_module, "save_image", fake_save)
    monkeypatch.setattr(generate_module, "images_dir", lambda: target.parent)
    monkeypatch.setattr(generate_module, "scan_directory", lambda *args, **kwargs: [])
    GenerateBrollStep().run(
        context,
        GenerateBrollParams(
            base_url="http://127.0.0.1:8188/v1",
            count=1,
            allow_external_services=True,
        ),
        StepIO(),
    )
    generated = context.metadata["generated_broll"]
    assert generated[0]["path"] == str(target)
    assert Path(context.artifacts["generated_broll"]).is_file()
    ledger = tmp_path / "out" / "assets" / "licenses.json"
    assert ledger.is_file()
    assert "generated" in ledger.read_text()
