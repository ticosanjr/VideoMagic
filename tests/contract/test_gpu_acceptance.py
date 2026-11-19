from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.gpu_acceptance import main


def test_gpu_acceptance_blocks_without_a_worker(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "acceptance.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["gpu_acceptance.py", "--json-out", str(target)],
    )
    assert main() == 2
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["checks"] == {}
    assert "worker-url" in payload["message"]
