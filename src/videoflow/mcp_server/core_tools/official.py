"""Official profile aliases and the session brief tool.

The v4.2 profiles expose stable names. Older granular tools remain available
only through the internal ``all`` profile, so the Official surface stays small
without duplicating business logic.
"""

from __future__ import annotations

import functools
import inspect
import json
from pathlib import Path
from typing import Any, Literal

from videoflow.application.curation_board import (
    CurationError,
    auto_select_board,
    board_url,
    load_board,
    load_decisions,
    publish_board,
)
from videoflow.application.projects import get_project, load_project_state
from videoflow.application.session_brief import build_session_brief
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error

ALIASES: dict[str, str] = {
    "vf_transcript": "vf_transcript_query",
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
                board = publish_board(output, record.project_id, list(items or []))
                return {
                    "ok": True,
                    "status": board.status,
                    "board_id": board.board_id,
                    "board_url": board_url(record.project_id),
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
    def vf_decupage(
        action: Literal["plan", "run_full"] = "plan",
        project_id: str = "",
        style_id: str = "",
        instructions: str = "",
        pacing_profile: Literal["tight", "balanced", "relaxed"] = "tight",
        max_pause_ms: int | None = None,
        min_silence_ms: int | None = None,
        pad_before_ms: int | None = None,
        pad_after_ms: int | None = None,
        second_pass: bool = True,
        wait: bool = True,
        timeout_sec: float = 1800.0,
    ) -> dict[str, Any]:
        """[DOES] Plan a beat map or run the canonical safe decupage chain.
        [REQUIRES] ``project_id`` and, for run_full, an ingested project.
        [RETURNS] Beat-map plan or job with flagged long cuts and next action.
        """
        if action == "plan":
            return tools["vf_beatmap_plan"](
                project_id=project_id,
                style_id=style_id,
                instructions=instructions,
            )
        if action != "run_full":
            return error(
                "invalid_decupage_action",
                "action must be plan or run_full",
            )
        from videoflow.application.silence import resolve_pacing_profile

        pacing = resolve_pacing_profile(
            pacing_profile,
            max_pause_ms=max_pause_ms,
            min_silence_ms=min_silence_ms,
            pad_before_ms=pad_before_ms,
            pad_after_ms=pad_after_ms,
        )
        result = tools["vf_run"](
            project_id=project_id,
            steps=[
                "ingest",
                "audio.vad",
                "transcribe",
                "speech.editorial_clean",
                "retakes.cull",
                "decupage.snap",
                "decupage.timeline",
            ],
            params={},
            step_params={
                "audio.vad": {
                    "min_silence_ms": pacing["min_silence_ms"],
                },
                "speech.editorial_clean": {
                    "pad_before_ms": pacing["pad_before_ms"],
                    "pad_after_ms": pacing["pad_after_ms"],
                    "second_pass": second_pass,
                },
                "decupage.snap": {
                    "pre_roll_ms": pacing["pad_before_ms"],
                    "post_roll_ms": pacing["pad_after_ms"],
                    "pre_roll_floor_ms": pacing["pad_before_ms"],
                    "post_roll_floor_ms": pacing["pad_after_ms"],
                    "min_cut_gap_ms": pacing["max_pause_ms"],
                    "pacing_profile": pacing_profile,
                    "qa_dead_air_ms": pacing["qa_dead_air_ms"],
                },
            },
            wait=wait,
            timeout_sec=timeout_sec,
        )
        if not isinstance(result, dict) or not result.get("ok"):
            return result
        if wait:
            plan_result = tools["vf_beatmap_plan"](
                project_id=project_id,
                style_id=style_id,
                instructions=instructions,
            )
            if isinstance(plan_result, dict) and plan_result.get("ok"):
                result["beat_map_path"] = plan_result.get("path", "")
                result["beatmap"] = plan_result.get("plan", {})
            try:
                record = get_project(project_id)
                report_path = Path(record.output) / "work" / "decupage" / "report.json"
                payload = json.loads(report_path.read_text(encoding="utf-8"))
                result["flagged_long_cuts"] = payload.get("flagged_long_cuts", [])
            except (OSError, ValueError, VideoFlowError):
                result["flagged_long_cuts"] = []
        try:
            record = get_project(project_id)
            state = load_project_state(record)
            report = state.pipeline.metadata.get("editorial_clean")
        except VideoFlowError:
            report = None
        if isinstance(report, dict):
            candidates = report.get("semantic_candidates") or []
            if report.get("semantic_status") == "delegated" and candidates:
                result["pending_semantic_review"] = True
                result["semantic_candidates"] = candidates
                result["_next_step"] = (
                    "Analise os pares em semantic_candidates e chame "
                    "vf_decupage(action='discard_sentences', sentence_ids=[...]) "
                    "antes de exportar"
                )
                return result
        result["pacing_profile"] = pacing_profile
        result["pacing"] = dict(pacing)
        result["_next_step"] = (
            "Revise flagged_long_cuts. If any requires_review is true, open the "
            "curation board or inspect decupage/report.json before exporting."
        )
        return result

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
