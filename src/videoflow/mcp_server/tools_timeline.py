"""MCP timeline editing, overlay, comment, and copilot tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.broll_approval import save_approval
from videoflow.application.copilot import propose_recipe, propose_timeline_edits
from videoflow.application.llm_factory import build_llm
from videoflow.application.timeline_edit import TimelineEdit, apply_timeline_edit
from videoflow.application.timeline_history import TimelineHistory
from videoflow.application.timeline_meta import (
    add_comment,
    comments_for,
    load_meta,
    remove_comment,
)
from videoflow.domain.errors import StateNotReadyError, VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.state import OverlayClip
from videoflow.domain.state import ProjectState as TimelineProjectState
from videoflow.mcp_server.context import ToolContext, error
from videoflow.runtime import allowed_roots


def register_timeline_tools(register: Any, ctx: ToolContext) -> None:
    """Register timeline mutation, review, and copilot tools."""

    @register
    def videoflow_edit_timeline(
        clip_id: str,
        action: str,
        start_sec: float | None = None,
        end_sec: float | None = None,
        delta_sec: float = 0.0,
        split_sec: float | None = None,
        job_id: str | None = None,
    ) -> dict[str, object]:
        """Edit one clip and persist undo history."""

        try:
            job = ctx.timeline_job(job_id)
            state_path = Path(
                str(
                    (job.result or {}).get("state_path")
                    or job.output / "project_state.json"
                )
            )
            history = TimelineHistory(job.output / "timeline_history.json")
            state = TimelineProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            previous = state.model_copy(deep=True)
            state = apply_timeline_edit(
                state,
                TimelineEdit(
                    clip_id=clip_id,
                    action=action,  # type: ignore[arg-type]
                    start_sec=start_sec,
                    end_sec=end_sec,
                    delta_sec=delta_sec,
                    split_sec=split_sec,
                ),
            )
            history.record(previous)
            state = state.model_copy(update={"revision": previous.revision + 1})
            state_path.write_text(
                state.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "revision": state.revision, "can_undo": history.can_undo}

    @register
    def videoflow_approve_broll(
        title: str,
        approved: list[int],
        order: list[int] | None = None,
        job_id: str | None = None,
    ) -> dict[str, object]:
        """Approve and order planned B-roll for one Short."""

        try:
            job = ctx.timeline_job(job_id)
            plan = (job.result or {}).get("broll_plan", {})
            approvals = save_approval(
                job.output,
                title=title,
                approved=approved,
                order=order,
                plan=plan if isinstance(plan, dict) else {},
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "approval": approvals}

    @register
    def videoflow_get_timeline(job_id: str | None = None) -> dict[str, object]:
        """Return the canonical timeline clips, tracks, markers, and comments."""

        try:
            job = ctx.timeline_job(job_id)
            state = ctx.state_for_job(job)
            if state is None:
                raise StateNotReadyError("The job has no project state.")
            meta = load_meta(job.output)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "job_id": str(job.job_id),
            "revision": state.revision,
            "fps": (
                state.media_info.fps_num / state.media_info.fps_den
                if state.media_info is not None
                else 30.0
            ),
            "video": [
                {
                    "clip_id": clip.clip_id,
                    "source_in_frame": clip.source_in_frame,
                    "source_out_frame": clip.source_out_frame,
                    "timeline_in_frame": clip.timeline_in_frame,
                    "timeline_out_frame": clip.timeline_out_frame,
                }
                for clip in state.video_segments
            ],
            "audio": [
                {
                    "clip_id": clip.clip_id,
                    "source_in_sample": clip.source_in_sample,
                    "source_out_sample": clip.source_out_sample,
                    "timeline_in_sample": clip.timeline_in_sample,
                    "timeline_out_sample": clip.timeline_out_sample,
                }
                for clip in state.audio_segments
            ],
            "overlays": [item.model_dump(mode="json") for item in state.overlays],
            "markers": [item.model_dump(mode="json") for item in meta.markers],
            "tracks": {key: value.model_dump() for key, value in meta.tracks.items()},
            "comments": [item.model_dump(mode="json") for item in meta.comments],
        }

    @register
    def videoflow_add_timeline_overlay(
        path: str,
        start_sec: float,
        duration_sec: float,
        asset_id: str = "",
        position_x: float = 0.5,
        position_y: float = 0.5,
        width_ratio: float = 0.25,
        opacity: float = 1.0,
        kind: str = "image",
        job_id: str | None = None,
    ) -> dict[str, object]:
        """Add an image or video overlay to the canonical timeline."""

        from uuid import uuid4

        try:
            job = ctx.timeline_job(job_id)
            resolved = resolve_allowed(Path(path), allowed_roots())
            state_path = Path(
                str(
                    (job.result or {}).get("state_path")
                    or job.output / "project_state.json"
                )
            )
            history = TimelineHistory(job.output / "timeline_history.json")
            state = TimelineProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            previous = state.model_copy(deep=True)
            fps = (
                state.media_info.fps_num / state.media_info.fps_den
                if state.media_info is not None
                else 30.0
            )
            overlay = OverlayClip(
                overlay_id=f"overlay-{uuid4().hex[:8]}",
                asset_id=asset_id,
                path=str(resolved),
                start_frame=round(start_sec * fps),
                duration_frames=max(1, round(duration_sec * fps)),
                position_x=position_x,
                position_y=position_y,
                width_ratio=width_ratio,
                opacity=opacity,
                kind="video" if kind == "video" else "image",
            )
            state.overlays = [*state.overlays, overlay]
            history.record(previous)
            state = state.model_copy(update={"revision": previous.revision + 1})
            state_path.write_text(
                state.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        except (VideoFlowError, OSError, ValueError) as exc:
            if isinstance(exc, VideoFlowError):
                return exc.to_dict()
            return error("overlay_failed", str(exc))
        return {"ok": True, "overlay": overlay.model_dump(mode="json")}

    @register
    def videoflow_remove_timeline_overlay(
        overlay_id: str, job_id: str | None = None
    ) -> dict[str, object]:
        """Remove one timeline overlay."""

        try:
            job = ctx.timeline_job(job_id)
            state_path = Path(
                str(
                    (job.result or {}).get("state_path")
                    or job.output / "project_state.json"
                )
            )
            history = TimelineHistory(job.output / "timeline_history.json")
            state = TimelineProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            previous = state.model_copy(deep=True)
            kept = [item for item in state.overlays if item.overlay_id != overlay_id]
            if len(kept) == len(state.overlays):
                raise StateNotReadyError(f"Unknown overlay: {overlay_id}")
            state.overlays = kept
            history.record(previous)
            state = state.model_copy(update={"revision": previous.revision + 1})
            state_path.write_text(
                state.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "revision": state.revision}

    @register
    def videoflow_list_clip_comments(
        clip_id: str = "", job_id: str | None = None
    ) -> dict[str, object]:
        """List comments for a clip or the whole timeline."""

        try:
            job = ctx.timeline_job(job_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "comments": comments_for(job.output, clip_id)}

    @register
    def videoflow_add_clip_comment(
        clip_id: str, text: str, author: str = "", job_id: str | None = None
    ) -> dict[str, object]:
        """Add a comment to a timeline clip."""

        from uuid import uuid4

        try:
            job = ctx.timeline_job(job_id)
            meta = add_comment(
                job.output,
                comment_id=f"comment-{uuid4().hex[:10]}",
                clip_id=clip_id,
                text=text,
                author=author,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "comment": next(
                item.model_dump() for item in meta.comments if item.clip_id == clip_id
            ),
        }

    @register
    def videoflow_remove_clip_comment(
        comment_id: str, job_id: str | None = None
    ) -> dict[str, object]:
        """Remove one clip comment."""

        try:
            job = ctx.timeline_job(job_id)
            remove_comment(job.output, comment_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "deleted": comment_id}

    @register
    def videoflow_copilot_recipe(prompt: str) -> dict[str, object]:
        """Draft and validate a recipe from a natural-language request."""

        try:
            recipe = propose_recipe(build_llm(), prompt)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "recipe": recipe.model_dump(mode="json")}

    @register
    def videoflow_copilot_timeline(
        prompt: str, apply: bool = False, job_id: str | None = None
    ) -> dict[str, object]:
        """Propose (or apply) validated timeline edits from a request."""

        try:
            job = ctx.timeline_job(job_id)
            state = ctx.state_for_job(job)
            if state is None:
                raise StateNotReadyError("The job has no project state.")
            fps = (
                state.media_info.fps_num / state.media_info.fps_den
                if state.media_info is not None
                else 30.0
            )
            edits = propose_timeline_edits(
                build_llm(),
                prompt,
                [
                    {
                        "id": clip.clip_id,
                        "start_sec": clip.timeline_in_frame / fps,
                        "end_sec": clip.timeline_out_frame / fps,
                    }
                    for clip in state.video_segments
                ],
            )
            if apply:
                state_path = Path(
                    str(
                        (job.result or {}).get("state_path")
                        or job.output / "project_state.json"
                    )
                )
                history = TimelineHistory(job.output / "timeline_history.json")
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
                working = working.model_copy(
                    update={"revision": previous.revision + 1}
                )
                state_path.write_text(
                    working.model_dump_json(indent=2) + "\n", encoding="utf-8"
                )
                state = working
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "edits": edits,
            "applied": apply,
            "revision": state.revision,
        }
