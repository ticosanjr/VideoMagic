"""Official profile aliases and the session brief tool.

The v4.2 profiles expose stable names. Older granular tools remain available
only through the internal ``all`` profile, so the Official surface stays small
without duplicating business logic.
"""

from __future__ import annotations

import functools
import inspect
from pathlib import Path
from typing import Any, Literal

from videoflow.application.curation_board import (
    CurationError,
    auto_select_board,
    load_board,
    load_decisions,
    publish_board,
)
from videoflow.application.projects import get_project
from videoflow.application.session_brief import build_session_brief
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error

ALIASES: dict[str, str] = {
    "vf_transcript": "vf_transcript_query",
    "vf_decupage": "vf_beatmap_plan",
    "vf_shorts": "vf_shorts_batch",
    "vf_qa": "vf_qa_final",
    "vf_jobs": "vf_job",
}


def _alias(name: str, target: Any) -> Any:
    @functools.wraps(target)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return target(*args, **kwargs)

    wrapper.__name__ = name
    wrapper.__qualname__ = name
    wrapper.__signature__ = inspect.signature(target)  # type: ignore[attr-defined]
    return wrapper


def register_official_tools(register: Any, tools: dict[str, Any]) -> None:
    """Register the official names on top of the captured implementations."""

    @register
    def vf_curation(
        action: Literal["publish", "read", "auto_select"],
        project_id: str,
        items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """[DOES] Publish, read, or auto-select a visual curation board.
        [REQUIRES] ``project_id`` and, for publish, a non-empty ``items`` list.
        [RETURNS] Board status, selected items, and the next agent action.
        """
        try:
            record = get_project(project_id)
            output = Path(record.output).expanduser()
            if action == "publish":
                board = publish_board(output, project_id, list(items or []))
                return {
                    "ok": True,
                    "status": board.status,
                    "board_id": board.board_id,
                    "board_url": f"http://127.0.0.1:8765/#curation/{project_id}",
                    "item_count": len(board.items),
                    "_next_step": (
                        "Informe board_url ao usuário e aguarde 'pronto' ou "
                        "'pode escolher você'."
                    ),
                }
            if action == "auto_select":
                board = auto_select_board(output)
            elif action == "read":
                board = load_board(output)
            else:
                return error(
                    "invalid_curation_action",
                    "action must be publish, read, or auto_select",
                )
            if board is None:
                return error(
                    "curation_board_missing",
                    "No curation board exists for this project",
                )
            decisions = load_decisions(output)
            status = decisions.status if decisions is not None else board.status
            selected = [
                item.model_dump(mode="json")
                for item in board.items
                if item.status == "selected"
            ]
            if status == "waiting_human":
                return {
                    "ok": True,
                    "status": status,
                    "board_id": board.board_id,
                    "item_count": len(board.items),
                    "selected": [],
                    "_next_step": (
                        "Aguardando confirmação na UI ou autorização para "
                        "auto_select."
                    ),
                }
            return {
                "ok": True,
                "status": status,
                "board_id": board.board_id,
                "selected": selected,
                "rejected_ids": list(decisions.rejected_ids) if decisions else [],
                "_next_step": "Use os itens selecionados para montar a timeline.",
            }
        except CurationError as exc:
            return exc.to_dict()
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def vf_session_brief(project_id: str) -> dict[str, Any]:
        """[DOES] Summarize a project's stage, sources, GPU, QA, and next moves.
        [REQUIRES] A registered ``project_id``.
        [RETURNS] Compact session brief with revision and next actions.
        """
        try:
            return build_session_brief(project_id)
        except VideoFlowError as exc:
            return exc.to_dict()

    for name, target_name in ALIASES.items():
        target = tools.get(target_name)
        if target is None:  # pragma: no cover - registry bug
            raise RuntimeError(f"Official tool {name} needs {target_name}")
        register(_alias(name, target))


__all__ = ["ALIASES", "register_official_tools"]
