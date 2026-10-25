"""Tool-calling assistant: plan, validate, diff, approve, and record.

The model may only name allowlisted tools. Read-only tools run immediately.
Write tools are stored as a pending plan and execute only after an explicit
approval, so a completion can never edit or render on its own.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from videoflow.adapters import LlmClient
from videoflow.application.copilot import ALLOWED_ACTIONS
from videoflow.domain.errors import StateNotReadyError

ToolName = Literal[
    "list_recipes",
    "get_job",
    "get_timeline",
    "list_projects",
    "validate_exports",
    "apply_timeline_edits",
    "render_preview",
    "run_recipe",
]

READ_ONLY: frozenset[str] = frozenset(
    {"list_recipes", "get_job", "get_timeline", "list_projects", "validate_exports"}
)
WRITE: frozenset[str] = frozenset({"apply_timeline_edits", "render_preview", "run_recipe"})

SYSTEM_PROMPT = """\
You are the VideoFlow local assistant. You may only use these tools:
{tools}

Return JSON:
{{"message":"short reply for the operator",
  "actions":[{{"tool":"tool_name","arguments":{{...}}}}],
  "requires_approval":true}}

Rules:
- Read-only tools: list_recipes, get_job, get_timeline, list_projects, validate_exports.
- Write tools need approval: apply_timeline_edits, render_preview, run_recipe.
- apply_timeline_edits arguments: {{"edits":[{{"clip_id":"v1","action":"trim",
  "start_sec":0.0,"end_sec":2.0}}]}}. Allowed actions: {actions}.
- run_recipe arguments: {{"recipe_id":"...","source":"/abs/path","output":"/abs/path"}}.
- Never invent clip ids, recipe ids, or paths. Use the context below.
- Keep the plan minimal and explain the intended outcome.

Context:
{context}

Operator request: {prompt}
"""


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = ""
    tool: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)

    @property
    def writes(self) -> bool:
        return self.tool in WRITE


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = ""
    actions: list[Action] = Field(default_factory=list)
    requires_approval: bool = False


class PendingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    job_id: str
    prompt: str
    message: str
    actions: list[Action]
    diff: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str
    job_id: str
    prompt: str
    message: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    applied: bool = False
    approval_id: str = ""
    tokens: int = 0
    cost_usd: float = 0.0
    error: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def validate_actions(turn: Turn) -> Turn:
    cleaned: list[Action] = []
    for index, action in enumerate(turn.actions):
        action.id = action.id or f"a{index + 1}"
        if action.tool == "apply_timeline_edits":
            edits = action.arguments.get("edits")
            if not isinstance(edits, list) or not edits:
                raise StateNotReadyError("The assistant proposed no timeline edits.")
            for edit in edits:
                if not isinstance(edit, dict):
                    raise StateNotReadyError("The assistant proposed a malformed edit.")
                action_name = str(edit.get("action") or "")
                if action_name not in ALLOWED_ACTIONS:
                    raise StateNotReadyError(
                        f"The assistant proposed an unsupported edit: {action_name}"
                    )
                if not str(edit.get("clip_id") or ""):
                    raise StateNotReadyError("The assistant proposed an edit without a clip.")
        elif action.tool == "run_recipe":
            if not str(action.arguments.get("recipe_id") or "").strip():
                raise StateNotReadyError("The assistant did not choose a recipe.")
            for key in ("source", "output"):
                if not str(action.arguments.get(key) or "").strip():
                    raise StateNotReadyError(f"The assistant did not set {key}.")
        elif action.tool == "render_preview":
            if action.arguments.get("job_id") not in {None, ""}:
                raise StateNotReadyError("The assistant cannot target another job.")
            action.arguments = {}
        cleaned.append(action)
    turn.actions = cleaned
    return turn


def plan(
    client: LlmClient,
    *,
    prompt: str,
    context: dict[str, Any],
    observations: list[dict[str, Any]] | None = None,
) -> Turn:
    if not prompt.strip():
        raise StateNotReadyError("Describe what the assistant should do.")
    payload: dict[str, Any] = dict(context)
    if observations:
        payload["observations"] = observations
    raw = client.complete_json(
        SYSTEM_PROMPT.format(
            tools=", ".join([*sorted(READ_ONLY), *sorted(WRITE)]),
            actions=", ".join(sorted(ALLOWED_ACTIONS)),
            context=json.dumps(payload, ensure_ascii=False, default=str)[:12000],
            prompt=prompt.strip(),
        ),
        "videoflow.assistant",
    )
    try:
        turn = Turn.model_validate(raw)
    except ValidationError as exc:
        raise StateNotReadyError(f"The assistant returned an invalid plan: {exc}") from exc
    return validate_actions(turn)


def diff_timeline(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe clip-level changes between two serialized timelines."""

    before_clips = {clip["id"]: clip for clip in before.get("video", [])}
    after_clips = {clip["id"]: clip for clip in after.get("video", [])}
    changes: list[dict[str, Any]] = []
    for clip_id in sorted(set(before_clips) | set(after_clips)):
        old = before_clips.get(clip_id)
        new = after_clips.get(clip_id)
        if old is None:
            changes.append({"clip_id": clip_id, "change": "added", "after": new})
        elif new is None:
            changes.append({"clip_id": clip_id, "change": "removed", "before": old})
        else:
            fields = {
                key: {"before": old.get(key), "after": new.get(key)}
                for key in ("start_sec", "end_sec", "source_in_frame", "source_out_frame")
                if old.get(key) != new.get(key)
            }
            if fields:
                changes.append({"clip_id": clip_id, "change": "modified", **fields})
    return changes


def _plan_path(output: Path, approval_id: str) -> Path:
    return output / "assistant" / "pending" / f"{approval_id}.json"


def save_pending(output: Path, pending: PendingPlan) -> PendingPlan:
    path = _plan_path(output, pending.approval_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(pending.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return pending


def load_pending(output: Path, approval_id: str) -> PendingPlan:
    path = _plan_path(output, approval_id)
    if not path.is_file():
        raise StateNotReadyError("Unknown or already applied approval id.")
    try:
        return PendingPlan.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateNotReadyError(f"Invalid pending plan: {exc}") from exc


def delete_pending(output: Path, approval_id: str) -> None:
    _plan_path(output, approval_id).unlink(missing_ok=True)


def _history_path(output: Path) -> Path:
    return output / "assistant" / "history.json"


def read_history(output: Path) -> list[dict[str, Any]]:
    path = _history_path(output)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return raw if isinstance(raw, list) else []


def record_history(output: Path, entry: HistoryEntry) -> None:
    items = read_history(output)[-49:]
    items.append(entry.model_dump(mode="json"))
    path = _history_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def now() -> str:
    return _now()
