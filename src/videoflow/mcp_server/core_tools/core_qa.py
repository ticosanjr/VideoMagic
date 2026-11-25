"""VideoFlow core MCP tools: Shorts, QA and storyboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.agent_helpers import _job_payload
from videoflow.mcp_server.context import error

from .core_shared import (
    _fps_int,
    _short_clip_for_video,
    _wait,
)


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    manager = ctx.manager

    @register
    def vf_shorts_batch(
        project_id: str,
        clips: list[dict[str, Any]],
        wait: bool = True,
    ) -> dict[str, Any]:
        """Render several Shorts in one batch with per-clip settings."""

        try:
            record = get_project(project_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        job = manager.start(
            Path(record.primary_source or record.output),
            Path(record.output),
            {
                "mode": "shorts_batch",
                "project_id": record.project_id,
                "clips": clips,
            },
            queue=True,
            project_id=record.project_id,
        )
        response: dict[str, Any] = {
            "ok": True,
            "project_id": project_id,
            "job": _job_payload(job),
        }
        if wait:
            response["wait"] = _wait(manager, project_id, str(job.job_id), 1800.0)
        return response

    @register
    def vf_qa_final(
        project_id: str,
        video_path: str = "",
        strict: bool = True,
        platforms: list[str] | None = None,
        mode: str = "full",
        collision_mode: str = "visual",
        max_wer: float = 0.12,
        compute_policy: str = "auto",
        allow_slow_cpu_fallback: bool = True,
    ) -> dict[str, Any]:
        """Audit the deliverable MP4 and write a contact sheet."""

        requested = str(mode or "full").strip().lower()
        if requested in {"skip", "off", "none"}:
            return {
                "ok": True,
                "status": "skipped",
                "mode": requested,
                "report": {"ok": True, "skipped": True, "mode": requested},
            }
        skip_wer = requested == "preview"
        if skip_wer:
            mode = "fast"
        elif requested in {"fast", "full"}:
            mode = requested
        else:
            return error(
                "invalid_qa_mode",
                "mode must be fast, full, preview, skip, or off",
            )

        from videoflow.application.qa_final import audit_final
        from videoflow.application.shorts import short_dimensions

        try:
            record = get_project(project_id)
            state = load_project_state(record)
            output = Path(record.output)
            default = output / "exports" / "youtube_master.mp4"
            fallback = output / "exports" / "final_youtube.mp4"
            video = (
                Path(video_path).expanduser()
                if video_path
                else (default if default.is_file() else fallback)
            )
            clip = _short_clip_for_video(output, video)
            if clip is None:
                import json

                bundle_fps: int | None = None
                bundle_frames: int | None = None
                bundle_path = output / "exports" / "bundle.json"
                try:
                    bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
                    bundle_fps = _fps_int(
                        (bundle_payload.get("mp4") or {}).get("fps")
                    )
                    frames = bundle_payload.get("mp4_frames")
                    bundle_frames = int(frames) if frames else None
                except (OSError, ValueError, TypeError):
                    pass
                report = audit_final(
                    video,
                    output=output,
                    state=state,
                    strict=strict,
                    platforms=platforms,
                    mode=mode,
                    fps=float(bundle_fps) if bundle_fps else None,
                    expected_frames=bundle_frames,
                    collision_mode=collision_mode,
                    max_wer=max_wer,
                    skip_wer=skip_wer,
                    compute_policy=compute_policy,
                    allow_slow_cpu_fallback=allow_slow_cpu_fallback,
                )
            else:
                start = float(clip.get("start_sec") or 0.0)
                end = float(clip.get("end_sec") or start)
                aspect = str(clip.get("aspect_ratio") or "9:16")
                clip_width, clip_height = short_dimensions(aspect)
                rate = state.media_info.audio_sample_rate if state.media_info else 48000
                transcript = [
                    item
                    for item in state.transcript
                    if item.end_sample > round(start * rate)
                    and item.start_sample < round(end * rate)
                    and item.id not in set(state.pipeline.discard_sentence_ids)
                ]
                subtitles = str(clip.get("subtitles") or "")
                subtitle_path = Path(subtitles).expanduser() if subtitles else None
                if subtitle_path is not None and not subtitle_path.is_absolute():
                    subtitle_path = output / subtitle_path
                report = audit_final(
                    video,
                    output=output,
                    state=state,
                    strict=strict,
                    platforms=platforms,
                    mode=mode,
                    window_sec=(start, end),
                    expected_sec=max(0.0, end - start),
                    fps=float(clip.get("fps") or 30.0),
                    transcript=transcript,
                    caption_path=subtitle_path,
                    width=clip_width,
                    height=clip_height,
                    collision_mode=collision_mode,
                    max_wer=max_wer,
                    skip_wer=skip_wer,
                    compute_policy=compute_policy,
                    allow_slow_cpu_fallback=allow_slow_cpu_fallback,
                )
                report["short"] = {
                    "title": clip.get("title", ""),
                    "start_sec": start,
                    "end_sec": end,
                    "aspect_ratio": aspect,
                }
        except (VideoFlowError, OSError, ValueError) as exc:
            return error("qa_final_failed", str(exc))
        return {"ok": bool(report.get("ok")), "report": report}

    @register
    def vf_qa_compare(
        project_id: str,
        report_a: str,
        report_b: str,
    ) -> dict[str, Any]:
        """Compare two immutable QA reports for regressions."""

        from videoflow.application.qa_store import QaStore

        if not report_a or not report_b:
            return error("qa_reports_required", "report_a and report_b are required")
        try:
            record = get_project(project_id)
            output = Path(record.output)

            def resolve(value: str) -> Path:
                path = Path(value).expanduser()
                return path if path.is_absolute() else output / path

            return QaStore(output).compare(resolve(report_a), resolve(report_b))
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def vf_glossary(
        action: str = "list",
        channel_id: str = "",
        terms: list[dict[str, Any]] | None = None,
        text: str = "",
    ) -> dict[str, Any]:
        """List, update, or apply a channel glossary of technical terms."""

        from videoflow.application.glossary import (
            apply_glossary,
            load_glossary,
            upsert_glossary,
        )

        try:
            if action == "list":
                return load_glossary(channel_id)
            if action == "upsert":
                return upsert_glossary(channel_id, list(terms or []))
            if action == "apply":
                corrected, count = apply_glossary(
                    text, load_glossary(channel_id)["terms"]
                )
                return {
                    "ok": True,
                    "channel_id": channel_id,
                    "text": corrected,
                    "applied": count,
                }
            return error(
                "unknown_action",
                "vf_glossary supports list, upsert, or apply",
            )
        except (OSError, ValueError) as exc:
            return error("glossary_failed", str(exc))

    @register
    def vf_storyboard_strip(
        project_id: str,
        source_id: str = "",
        start_sec: float = 0.0,
        end_sec: float = 0.0,
        cols: int = 5,
        annotate: bool = True,
    ) -> dict[str, Any]:
        """Render a 5x2 contact sheet of one timeline/source range."""

        from videoflow.application.storyboard_strip import build_storyboard_strip

        try:
            record = get_project(project_id)
            state = load_project_state(record)
            media = state.source_media(source_id) if source_id else state.media_info
            source = Path(
                media.source_path if media is not None else record.primary_source
            )
            if not source.is_file():
                return error("source_not_found", f"Source is missing: {source}")
            result = build_storyboard_strip(
                source,
                record.output,
                start_sec=start_sec,
                end_sec=end_sec,
                cols=cols,
                annotate=annotate,
            )
            return {"ok": True, "project_id": project_id, "storyboard": result}
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("storyboard_failed", str(exc))
