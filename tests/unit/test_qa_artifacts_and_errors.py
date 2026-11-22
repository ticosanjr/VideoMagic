from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from videoflow.api.errors import STATUS_BY_CODE, status_for
from videoflow.api.routes_jobs import _job_event_stream
from videoflow.application import artifacts


def test_qa_artifacts_reads_work_and_exports(tmp_path: Path) -> None:
    work = tmp_path / "work" / "qa"
    work.mkdir(parents=True)
    (work / "qa_report.json").write_text(
        json.dumps(
            {
                "ok": False,
                "defects": [{"kind": "overlap", "path": "a.png"}],
            }
        ),
        encoding="utf-8",
    )
    exports = tmp_path / "exports" / "qa" / "video"
    exports.mkdir(parents=True)
    (exports / "final_qa.json").write_text(
        json.dumps(
            {
                "ok": False,
                "issues": [{"kind": "loudness", "message": "out of spec"}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "exports" / "qa" / "broken.json").write_text("{", encoding="utf-8")

    payload = artifacts.qa_artifacts(tmp_path)

    assert payload["reports"]["qa_report"]["ok"] is False
    assert payload["reports"]["final_qa"]["issues"][0]["kind"] == "loudness"
    assert payload["reports"]["broken"] == {"error": "unreadable"}
    kinds = {item.get("kind") for item in payload["defects"]}
    assert {"overlap", "loudness"} <= kinds


def test_new_v4_http_codes() -> None:
    expected = {
        "precondition_failed": 412,
        "gpu_worker_offline": 503,
        "gpu_required_for_operation": 503,
        "alpha_channel_missing": 422,
        "insufficient_contiguous_speech": 422,
        "beatmap_conflict": 409,
        "insufficient_disk_space": 507,
    }
    for code, status in expected.items():
        assert STATUS_BY_CODE[code] == status
        assert status_for(code) == status


def test_job_stream_is_async_and_emits_terminal_job() -> None:
    job = SimpleNamespace(
        to_dict=lambda: {
            "status": "succeeded",
            "progress": 100,
            "stage": "done",
            "job_id": "j1",
        }
    )

    async def collect() -> list[str]:
        return [chunk async for chunk in _job_event_stream(job)]

    chunks = asyncio.run(collect())
    assert chunks
    assert '"status": "succeeded"' in chunks[0]
