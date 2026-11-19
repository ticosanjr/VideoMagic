from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.projects import init_project, save_project_state
from videoflow.application.revisions import list_snapshots
from videoflow.domain.errors import TimelineConflict


def test_timeline_conflict_and_reset_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    record, state = init_project(name="Guard", output=tmp_path / "out")
    first = save_project_state(record, state, bump_revision=True)
    assert first.revision == state.revision + 1

    with pytest.raises(TimelineConflict):
        save_project_state(record, first, expected_revision=state.revision)

    reset = save_project_state(
        record,
        first,
        expected_revision=state.revision,
        reset=True,
        snapshot_reason="test_reset",
        snapshot_step="test",
    )
    assert reset.revision == first.revision + 1
    snapshots = list_snapshots(record.output)
    assert snapshots
    assert snapshots[0]["reason"] == "test_reset"
