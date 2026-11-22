"""Agent-facing MCP surface: project-scoped, explicit, and context-efficient."""

from __future__ import annotations

import resource
from pathlib import Path
from typing import Any

from videoflow.application import artifacts as artifact_service
from videoflow.application.capabilities import capability_manifest
from videoflow.application.hilt import public_payload, respond
from videoflow.application.projects import (
    get_project,
    init_project,
    load_project_state,
    project_uuid,
    save_project_state,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError, VideoFlowError
from videoflow.engine.recipes.catalog import parse_recipe
from videoflow.mcp_server.agent_helpers import (
    _adopt_job,
    _context,
    _job,
    _job_belongs,
    _job_payload,
    _record,
    _resources,
    _state,
    _summary,
)
from videoflow.mcp_server.context import error
from videoflow.runtime import allowed_roots
from videoflow.steps.base import StepIO


def register_agent_tools(register: Any, ctx: Any) -> None:
    manager = ctx.manager

    @register
    def vf_project_init(
        project_id: str = "",
        name: str = "",
        output: str = "",
        sources: list[str] | None = None,
        channel_id: str = "",
        style_id: str = "",
    ) -> dict[str, Any]:
        """Create or adopt a project. Returns the stable project_id and resources."""

        try:
            record = get_project(project_id) if project_id else None
            if record is None:
                if not output:
                    if not project_id:
                        return error(
                            "output_required",
                            "Pass project_id or output when creating a project",
                        )
                    from vf_shared.contracts.workspace import project_dir as workspace_project_dir

                    output = str(workspace_project_dir(project_id))
                record, state = init_project(
                    name=name,
                    output=output,
                    sources=sources or [],
                    project_id=project_id or None,
                    channel_id=channel_id,
                    style_id=style_id,
                )
            else:
                state = _state(record)
                if sources or channel_id or style_id:
                    record, state = init_project(
                        name=record.name,
                        output=record.output,
                        sources=sources or [],
                        project_id=record.project_id,
                        channel_id=channel_id or record.channel_id,
                        style_id=style_id or record.style_id,
                    )
                return {
                    "ok": True,
                    "project": record.to_dict(),
                    "summary": _summary(state),
                    "resources": _resources(record.project_id),
                }
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "project": record.to_dict(),
            "summary": _summary(state),
            "resources": _resources(record.project_id),
        }

    @register
    def vf_project_status(project_id: str) -> dict[str, Any]:
        """Return project state, jobs, and artifact counts."""

        try:
            record = _record(project_id)
            state = _state(record)
            jobs = [
                {
                    "job_id": str(job.job_id),
                    "status": job.status,
                    "stage": job.stage,
                    "progress": job.progress,
                    "message": job.message,
                    "created_at": job.created_at,
                }
                for job in manager.list()
                if _job_belongs(job, record)
            ]
            artifacts = artifact_service.list_artifacts(Path(record.output))
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "project": record.to_dict(),
            "summary": _summary(state),
            "jobs": jobs,
            "artifact_count": len(artifacts),
            "resources": _resources(project_id),
        }

    @register
    def vf_capabilities(allow_external_services: bool = False) -> dict[str, Any]:
        """Return backend and provider availability."""

        return {
            "ok": True,
            "capabilities": capability_manifest(allow_external_services=allow_external_services),
        }

    @register
    def vf_get_job(project_id: str, job_id: str = "") -> dict[str, Any]:
        """Return one job with artifacts and QA summary."""

        try:
            job = _job(manager, project_id, job_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "job": _job_payload(job)}

    @register
    def vf_get_step_logs(
        project_id: str,
        job_id: str = "",
        step_id: str = "",
        tail_lines: int = 100,
    ) -> dict[str, Any]:
        """Return bounded logs, commands, timing, and memory for a job/step."""

        try:
            job = _job(manager, project_id, job_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        limit = max(1, min(2000, int(tail_lines)))
        logs = job.telemetry.logs(limit=limit)
        if step_id:
            logs = [
                item
                for item in logs
                if step_id in str(item.get("module", "")) or step_id in str(item.get("message", ""))
            ]
        if not logs:
            log_path = Path(job.output) / "job.log"
            if log_path.is_file():
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                logs = [{"line": line} for line in lines[-limit:]]
        commands = [
            item["message"]
            for item in logs
            if isinstance(item, dict) and str(item.get("message", "")).lstrip().startswith("$ ")
        ]
        return {
            "ok": True,
            "project_id": project_id,
            "job_id": str(job.job_id),
            "step_id": step_id,
            "status": job.status,
            "stage": job.stage,
            "stages": job.telemetry.stages(),
            "logs": logs,
            "commands": commands[-50:],
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "log_resource": f"vf://projects/{project_id}/jobs/{job.job_id}/logs",
        }

    @register
    def vf_get_qa_artifacts(project_id: str, include_images: bool = False) -> list[Any]:
        """Return QA defects, failed frame paths, and optionally image content."""

        try:
            record = _record(project_id)
            payload = artifact_service.qa_artifacts(Path(record.output))
        except VideoFlowError as exc:
            return [exc.to_dict()]
        result: list[Any] = [
            {
                "ok": True,
                "project_id": project_id,
                "defects": payload["defects"],
                "reports": payload["reports"],
                "frames": payload["frames"],
                "frame_count": len(payload["frames"]),
            }
        ]
        if include_images:
            from mcp.server.mcpserver import Image

            for frame in payload["frames"][:8]:
                result.append(Image(path=str(frame["path"])))
        return result

    @register
    def vf_get_timeline(project_id: str, job_id: str = "") -> dict[str, Any]:
        """Return the canonical timeline with per-clip source ids."""

        try:
            record = _record(project_id)
            state = _state(record)
            if state is None:
                if job_id:
                    _job(manager, project_id, job_id)
                    state = _state(record)
                if state is None:
                    raise StateNotReadyError("Project has no timeline yet")
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "project_id": project_id,
            "revision": state.revision,
            "fps": (
                state.media_info.fps_num / state.media_info.fps_den
                if state.media_info is not None
                else 30.0
            ),
            "primary_source_id": state.primary_source_id,
            "sources": _summary(state)["sources"],
            "video": [item.model_dump(mode="json") for item in state.video_segments],
            "audio": [item.model_dump(mode="json") for item in state.audio_segments],
            "overlays": [item.model_dump(mode="json") for item in state.overlays],
        }

    @register
    def vf_edit_timeline(
        project_id: str,
        clip_id: str,
        action: str,
        start_sec: float | None = None,
        end_sec: float | None = None,
        delta_sec: float = 0.0,
        split_sec: float | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Edit one clip with optimistic concurrency."""

        from videoflow.application.timeline_edit import TimelineEdit, apply_timeline_edit
        from videoflow.application.timeline_history import TimelineHistory

        try:
            record = _record(project_id)
            state = load_project_state(record)
            if expected_revision is not None and state.revision != expected_revision:
                return error(
                    "revision_conflict",
                    f"Expected revision {expected_revision}, current {state.revision}",
                )
            history = TimelineHistory(Path(record.output) / "timeline_history.json")
            previous = state.model_copy(deep=True)
            updated = apply_timeline_edit(
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
            state = save_project_state(
                record,
                updated,
                expected_revision=expected_revision,
                bump_revision=True,
                snapshot=True,
                snapshot_reason=f"timeline_edit:{action}",
                snapshot_step="timeline_edit",
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "revision": state.revision, "can_undo": history.can_undo}

    @register
    def vf_get_artifact(
        project_id: str,
        artifact: str,
        include_content: bool = True,
    ) -> list[Any]:
        """Return one artifact metadata and, for images, MCP image content."""

        try:
            record = _record(project_id)
            path = artifact_service.find_artifact(Path(record.output), artifact)
            payload = artifact_service.artifact_payload(Path(record.output), path)
        except VideoFlowError as exc:
            return [exc.to_dict()]
        result: list[Any] = [{"ok": True, **payload}]
        if include_content and payload["kind"] == "image":
            from mcp.server.mcpserver import Image

            result.append(Image(path=str(path)))
        return result

    @register
    def vf_edit_short(
        project_id: str,
        job_id: str = "",
        index: int = 0,
        title: str | None = None,
        start_sec: float | None = None,
        end_sec: float | None = None,
        aspect_ratio: str | None = None,
        burn_subtitles: bool | None = None,
        caption_style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Re-render one completed Short."""

        from videoflow.application.short_editor import ShortEditOptions, edit_short

        try:
            record = _record(project_id)
            job = _job(manager, project_id, job_id)
            result = edit_short(
                source=Path(job.source),
                output=Path(record.output),
                index=index,
                result=dict(job.result or {}),
                options=ShortEditOptions(
                    title=title,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    aspect_ratio=aspect_ratio,
                    burn_subtitles=burn_subtitles,
                    caption_style=caption_style,
                ),
            )
            manager.update_result(str(job.job_id), result)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "project_id": project_id, "short": result.get("shorts", [])[index]}

    @register
    def vf_nle_roundtrip(
        project_id: str,
        direction: str = "pull",
        nle: str = "fcpxml",
        path: str = "",
        apply: bool = False,
    ) -> dict[str, Any]:
        """Push/pull markers and cuts through FCPXML/MLT or Resolve."""

        from videoflow.steps.nle_sync import NleSyncParams, NleSyncStep

        try:
            record = _record(project_id)
            state = load_project_state(record)
            try:
                job = _job(manager, project_id, "")
                context = _context(record, job)
            except StateNotReadyError:
                source = state.source_media()
                context = PipelineContext(
                    source=Path(source.source_path) if source is not None else Path(record.output),
                    output=Path(record.output),
                    work=Path(record.output) / "work",
                    exports=Path(record.output) / "exports",
                    media=state.media_info,
                    state=state,
                    transcript=list(state.transcript),
                    metadata={"project_id": record.project_id},
                )
            target_path = path
            if direction == "push":
                from videoflow.exporters.fcpxml import export_fcpxml
                from videoflow.exporters.kdenlive import export_kdenlive
                from videoflow.exporters.xmeml import export_xmeml

                if context.state is None:
                    raise StateNotReadyError("Project has no timeline")
                if nle in {"premiere", "xmeml"}:
                    suffix, exporter = ".xml", export_xmeml
                elif nle in {"kdenlive", "mlt"}:
                    suffix, exporter = ".kdenlive", export_kdenlive
                else:
                    suffix, exporter = ".fcpxml", export_fcpxml
                destination = (
                    Path(path) if path else Path(record.output) / "exports" / f"timeline{suffix}"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                exporter(context.state, destination)
                target_path = str(destination)
            if nle == "resolve":
                from videoflow.adapters.resolve import resolve_roundtrip

                report = resolve_roundtrip(
                    context,
                    direction=direction,
                    path=target_path,
                    apply=apply,
                )
            else:
                step = NleSyncStep()
                step.run(
                    context,
                    NleSyncParams(
                        format=(
                            "xmeml"
                            if nle in {"premiere", "xmeml"}
                            else "mlt"
                            if nle in {"kdenlive", "mlt"}
                            else "fcpxml"
                        ),
                        path=target_path,
                        apply=apply,
                    ),
                    StepIO(stage="nle.sync_back"),
                )
                if context.state is not None:
                    state = context.state.model_copy(
                        update={"project_id": project_uuid(record.project_id)}
                    )
                    save_project_state(record, state, bump_revision=False)
                report = context.metadata.get("sync_back_report", {})
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "direction": direction, "nle": nle, "report": report}

    @register
    def vf_validate_exports(project_id: str, job_id: str = "") -> dict[str, Any]:
        """Cross-validate FCPXML, XMEML, and Kdenlive against the timeline."""

        from videoflow.application.delivery_bundle import blocked_paths, timeline_frames
        from videoflow.application.nle_validation import validate_nle_exports
        from videoflow.domains.media import license_blockers

        try:
            record = _record(project_id)
            job = _job(manager, project_id, job_id)
            output = Path(job.output)
            state = load_project_state(record)
            report = validate_nle_exports(
                output / "exports",
                timeline_frames=timeline_frames(state) if state.video_segments else None,
                blocked_paths=blocked_paths(license_blockers(output, state), output),
                check_media=True,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": bool(report.get("ok")), "report": report}

    @register
    def vf_respond_interaction(
        project_id: str,
        interaction_id: str,
        action: str = "submit",
        answers: dict[str, Any] | None = None,
        comment: str = "",
        job_id: str = "",
        channel: str = "local",
        token: str = "",
    ) -> dict[str, Any]:
        """Answer a HITL request and resume the job."""

        try:
            record = _record(project_id)
            job = _job(manager, project_id, job_id)
            request, response = respond(
                Path(job.output),
                str(job.job_id),
                interaction_id,
                action=action,
                answers=answers,
                comment=comment,
                channel=channel,
                token=token,
            )
            resumed = manager.start(
                job.source,
                job.output,
                {**job.options, "resume": True, "project_id": record.project_id},
                queue=True,
                project_id=record.project_id,
                finalizer=lambda finished: _adopt_job(record, finished),
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "request": public_payload(Path(job.output), request, response),
            "job": resumed.to_dict(),
        }

    @register
    def vf_ingest_session(
        project_id: str,
        sources: list[str] | None = None,
        raw_dir: str = "",
        order: str = "auto",
        target_fps: float = 0.0,
        target_width: int = 0,
        target_height: int = 0,
        normalize: bool = False,
        queue: bool = True,
    ) -> dict[str, Any]:
        """Start a multi-take session ingest job."""

        from videoflow.domain.paths import resolve_allowed
        from videoflow.steps.session_ingest import (
            SessionIngestParams,
        )

        try:
            record = _record(project_id)
            paths = list(sources or [])
            if raw_dir:
                directory = resolve_allowed(Path(raw_dir), allowed_roots())
                if not directory.is_dir():
                    raise StateNotReadyError(f"raw_dir is not a directory: {directory}")
                paths.extend(
                    str(path)
                    for path in sorted(directory.iterdir())
                    if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".mkv", ".m4v"}
                )
            if not paths:
                raise StateNotReadyError("Pass sources or raw_dir")
            params = SessionIngestParams(
                sources=paths,
                order=order,  # type: ignore[arg-type]
                target_fps=target_fps,
                target_width=target_width,
                target_height=target_height,
                normalize=normalize,
            )
            recipe = {
                "id": "session_ingest",
                "name": "Session ingest",
                "steps": [
                    {
                        "id": "session",
                        "type": "session.ingest",
                        "needs": [],
                        "params": params.model_dump(mode="json"),
                    }
                ],
            }
            job = manager.start(
                Path(paths[0]).expanduser(),
                Path(record.output),
                {
                    "mode": "recipe",
                    "recipe": parse_recipe(recipe).model_dump(mode="json"),
                    "resume": False,
                    "project_id": record.project_id,
                },
                queue=queue,
                project_id=record.project_id,
                finalizer=lambda finished: _adopt_job(record, finished),
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "job": _job_payload(job), "project_id": project_id}

    @register
    def vf_sync_multicam(
        project_id: str,
        primary_source_id: str = "",
        secondary_source_id: str = "",
        apply: bool = False,
        min_confidence: float = 0.2,
        compose: str = "none",
        pip_position: str = "top_right",
        pip_width_ratio: float = 0.28,
    ) -> dict[str, Any]:
        """Synchronize two sources by audio cross-correlation."""

        from videoflow.application.multicam import sync_multicam

        try:
            record = _record(project_id)
            state = load_project_state(record)
            report = sync_multicam(
                state,
                Path(record.output) / "work" / "multicam",
                primary_source_id=primary_source_id,
                secondary_source_id=secondary_source_id,
                apply=apply,
                min_confidence=min_confidence,
                compose=compose,
                pip_position=pip_position,
                pip_width_ratio=pip_width_ratio,
            )
            if apply:
                save_project_state(record, report["state"], bump_revision=False)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "report": {key: value for key, value in report.items() if key != "state"},
        }

    @register
    def vf_render_start(
        project_id: str,
        kind: str = "timeline",
        crf: int = 20,
        preset: str = "veryfast",
        width: int = 0,
        height: int = 0,
        draft_scale: float = 1.0,
    ) -> dict[str, Any]:
        """Start a timeline or preview render job."""

        try:
            record = _record(project_id)
            state = load_project_state(record)
            source = (
                Path(state.media_info.source_path)
                if state.media_info is not None
                else Path(record.output) / "source.mp4"
            )
            job = manager.start(
                source,
                Path(record.output),
                {
                    "mode": "render",
                    "project_id": record.project_id,
                    "kind": kind,
                    "crf": crf,
                    "preset": preset,
                    "width": width,
                    "height": height,
                    "draft_scale": draft_scale,
                },
                queue=True,
                project_id=record.project_id,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "project_id": project_id, "job": _job_payload(job)}
