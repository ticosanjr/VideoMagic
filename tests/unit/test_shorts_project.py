from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.shorts_project import (
    load_short_project,
    save_short_entry,
    short_entry,
    short_pieces,
    transcript_text,
)
from videoflow.domain.errors import ShortEditError, StateNotReadyError
from videoflow.domain.state import ProjectState, Sentence


def _state() -> ProjectState:
    return ProjectState(
        transcript=[
            Sentence(id=0, start_sample=0, end_sample=100, text="keep"),
            Sentence(id=1, start_sample=100, end_sample=200, text="drop"),
            Sentence(id=2, start_sample=200, end_sample=300, text="also"),
        ]
    )


def test_load_short_project_reads_state_and_report(tmp_path: Path) -> None:
    (tmp_path / "project_state.json").write_text(
        _state().model_dump_json(), encoding="utf-8"
    )
    (tmp_path / "shorts.json").write_text(
        json.dumps({"ok": True, "clips": [{"title": "a"}]}), encoding="utf-8"
    )

    state, report = load_short_project(tmp_path)

    assert state.transcript[0].text == "keep"
    assert report["clips"][0]["title"] == "a"


def test_load_short_project_rejects_missing_files(tmp_path: Path) -> None:
    with pytest.raises(StateNotReadyError):
        load_short_project(tmp_path)


def test_load_short_project_rejects_non_object_report(tmp_path: Path) -> None:
    (tmp_path / "project_state.json").write_text(
        _state().model_dump_json(), encoding="utf-8"
    )
    (tmp_path / "shorts.json").write_text("[]", encoding="utf-8")

    with pytest.raises(StateNotReadyError):
        load_short_project(tmp_path)


def test_short_entry_validates_index_and_type() -> None:
    container = {"shorts": [{"title": "a"}, "bad"]}

    assert short_entry(container, 0)["title"] == "a"
    with pytest.raises(ShortEditError):
        short_entry(container, 2)
    with pytest.raises(ShortEditError):
        short_entry(container, 1)


def test_short_pieces_strict_and_lenient() -> None:
    assert short_pieces({"pieces": [[0, 100], [200, 300]]}) == [(0, 100), (200, 300)]

    with pytest.raises(ShortEditError):
        short_pieces({"pieces": [[0]]})
    with pytest.raises(ShortEditError):
        short_pieces({"pieces": []})

    assert short_pieces({"pieces": [[0], [1, 2]]}, strict=False) == [(1, 2)]
    assert short_pieces({"pieces": []}, require=False) == []


def test_transcript_text_keeps_overlapping_sentences() -> None:
    state = _state()

    assert transcript_text(state, [(0, 100), (250, 300)]) == "keep also"


def test_save_short_entry_updates_report(tmp_path: Path) -> None:
    report = {"clips": [{"title": "old"}]}

    save_short_entry(tmp_path, report, 0, {"title": "new"}, fallback=[])

    written = json.loads((tmp_path / "shorts.json").read_text(encoding="utf-8"))
    assert written == {"ok": True, "clips": [{"title": "new"}]}


def test_save_short_entry_uses_fallback_without_clips(tmp_path: Path) -> None:
    save_short_entry(
        tmp_path,
        {},
        0,
        {"title": "new"},
        fallback=[{"title": "fallback"}],
    )

    written = json.loads((tmp_path / "shorts.json").read_text(encoding="utf-8"))
    assert written["clips"] == [{"title": "fallback"}]
