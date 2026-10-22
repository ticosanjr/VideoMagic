import os
import time
from pathlib import Path

from videoflow.engine.history import append_run, read_runs
from videoflow.engine.maintenance import prune_output


def test_prune_keeps_newest_checkpoints(tmp_path: Path) -> None:
    steps = tmp_path / "work" / "steps"
    steps.mkdir(parents=True)
    for index in range(5):
        directory = steps / f"step{index}"
        directory.mkdir()
        (directory / "snapshot.json").write_text("{}")
        timestamp = time.time() - (5 - index) * 60
        directory.touch()
        os.utime(directory, (timestamp, timestamp))
    result = prune_output(tmp_path, keep_steps=2)
    assert result["ok"] is True
    assert len(list(steps.iterdir())) == 2
    assert result["freed_bytes"] > 0
    assert {item["kind"] for item in result["removed"]} == {"checkpoint"}


def test_prune_trims_history(tmp_path: Path) -> None:
    for index in range(8):
        append_run(
            tmp_path,
            {
                "job_id": f"j{index}",
                "status": "succeeded",
                "recipe_id": "r",
                "created_at": str(index),
            },
        )
    result = prune_output(tmp_path, keep_runs=3)
    assert result["trimmed_runs"] == 5
    assert len(read_runs(tmp_path)) == 3


def test_prune_dry_run_does_not_delete(tmp_path: Path) -> None:
    steps = tmp_path / "work" / "steps"
    steps.mkdir(parents=True)
    for index in range(3):
        (steps / f"step{index}").mkdir()
    result = prune_output(tmp_path, keep_steps=1, dry_run=True)
    assert len(list(steps.iterdir())) == 3
    assert result["dry_run"] is True
