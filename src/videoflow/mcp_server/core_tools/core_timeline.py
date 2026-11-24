"""VideoFlow core MCP tools: timeline and ingest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error, unknown_action

from .core_shared import (
    _wait,
)


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    manager = ctx.manager

    @register
    def vf_timeline(
        action: str = "get",
        project_id: str = "",
        job_id: str = "",
        clip_id: str = "",
        edit_action: str = "trim",
        start_sec: float | None = None,
        end_sec: float | None = None,
        delta_sec: float = 0.0,
        split_sec: float | None = None,
        expected_revision: int | None = None,
        beatmap: dict[str, Any] | None = None,
        beat_map_path: str = "",
        time_basis: str = "timeline",
        keep_ranges: list[dict[str, Any]] | None = None,
        remove_ranges: list[dict[str, Any]] | None = None,
        sentence_ids: list[int] | None = None,
        page: int = 1,
        page_size: int = 30,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Read, edit, discard sentences, or apply a declarative beatmap."""

        if action not in {"get", "discard_sentences", "apply_beatmap", "edit"}:
            return unknown_action(
                "vf_timeline",
                action,
                ("get", "edit", "discard_sentences", "apply_beatmap"),
            )
        if action == "discard_sentences":
            if not sentence_ids:
                return error("sentence_ids_required", "sentence_ids is required")
            from videoflow.application.projects import save_project_state

            try:
                record = get_project(project_id)
                state = load_project_state(record)
                discarded = set(state.pipeline.discard_sentence_ids)
                discarded.update(int(item) for item in sentence_ids)
                updated = state.model_copy(
                    update={
                        "pipeline": state.pipeline.model_copy(
                            update={"discard_sentence_ids": sorted(discarded)}
                        )
                    }
                )
                saved = save_project_state(
                    record,
                    updated,
                    expected_revision=expected_revision,
                    bump_revision=True,
                    snapshot=True,
                    snapshot_reason="discard_sentences",
                    snapshot_step="discard_sentences",
                )
                return {
                    "ok": True,
                    "project_id": project_id,
                    "discarded_sentence_ids": sorted(discarded),
                    "revision": saved.revision,
                }
            except VideoFlowError as exc:
                return exc.to_dict()
        if action == "apply_beatmap":
            from videoflow.application.beatmap import (
                BeatmapError,
                apply_beatmap,
                write_beatmap_sidecar,
            )
            from videoflow.application.projects import save_project_state

            if not beatmap and not beat_map_path and not keep_ranges and not remove_ranges:
                return error("beatmap_required", "Pass a beatmap manifest or ranges")
            if time_basis not in {"edited", "timeline", "source"}:
                return error(
                    "invalid_time_basis",
                    "time_basis must be edited, timeline, or source",
                )
            manifest: dict[str, Any] = {}
            if beat_map_path:
                try:
                    record = get_project(project_id)
                    path = Path(beat_map_path).expanduser()
                    if not path.is_absolute():
                        path = Path(record.output) / path
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, VideoFlowError) as exc:
                    return error("beatmap_path_invalid", str(exc))
                if not isinstance(payload, dict):
                    return error("beatmap_path_invalid", "Beat map must be a JSON object")
                manifest.update(payload)
            manifest.update(dict(beatmap or {}))
            if keep_ranges is not None:
                manifest["keep_ranges"] = keep_ranges
            if remove_ranges is not None:
                manifest["remove_ranges"] = remove_ranges
            manifest["time_basis"] = "timeline" if time_basis == "edited" else time_basis
            try:
                record = get_project(project_id)
                state = load_project_state(record)
                updated, report, sidecar = apply_beatmap(
                    state,
                    Path(record.output),
                    manifest,
                    expected_revision=expected_revision,
                    time_basis=(
                        "timeline" if time_basis == "edited" else time_basis
                    ),  # type: ignore[arg-type]
                    dry_run=dry_run,
                    force=force,
                )
                if dry_run:
                    return {
                        "ok": True,
                        "dry_run": True,
                        "revision": state.revision,
                        "report": report.to_dict(),
                        "sidecar": "",
                    }
                saved = save_project_state(
                    record,
                    updated,
                    expected_revision=expected_revision,
                    bump_revision=True,
                    snapshot=True,
                    snapshot_reason="apply_beatmap",
                    snapshot_step="apply_beatmap",
                )
                sidecar_path = ""
                if sidecar.get("sfx_events") or sidecar.get("music_tracks"):
                    sidecar_path = str(write_beatmap_sidecar(Path(record.output), sidecar))
                return {
                    "ok": True,
                    "revision": saved.revision,
                    "report": report.to_dict(),
                    "sidecar": sidecar_path,
                }
            except BeatmapError as exc:
                return {
                    "ok": False,
                    "code": "beatmap_conflict",
                    "message": str(exc),
                    "report": exc.report.to_dict(),
                }
            except ValueError as exc:
                return error("invalid_beatmap_range", str(exc))
            except VideoFlowError as exc:
                return exc.to_dict()
        if action == "edit":
            if time_basis == "source":
                from videoflow.application.time_map import source_to_timeline_sec

                try:
                    state = load_project_state(get_project(project_id))
                    if start_sec is not None:
                        start_sec = source_to_timeline_sec(state, start_sec)
                    if end_sec is not None:
                        end_sec = source_to_timeline_sec(state, end_sec)
                    if split_sec is not None:
                        split_sec = source_to_timeline_sec(state, split_sec)
                except VideoFlowError as exc:
                    return exc.to_dict()
                except ValueError as exc:
                    return error("time_outside_timeline", str(exc))
            elif time_basis != "timeline":
                return error("invalid_time_basis", "time_basis must be timeline or source")
            return legacy["vf_edit_timeline"](
                project_id=project_id,
                clip_id=clip_id,
                action=edit_action,
                start_sec=start_sec,
                end_sec=end_sec,
                delta_sec=delta_sec,
                split_sec=split_sec,
                expected_revision=expected_revision,
            )
        result = legacy["vf_get_timeline"](project_id=project_id, job_id=job_id)
        if not isinstance(result, dict) or result.get("ok") is False:
            return result
        video = list(result.get("video") or [])
        audio = list(result.get("audio") or [])
        size = max(1, min(200, int(page_size or 30)))
        page_number = max(1, int(page or 1))
        start = (page_number - 1) * size
        fps = float(result.get("fps") or 30.0) or 30.0
        total_duration = sum(
            float(item.get("timeline_out_frame") or 0)
            - float(item.get("timeline_in_frame") or 0)
            for item in video
            if isinstance(item, dict)
        ) / fps
        payload: dict[str, Any] = {
            "ok": True,
            "total_clips": len(video),
            "total_duration_sec": round(total_duration, 3),
            "page": page_number,
            "page_size": size,
            "has_more": start + size < len(video),
        }
        payload.update(
            {
                key: value
                for key, value in result.items()
                if key not in {"video", "audio"}
            }
        )
        payload["video"] = video[start : start + size]
        payload["audio"] = audio[start : start + size]
        return payload

    @register
    def vf_ingest(
        action: str = "session",
        project_id: str = "",
        sources: list[str] | None = None,
        raw_dir: str = "",
        order: str = "auto",
        target_fps: float = 0.0,
        target_width: int = 0,
        target_height: int = 0,
        normalize: bool = False,
        primary_source_id: str = "",
        secondary_source_id: str = "",
        apply: bool = False,
        min_confidence: float = 0.2,
        compose: str = "none",
        pip_position: str = "top_right",
        pip_width_ratio: float = 0.28,
        wait: bool = False,
        timeout_sec: float = 1800.0,
    ) -> dict[str, Any]:
        """Run session ingest, multicam synchronization, or audio diagnosis."""

        if action not in {"session", "multicam", "diagnose", "probe"}:
            return unknown_action(
                "vf_ingest",
                action,
                ("session", "multicam", "diagnose", "probe"),
            )
        if action == "probe":
            from videoflow.adapters.ffmpeg import FFmpegAdapter
            from videoflow.domain.paths import resolve_allowed
            from videoflow.runtime import allowed_roots

            candidate = str(sources[0]) if sources else ""
            if not candidate and project_id:
                try:
                    record = get_project(project_id)
                    state = load_project_state(record)
                    media = state.media_info
                    candidate = media.source_path if media is not None else record.primary_source
                except VideoFlowError as exc:
                    return exc.to_dict()
            if not candidate:
                return error("source_required", "Pass sources or project_id to probe")
            try:
                path = resolve_allowed(Path(candidate).expanduser(), allowed_roots())
                media_info = FFmpegAdapter().probe(path)
            except VideoFlowError as exc:
                return exc.to_dict()
            return {
                "ok": True,
                "project_id": project_id,
                "source": str(path),
                "probe": media_info.model_dump(mode="json"),
            }
        if action == "diagnose":
            from videoflow.domains.audio.diagnose import diagnose_audio

            try:
                record = get_project(project_id)
                state = load_project_state(record)
                media = state.media_info
                source = Path(
                    media.source_path if media is not None else record.primary_source
                )
                if not source.is_file():
                    return error("source_not_found", f"Source is missing: {source}")
                return {
                    "ok": True,
                    "project_id": project_id,
                    "audio_diagnosis": diagnose_audio(source, media),
                }
            except VideoFlowError as exc:
                return exc.to_dict()
        mode = "multicam" if action == "multicam" else "session"
        step_type = "sync.multicam_audio" if mode == "multicam" else "session.ingest"
        if mode == "multicam":
            response = legacy["vf_sync_multicam"](
                project_id=project_id,
                primary_source_id=primary_source_id,
                secondary_source_id=secondary_source_id,
                apply=apply,
                min_confidence=min_confidence,
                compose=compose,
                pip_position=pip_position,
                pip_width_ratio=pip_width_ratio,
            )
        else:
            response = legacy["vf_ingest_session"](
                project_id=project_id,
                sources=sources,
                raw_dir=raw_dir,
                order=order,
                target_fps=target_fps,
                target_width=target_width,
                target_height=target_height,
                normalize=normalize,
            )
            if wait and response.get("ok"):
                job_id = str((response.get("job") or {}).get("job_id") or "")
                if job_id:
                    response["wait"] = _wait(manager, project_id, job_id, timeout_sec)
        if not response.get("ok"):
            return response
        response["mode"] = mode
        response["step_type"] = step_type
        try:
            state = load_project_state(get_project(project_id))
            media = state.media_info
            if media is not None and media.fps_num:
                response["source_duration_sec"] = round(
                    media.duration_frames / (media.fps_num / media.fps_den), 6
                )
                response["cfr_fps"] = round(media.fps_num / media.fps_den, 6)
            else:
                response["source_duration_sec"] = 0.0
                response["cfr_fps"] = 0.0
            response["pcm_path"] = state.pipeline.pcm_path
            offset_samples = state.source_offsets.get(state.primary_source_id, 0)
            rate = media.audio_sample_rate if media is not None else 48000
            response["audio_offset_ms"] = round(offset_samples / max(1, rate) * 1000, 3)
            if media is not None:
                from videoflow.domains.audio.diagnose import diagnose_audio

                try:
                    response["audio_diagnosis"] = diagnose_audio(
                        media.source_path, media
                    )
                except Exception as exc:  # noqa: BLE001 - diagnosis is advisory
                    response["audio_diagnosis"] = {
                        "ok": False,
                        "error": str(exc),
                    }
        except VideoFlowError:
            response.setdefault("source_duration_sec", 0.0)
            response.setdefault("cfr_fps", 0.0)
            response.setdefault("pcm_path", "")
            response.setdefault("audio_offset_ms", 0.0)
        return response
