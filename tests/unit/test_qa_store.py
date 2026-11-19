from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.qa_store import QaStore


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "exports" / "short_01.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake-video")
    return path


def _report(*, lufs: float, wer: float) -> dict:
    return {
        "ok": True,
        "status": "succeeded",
        "duration": {"frame_delta": 0},
        "loudness": {"integrated_lufs": lufs},
        "word_fidelity": {"wer": wer},
        "issues": [{"kind": "overlay_overlap", "overlap_px": 0}],
    }


def test_qa_store_writes_immutable_report_and_latest(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    store = QaStore(tmp_path)
    reference = store.write(artifact, _report(lufs=-16.1, wer=0.04), run_id="run-1")

    report_path = Path(reference["report_path"])
    assert report_path.is_file()
    assert reference["artifact_slug"] == "short-01"
    assert reference["status"] == "passed"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-1"
    assert payload["artifact_sha256"]
    assert store.read(artifact, "run-1")["status"] == "passed"
    latest = store.latest(artifact)
    assert latest is not None
    assert latest["run_id"] == "run-1"

    second = store.write(artifact, _report(lufs=-16.0, wer=0.03), run_id="run-2")
    assert Path(second["report_path"]).is_file()
    assert Path(reference["report_path"]).is_file()
    assert store.latest(artifact)["run_id"] == "run-2"


def test_qa_compare_reports_loudness_and_wer_regressions(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    store = QaStore(tmp_path)
    first = store.write(artifact, _report(lufs=-16.1, wer=0.04), run_id="run-a")
    second = store.write(artifact, _report(lufs=-17.8, wer=0.11), run_id="run-b")

    comparison = store.compare(first["report_path"], second["report_path"])

    assert comparison["ok"] is True
    assert "wer" in comparison["regressions"]
    assert "integrated_lufs" in comparison["regressions"]
    assert comparison["deltas"]["wer"] > 0
