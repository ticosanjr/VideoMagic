from __future__ import annotations

import subprocess
from pathlib import Path

from gpu_worker import repair


def test_repair_uninstalls_both_distributions_and_forces_gpu(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []
    statuses = iter(
        [
            {"ok": False, "version": "", "providers": [], "error": "broken"},
            {"ok": True, "version": "1.20.2", "providers": ["CPUExecutionProvider"], "error": ""},
        ]
    )

    def runner(args, **kwargs):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(repair, "onnx_status", lambda: next(statuses))
    monkeypatch.setattr(repair, "_purelib", lambda: tmp_path)
    (tmp_path / "onnxruntime").mkdir()
    (tmp_path / "onnxruntime-1.31.0.dist-info").mkdir()
    result = repair.repair_onnx(runner=runner, python="/venv/python")
    assert result["ok"] is True
    assert not (tmp_path / "onnxruntime").exists()
    flattened = [" ".join(item) for item in calls]
    assert any("uninstall" in item and "onnxruntime-gpu" in item for item in flattened)
    assert any(
        "--force-reinstall" in item and "onnxruntime-gpu==1.20.2" in item
        for item in flattened
    )


def test_onnx_status_marks_missing_session_api(monkeypatch) -> None:
    import sys
    import types

    fake = types.SimpleNamespace(__version__="1.20.2", get_available_providers=lambda: [])
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    status = repair.onnx_status()
    assert status["ok"] is False
    assert "SessionOptions" in status["error"]
