"""Copilot recipe/timeline and assistant approval routes."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from videoflow.api.routes_recipes import (
    RecipeRunRequest,
    start_recipe_job,
)
from videoflow.api.routes_timeline import (
    _apply_and_store,
    _assert_tracks_unlocked,
    _timeline_etag,
    _timeline_history,
    _timeline_state_path,
)
from videoflow.application.jobs import JobManager
from videoflow.application.nle_validation import validate_nle_exports
from videoflow.application.previews import previews
from videoflow.application.timeline_edit import TimelineEdit, apply_timeline_edit
from videoflow.domain.errors import StateNotReadyError
from videoflow.domain.state import ProjectState
from videoflow.engine.recipes import list_recipes


class CopilotRecipeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class CopilotTimelineRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    apply: bool = True


class AssistantRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    approve: bool = False


class AssistantApprovalRequest(BaseModel):
    approval_id: str = Field(min_length=1, max_length=120)


def register_copilot_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register copilot and assistant routes."""

    @app.post("/api/v1/copilot/recipe")
    def copilot_recipe(request: CopilotRecipeRequest) -> dict[str, object]:
        from videoflow.application.copilot import propose_recipe
        from videoflow.application.llm_factory import build_llm

        recipe = propose_recipe(build_llm(), request.prompt)
        return {"ok": True, "recipe": recipe.model_dump(mode="json")}

    @app.post("/api/v1/jobs/{job_id}/copilot/timeline")
    def copilot_timeline(
        job_id: str, request: CopilotTimelineRequest
    ) -> dict[str, object]:
        from videoflow.application.copilot import propose_timeline_edits
        from videoflow.application.llm_factory import build_llm

        job = jobs.get(job_id)
        _assert_tracks_unlocked(job, {"video", "audio"})
        state_path = _timeline_state_path(job)
        history = _timeline_history(job)
        state = ProjectState.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )
        edits = propose_timeline_edits(
            build_llm(),
            request.prompt,
            [
                {
                    "id": clip.clip_id,
                    "start_sec": clip.timeline_in_frame
                    / max(0.001, (state.media_info.fps_num / state.media_info.fps_den)),
                    "end_sec": clip.timeline_out_frame
                    / max(0.001, (state.media_info.fps_num / state.media_info.fps_den)),
                }
                for clip in state.video_segments
            ],
        )
        if request.apply:
            previous = state.model_copy(deep=True)
            working = state.model_copy(deep=True)
            for item in edits:
                working = apply_timeline_edit(
                    working,
                    TimelineEdit(
                        clip_id=str(item.get("clip_id")),
                        action=str(item.get("action")),  # type: ignore[arg-type]
                        start_sec=item.get("start_sec"),
                        end_sec=item.get("end_sec"),
                        delta_sec=float(item.get("delta_sec") or 0.0),
                        split_sec=item.get("split_sec"),
                    ),
                )
            history.record(previous)
            state = _apply_and_store(
                job, working, state_path, history, previous.revision + 1
            )
        return {
            "ok": True,
            "edits": edits,
            "applied": request.apply,
            "revision": state.revision,
            "etag": _timeline_etag(state.revision),
        }

    def _assistant_timeline(state: ProjectState) -> dict[str, object]:
        media = state.media_info
        fps = (media.fps_num / media.fps_den) if media is not None else 30.0
        return {
            "revision": state.revision,
            "fps": fps,
            "video": [
                {
                    "id": clip.clip_id,
                    "start_sec": round(clip.timeline_in_frame / fps, 3),
                    "end_sec": round(clip.timeline_out_frame / fps, 3),
                    "source_in_frame": clip.source_in_frame,
                    "source_out_frame": clip.source_out_frame,
                }
                for clip in state.video_segments
            ],
        }

    def _assistant_context(job: Any) -> dict[str, object]:
        context: dict[str, object] = {
            "job": {
                "job_id": str(job.job_id),
                "status": job.status,
                "stage": job.stage,
                "source": str(job.source),
                "output": str(job.output),
            },
            "recipes": [
                {"id": item.get("id"), "name": item.get("name")}
                for item in list_recipes()[:40]
            ],
        }
        try:
            state = ProjectState.model_validate_json(
                _timeline_state_path(job).read_text(encoding="utf-8")
            )
            context["timeline"] = _assistant_timeline(state)
        except (OSError, ValueError, StateNotReadyError):
            context["timeline"] = None
        return context

    def _assistant_read(job: Any, action: Any) -> dict[str, object]:
        if action.tool == "list_recipes":
            return {"tool": action.id, "recipes": list_recipes()[:80]}
        if action.tool == "get_job":
            payload = job.to_dict()
            payload.pop("result", None)
            payload.pop("options", None)
            return {"tool": action.id, "job": payload}
        if action.tool == "get_timeline":
            state = ProjectState.model_validate_json(
                _timeline_state_path(job).read_text(encoding="utf-8")
            )
            return {"tool": action.id, "timeline": _assistant_timeline(state)}
        if action.tool == "validate_exports":
            return {
                "tool": action.id,
                "validation": validate_nle_exports(job.output / "nle"),
            }
        return {"tool": action.id, "skipped": "not read-only"}

    @app.post("/api/v1/jobs/{job_id}/assistant")
    def assistant_turn(
        job_id: str, request: AssistantRequest
    ) -> dict[str, object]:
        from videoflow.application import assistant
        from videoflow.application.cost import snapshot as cost_snapshot
        from videoflow.application.llm_factory import build_llm

        job = jobs.get(job_id)
        context = _assistant_context(job)
        before = cost_snapshot()
        client = build_llm()
        turn = assistant.plan(client, prompt=request.prompt, context=context)
        observations: list[dict[str, object]] = []
        if turn.actions and all(not item.writes for item in turn.actions):
            observations = [_assistant_read(job, item) for item in turn.actions]
            turn = assistant.plan(
                client,
                prompt=request.prompt,
                context=context,
                observations=observations,
            )
        writes = [item for item in turn.actions if item.writes]
        diff: list[dict[str, Any]] = []
        if writes:
            state = ProjectState.model_validate_json(
                _timeline_state_path(job).read_text(encoding="utf-8")
            )
            before_timeline = _assistant_timeline(state)
            working = state.model_copy(deep=True)
            for action in writes:
                if action.tool != "apply_timeline_edits":
                    continue
                for item in action.arguments.get("edits", []):
                    working = apply_timeline_edit(
                        working,
                        TimelineEdit(
                            clip_id=str(item.get("clip_id")),
                            action=str(item.get("action")),  # type: ignore[arg-type]
                            start_sec=item.get("start_sec"),
                            end_sec=item.get("end_sec"),
                            delta_sec=float(item.get("delta_sec") or 0.0),
                            split_sec=item.get("split_sec"),
                        ),
                    )
            diff = assistant.diff_timeline(
                before_timeline, _assistant_timeline(working)
            )
        after = cost_snapshot()
        approval_id = ""
        if writes:
            import uuid

            approval_id = f"approval-{uuid.uuid4().hex[:10]}"
            assistant.save_pending(
                job.output,
                assistant.PendingPlan(
                    approval_id=approval_id,
                    job_id=str(job.job_id),
                    prompt=request.prompt,
                    message=turn.message,
                    actions=writes,
                    diff=diff,
                    created_at=assistant.now(),
                ),
            )
            assistant.record_history(
                job.output,
                assistant.HistoryEntry(
                    at=assistant.now(),
                    job_id=str(job.job_id),
                    prompt=request.prompt,
                    message=turn.message,
                    actions=[item.model_dump(mode="json") for item in writes],
                    applied=False,
                    approval_id=approval_id,
                    tokens=int(after.get("prompt_tokens", 0))
                    + int(after.get("completion_tokens", 0))
                    - int(before.get("prompt_tokens", 0))
                    - int(before.get("completion_tokens", 0)),
                    cost_usd=round(
                        float(after.get("estimated_cost_usd", 0.0))
                        - float(before.get("estimated_cost_usd", 0.0)),
                        6,
                    ),
                ),
            )
        token_delta = (
            int(after.get("prompt_tokens", 0))
            + int(after.get("completion_tokens", 0))
            - int(before.get("prompt_tokens", 0))
            - int(before.get("completion_tokens", 0))
        )
        cost_delta = round(
            float(after.get("estimated_cost_usd", 0.0))
            - float(before.get("estimated_cost_usd", 0.0)),
            6,
        )
        return {
            "ok": True,
            "message": turn.message,
            "actions": [item.model_dump(mode="json") for item in turn.actions],
            "observations": observations,
            "diff": diff,
            "requires_approval": bool(writes),
            "approval_id": approval_id,
            "tokens": token_delta,
            "cost_usd": cost_delta,
            "budget_usd": after.get("budget_usd", 0.0),
            "remaining_usd": after.get("remaining_usd"),
        }

    def _assistant_apply(job: Any, action: Any) -> dict[str, object]:
        if action.tool == "apply_timeline_edits":
            _assert_tracks_unlocked(job, {"video", "audio"})
            state_path = _timeline_state_path(job)
            history = _timeline_history(job)
            previous = ProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            working = previous.model_copy(deep=True)
            for item in action.arguments.get("edits", []):
                working = apply_timeline_edit(
                    working,
                    TimelineEdit(
                        clip_id=str(item.get("clip_id")),
                        action=str(item.get("action")),  # type: ignore[arg-type]
                        start_sec=item.get("start_sec"),
                        end_sec=item.get("end_sec"),
                        delta_sec=float(item.get("delta_sec") or 0.0),
                        split_sec=item.get("split_sec"),
                    ),
                )
            history.record(previous)
            applied = _apply_and_store(
                job, working, state_path, history, previous.revision + 1
            )
            return {
                "tool": action.id,
                "applied": True,
                "revision": applied.revision,
                "etag": _timeline_etag(applied.revision),
            }
        if action.tool == "render_preview":
            preview = previews.start(job)
            return {"tool": action.id, "preview": preview.to_dict()}
        if action.tool == "run_recipe":
            payload = RecipeRunRequest(
                recipe_id=str(action.arguments.get("recipe_id")),
                source=str(action.arguments.get("source")),
                output=str(action.arguments.get("output")),
                variables=dict(action.arguments.get("variables") or {}),
            )
            return {"tool": action.id, **start_recipe_job(payload, None, jobs)}
        raise StateNotReadyError(f"Unsupported write tool: {action.tool}")

    @app.post("/api/v1/jobs/{job_id}/assistant/approve")
    def assistant_approve(
        job_id: str, request: AssistantApprovalRequest
    ) -> dict[str, object]:
        from videoflow.application import assistant

        job = jobs.get(job_id)
        pending = assistant.load_pending(job.output, request.approval_id)
        if pending.job_id != str(job.job_id):
            raise StateNotReadyError("The approval belongs to another job.")
        results = [_assistant_apply(job, action) for action in pending.actions]
        assistant.delete_pending(job.output, request.approval_id)
        assistant.record_history(
            job.output,
            assistant.HistoryEntry(
                at=assistant.now(),
                job_id=str(job.job_id),
                prompt=pending.prompt,
                message=pending.message,
                actions=[item.model_dump(mode="json") for item in pending.actions],
                applied=True,
                approval_id=pending.approval_id,
            ),
        )
        return {"ok": True, "approval_id": request.approval_id, "results": results}

    @app.get("/api/v1/jobs/{job_id}/assistant/history")
    def assistant_history(job_id: str) -> dict[str, object]:
        from videoflow.application import assistant

        job = jobs.get(job_id)
        return {"ok": True, "history": assistant.read_history(job.output)}
