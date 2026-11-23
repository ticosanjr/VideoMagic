"""Visual curation boards and two-turn human decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.clock import now_iso
from videoflow.application.files import read_json_dict, write_json_atomic
from videoflow.domain.errors import VideoFlowError

CurationCategory = Literal["style", "music", "sfx", "broll", "image", "short", "cut_review"]
CurationMediaType = Literal["audio", "video", "image", "style"]
CurationStatus = Literal["waiting_human", "decided", "delegated_to_ai"]


class CurationError(VideoFlowError):
    """A stable error from the curation board."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class CurationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    category: CurationCategory
    scene_id: str = ""
    title: str
    local_path: str = ""
    media_type: CurationMediaType
    duration_sec: float = 0.0
    recommended: bool = False
    reason: str = ""
    status: Literal["pending", "selected", "rejected"] = "pending"


class CurationBoard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    board_id: str
    status: CurationStatus = "waiting_human"
    items: list[CurationItem] = Field(default_factory=list)
    updated_at: str


class CurationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    board_id: str = ""
    status: CurationStatus = "waiting_human"
    selected_ids: list[str] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    updated_at: str


def curation_dir(project_dir: str | Path) -> Path:
    return Path(project_dir).expanduser() / "curation"


def board_path(project_dir: str | Path) -> Path:
    return curation_dir(project_dir) / "board.json"


def decisions_path(project_dir: str | Path) -> Path:
    return curation_dir(project_dir) / "decisions.json"


def load_board(project_dir: str | Path) -> CurationBoard | None:
    path = board_path(project_dir)
    if not path.is_file():
        return None
    try:
        return CurationBoard.model_validate(read_json_dict(path))
    except ValueError as exc:
        raise CurationError("curation_board_invalid", str(exc)) from exc


def load_decisions(project_dir: str | Path) -> CurationDecision | None:
    path = decisions_path(project_dir)
    if not path.is_file():
        return None
    try:
        return CurationDecision.model_validate(read_json_dict(path))
    except ValueError as exc:
        raise CurationError("curation_decisions_invalid", str(exc)) from exc


def _persist(
    project_dir: str | Path,
    board: CurationBoard,
    decisions: CurationDecision,
) -> CurationBoard:
    board.updated_at = now_iso()
    decisions.updated_at = board.updated_at
    decisions.project_id = board.project_id
    decisions.board_id = board.board_id
    write_json_atomic(board_path(project_dir), board.model_dump(mode="json"))
    write_json_atomic(
        decisions_path(project_dir), decisions.model_dump(mode="json")
    )
    return board


def publish_board(
    project_dir: str | Path,
    project_id: str,
    items: list[dict[str, Any]],
) -> CurationBoard:
    """Validate and atomically replace the pending board for one project."""

    if not items:
        raise CurationError(
            "empty_curation_board", "A curation board needs at least one item"
        )
    parsed: list[CurationItem] = []
    seen: set[str] = set()
    for raw in items:
        try:
            item = CurationItem.model_validate(raw)
        except ValueError as exc:
            raise CurationError("invalid_curation_item", str(exc)) from exc
        if item.item_id in seen:
            raise CurationError(
                "duplicate_item_id", f"Duplicate curation item: {item.item_id}"
            )
        seen.add(item.item_id)
        parsed.append(item)
    board = CurationBoard(
        project_id=project_id,
        board_id=f"board-{uuid4().hex[:12]}",
        status="waiting_human",
        items=parsed,
        updated_at=now_iso(),
    )
    decisions = CurationDecision(
        project_id=project_id,
        board_id=board.board_id,
        status="waiting_human",
        updated_at=board.updated_at,
    )
    return _persist(project_dir, board, decisions)


def _automatic_ids(board: CurationBoard) -> list[str]:
    recommended = [item.item_id for item in board.items if item.recommended]
    if recommended:
        return recommended
    seen: set[tuple[str, str]] = set()
    selected: list[str] = []
    for item in board.items:
        key = (item.category, item.scene_id)
        if key in seen:
            continue
        seen.add(key)
        selected.append(item.item_id)
    return selected


def _apply_selection(
    project_dir: str | Path,
    board: CurationBoard,
    *,
    selected_ids: list[str],
    rejected_ids: list[str],
    status: Literal["decided", "delegated_to_ai"],
) -> CurationBoard:
    selected = list(dict.fromkeys(str(item) for item in selected_ids))
    rejected = list(dict.fromkeys(str(item) for item in rejected_ids))
    overlap = set(selected) & set(rejected)
    if overlap:
        raise CurationError(
            "curation_decision_invalid",
            f"Items cannot be both selected and rejected: {sorted(overlap)}",
        )
    known = {item.item_id for item in board.items}
    unknown = (set(selected) | set(rejected)) - known
    if unknown:
        raise CurationError(
            "curation_decision_invalid",
            f"Unknown curation item(s): {sorted(unknown)}",
        )
    for item in board.items:
        if item.item_id in selected:
            item.status = "selected"
        elif item.item_id in rejected:
            item.status = "rejected"
        else:
            item.status = "pending"
    board.status = status
    decisions = CurationDecision(
        project_id=board.project_id,
        board_id=board.board_id,
        status=status,
        selected_ids=selected,
        rejected_ids=rejected,
        updated_at=now_iso(),
    )
    return _persist(project_dir, board, decisions)


def save_decisions(
    project_dir: str | Path,
    selected_ids: list[str],
    rejected_ids: list[str],
    delegate_to_ai: bool = False,
) -> CurationBoard:
    board = load_board(project_dir)
    if board is None:
        raise CurationError(
            "curation_board_missing", "No curation board exists for this project"
        )
    if delegate_to_ai:
        return auto_select_board(project_dir)
    return _apply_selection(
        project_dir,
        board,
        selected_ids=selected_ids,
        rejected_ids=rejected_ids,
        status="decided",
    )


def auto_select_board(project_dir: str | Path) -> CurationBoard:
    board = load_board(project_dir)
    if board is None:
        raise CurationError(
            "curation_board_missing", "No curation board exists for this project"
        )
    return _apply_selection(
        project_dir,
        board,
        selected_ids=_automatic_ids(board),
        rejected_ids=[],
        status="delegated_to_ai",
    )


def _board_summary(board: CurationBoard, project_dir: str | Path) -> dict[str, Any]:
    return {
        "project_id": board.project_id,
        "board_id": board.board_id,
        "status": board.status,
        "item_count": len(board.items),
        "updated_at": board.updated_at,
        "output": str(Path(project_dir).expanduser()),
    }


def list_boards(
    projects_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List every known curation board, newest first.

    ``projects_root`` is useful in tests and standalone workspaces. When it is
    omitted, the registered project registry is the source of truth.
    """

    directories: list[Path] = []
    if projects_root is not None:
        root = Path(projects_root).expanduser()
        if root.is_dir():
            directories = [item for item in root.iterdir() if item.is_dir()]
    else:
        from videoflow.application.projects import list_projects

        directories = [Path(item.output).expanduser() for item in list_projects()]
    boards: list[dict[str, Any]] = []
    for directory in directories:
        try:
            board = load_board(directory)
        except CurationError:
            continue
        if board is None:
            continue
        boards.append(_board_summary(board, directory))
    return sorted(boards, key=lambda item: str(item["updated_at"]), reverse=True)


def list_pending_boards(
    projects_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List boards still waiting for a human decision."""

    return [
        board
        for board in list_boards(projects_root)
        if board["status"] == "waiting_human"
    ]


__all__ = [
    "CurationBoard",
    "CurationDecision",
    "CurationError",
    "CurationItem",
    "auto_select_board",
    "board_path",
    "curation_dir",
    "decisions_path",
    "list_boards",
    "list_pending_boards",
    "load_board",
    "load_decisions",
    "publish_board",
    "save_decisions",
]
