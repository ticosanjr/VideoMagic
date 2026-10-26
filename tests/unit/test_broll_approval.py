"""B-roll approval ordering, validation, and undo/redo history."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application import broll_approval
from videoflow.domain.errors import StateNotReadyError

PLAN = {
    "Opening": [
        {"asset": "a.mp4", "start": 0},
        {"asset": "b.mp4", "start": 5},
        {"asset": "c.mp4", "start": 9},
    ]
}


def test_save_clamps_and_completes_the_order(tmp_path: Path) -> None:
    approvals = broll_approval.save_approval(
        tmp_path,
        title="Opening",
        approved=[2, 0, 2, 9, -1],
        order=[2],
        plan=PLAN,
    )

    assert approvals["Opening"] == {"approved": [0, 2], "order": [2, 0]}
    assert broll_approval.load_approvals(tmp_path) == approvals


def test_save_requires_a_title_and_a_known_plan(tmp_path: Path) -> None:
    with pytest.raises(StateNotReadyError, match="needs a Short title"):
        broll_approval.save_approval(tmp_path, title="  ", approved=[])

    with pytest.raises(StateNotReadyError, match="Unknown B-roll plan"):
        broll_approval.save_approval(
            tmp_path, title="Missing", approved=[], plan=PLAN
        )


def test_an_empty_plan_entry_is_allowed(tmp_path: Path) -> None:
    approvals = broll_approval.save_approval(
        tmp_path, title="Opening", approved=[0], plan={"Opening": []}
    )

    assert approvals["Opening"] == {"approved": [], "order": []}


def test_load_ignores_corrupt_files_and_bad_entries(tmp_path: Path) -> None:
    assert broll_approval.load_approvals(tmp_path) == {}

    (tmp_path / "broll_approval.json").write_text("not json", encoding="utf-8")
    assert broll_approval.load_approvals(tmp_path) == {}

    (tmp_path / "broll_approval.json").write_text("[]", encoding="utf-8")
    assert broll_approval.load_approvals(tmp_path) == {}

    (tmp_path / "broll_approval.json").write_text(
        json.dumps(
            {
                "Good": {"approved": [0, "x"], "order": []},
                "Bad": "not a dict",
            }
        ),
        encoding="utf-8",
    )
    assert broll_approval.load_approvals(tmp_path) == {
        "Good": {"approved": [0], "order": [0]}
    }


def test_undo_and_redo_round_trip(tmp_path: Path) -> None:
    broll_approval.save_approval(tmp_path, title="Opening", approved=[0], plan=PLAN)
    broll_approval.save_approval(tmp_path, title="Opening", approved=[1], plan=PLAN)

    undone = broll_approval.undo_approval(tmp_path)
    assert undone["Opening"]["approved"] == [0]

    redone = broll_approval.redo_approval(tmp_path)
    assert redone["Opening"]["approved"] == [1]

    assert broll_approval.undo_approval(tmp_path)["Opening"]["approved"] == [0]
    assert broll_approval.undo_approval(tmp_path) == {}
    # Empty stacks return the current state unchanged.
    assert broll_approval.undo_approval(tmp_path) == {}

    assert broll_approval.redo_approval(tmp_path)["Opening"]["approved"] == [0]
    assert broll_approval.redo_approval(tmp_path)["Opening"]["approved"] == [1]
    assert broll_approval.redo_approval(tmp_path)["Opening"]["approved"] == [1]


def test_history_is_bounded(tmp_path: Path) -> None:
    for index in range(broll_approval.MAX_HISTORY + 5):
        broll_approval.save_approval(
            tmp_path, title="Opening", approved=[index % 3], plan=PLAN
        )

    history = broll_approval._history(tmp_path)

    assert len(history["undo"]) == broll_approval.MAX_HISTORY
    assert history["redo"] == []


def test_corrupt_history_is_treated_as_empty(tmp_path: Path) -> None:
    (tmp_path / "broll_history.json").write_text("not json", encoding="utf-8")
    assert broll_approval._history(tmp_path) == {"undo": [], "redo": []}

    (tmp_path / "broll_history.json").write_text("[]", encoding="utf-8")
    assert broll_approval._history(tmp_path) == {"undo": [], "redo": []}


def test_ordered_entries_uses_the_operator_order(tmp_path: Path) -> None:
    approvals = broll_approval.save_approval(
        tmp_path, title="Opening", approved=[0, 1, 2], order=[2, 0], plan=PLAN
    )

    ordered = broll_approval.ordered_entries(PLAN, approvals)

    assert [entry["asset"] for entry in ordered["Opening"]] == [
        "c.mp4",
        "a.mp4",
        "b.mp4",
    ]


def test_ordered_entries_skips_missing_and_out_of_range(tmp_path: Path) -> None:
    approvals = {
        "Opening": {"approved": [0], "order": [0, 99]},
        "Missing": {"approved": [0], "order": [0]},
        "Unordered": {"approved": [0], "order": []},
    }

    ordered = broll_approval.ordered_entries(PLAN, approvals)

    assert list(ordered) == ["Opening"]
    assert ordered["Opening"] == [PLAN["Opening"][0]]
