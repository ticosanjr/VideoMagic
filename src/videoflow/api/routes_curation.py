"""REST surface for the two-turn visual curation board."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from videoflow.application.curation_board import (
    CurationError,
    list_boards,
    list_pending_boards,
    load_board,
    load_decisions,
    save_decisions,
)
from videoflow.application.projects import get_project
from videoflow.domain.errors import PathJailError, VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots


class DecideRequest(BaseModel):
    selected_ids: list[str] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    delegate_to_ai: bool = False


def _project_output(project_id: str) -> Path:
    try:
        return Path(get_project(project_id).output).expanduser()
    except VideoFlowError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()) from exc


def _http_error(exc: CurationError) -> HTTPException:
    status = 404 if exc.code.endswith("_missing") else 400
    return HTTPException(status_code=status, detail=exc.to_dict())


def register_curation_routes(app: FastAPI) -> None:
    """Register the curation board and reviewed-media endpoints."""

    @app.get("/api/v1/curation/boards")
    def curation_boards(pending_only: bool = False) -> dict[str, Any]:
        boards = list_pending_boards() if pending_only else list_boards()
        return {"ok": True, "boards": boards}

    @app.get("/api/v1/curation/{project_id}")
    def curation_board(project_id: str) -> dict[str, Any]:
        output = _project_output(project_id)
        try:
            board = load_board(output)
            decisions = load_decisions(output)
        except CurationError as exc:
            raise _http_error(exc) from exc
        if board is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "curation_board_missing",
                    "error_code": "curation_board_missing",
                    "message": "No curation board exists for this project",
                },
            )
        return {
            "ok": True,
            "board": board.model_dump(mode="json"),
            "decisions": (
                decisions.model_dump(mode="json") if decisions is not None else None
            ),
        }

    @app.get("/api/v1/curation/{project_id}/media/{item_id}")
    def curation_media(project_id: str, item_id: str) -> FileResponse:
        output = _project_output(project_id)
        try:
            board = load_board(output)
        except CurationError as exc:
            raise _http_error(exc) from exc
        if board is None:
            raise HTTPException(status_code=404, detail="curation board not found")
        item = next((entry for entry in board.items if entry.item_id == item_id), None)
        if item is None or not item.local_path:
            raise HTTPException(status_code=404, detail="curation item not found")
        candidate = Path(item.local_path).expanduser()
        if not candidate.is_absolute():
            candidate = output / candidate
        try:
            path = resolve_allowed(candidate, allowed_roots())
        except PathJailError as exc:
            raise HTTPException(status_code=403, detail=exc.to_dict()) from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="curation media not found")
        return FileResponse(path)

    @app.post("/api/v1/curation/{project_id}/decide")
    def curation_decide(project_id: str, request: DecideRequest) -> dict[str, Any]:
        output = _project_output(project_id)
        try:
            save_decisions(
                output,
                request.selected_ids,
                request.rejected_ids,
                delegate_to_ai=request.delegate_to_ai,
            )
            board = load_board(output)
            decisions = load_decisions(output)
        except CurationError as exc:
            raise _http_error(exc) from exc
        return {
            "ok": True,
            "board": board.model_dump(mode="json") if board is not None else None,
            "decisions": (
                decisions.model_dump(mode="json") if decisions is not None else None
            ),
        }


__all__ = ["DecideRequest", "register_curation_routes"]
