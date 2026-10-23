"""Persisted undo/redo history for timeline edits."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.domain.state import ProjectState

HISTORY_FILE = "timeline_history.json"
MAX_ENTRIES = 50


class TimelineHistory:
    """A small bounded undo/redo stack stored next to project_state.json."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.undo: list[str] = []
        self.redo: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.undo = [str(item) for item in payload.get("undo", [])][-MAX_ENTRIES:]
            self.redo = [str(item) for item in payload.get("redo", [])][-MAX_ENTRIES:]
        except (OSError, ValueError, TypeError):
            self.undo = []
            self.redo = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"undo": self.undo[-MAX_ENTRIES:], "redo": self.redo[-MAX_ENTRIES:]})
            + "\n",
            encoding="utf-8",
        )

    @property
    def can_undo(self) -> bool:
        return bool(self.undo)

    @property
    def can_redo(self) -> bool:
        return bool(self.redo)

    def record(self, previous: ProjectState) -> None:
        self.undo.append(previous.model_dump_json())
        self.undo = self.undo[-MAX_ENTRIES:]
        self.redo = []
        self._save()

    def undo_state(self, current: ProjectState) -> ProjectState | None:
        if not self.undo:
            return None
        payload = self.undo.pop()
        try:
            state = ProjectState.model_validate_json(payload)
        except ValueError:
            self._save()
            return None
        self.redo.append(current.model_dump_json())
        self._save()
        return state

    def redo_state(self, current: ProjectState) -> ProjectState | None:
        if not self.redo:
            return None
        payload = self.redo.pop()
        try:
            state = ProjectState.model_validate_json(payload)
        except ValueError:
            self._save()
            return None
        self.undo.append(current.model_dump_json())
        self._save()
        return state
