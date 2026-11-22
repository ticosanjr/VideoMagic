"""Official profile aliases and the session brief tool.

The v4.2 profiles expose stable names. Older granular tools remain available
only through the internal ``all`` profile, so the Official surface stays small
without duplicating business logic.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any

from videoflow.application.session_brief import build_session_brief
from videoflow.domain.errors import VideoFlowError

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
