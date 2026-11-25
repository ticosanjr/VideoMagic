"""VideoFlow core MCP tools: export and delivery bundles."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.agent_helpers import _job_payload
from videoflow.mcp_server.context import error, unknown_action

from .core_shared import (
    _fps_int,
    _wait,
)


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    manager = ctx.manager

    def _run_bundle(
        project_id: str,
        *,
        targets: str | list[str] | None = None,
        look: dict[str, Any] | None = None,
        audio_source: str = "master",
        captions: bool = True,
        draft: bool = False,
        dialect: str = "1.10",
        mp4_profile: str = "youtube_h264",
        mp4_loudness_lufs: float | None = -16.0,
        fps: int | str = 30,
        qa_mode: str = "fast",
        mp4_preset: str = "veryfast",
        compute_policy: str = "auto",
        allow_slow_cpu_fallback: bool = True,
        mode: Literal["final", "preview"] = "final",
        draft_scale: float = 1.0,
    ) -> dict[str, Any]:
        from videoflow.application.delivery_bundle import (
            DEFAULT_BUNDLE_TARGETS,
            DeliveryBundleRequest,
            build_delivery_bundle,
        )

        requested = [targets] if isinstance(targets, str) else targets
        record = get_project(project_id)
        state = load_project_state(record)
        if not state.video_segments:
            from videoflow.application.delivery_bundle import TimelineRequiredError

            raise TimelineRequiredError("Project has no built timeline")
        if not requested:
            style_id = record.style_id or record.channel_id
            if style_id:
                from videoflow.application.style_catalog import StyleCatalog
                from videoflow.domain.errors import StyleNotFoundError

                try:
                    requested = StyleCatalog().get(style_id).export_targets
                except StyleNotFoundError:
                    requested = None
        requested = requested or list(DEFAULT_BUNDLE_TARGETS)
        if record.channel_id:
            from videoflow.application.brand_kit import load_brand_kit

            brand = load_brand_kit(record.channel_id)
            if brand.get("lut"):
                merged = dict(look or {})
                merged.setdefault("lut_path", str(brand["lut"]))
                look = merged
        bundle = build_delivery_bundle(
            state,
            Path(record.output),
            request=DeliveryBundleRequest(
                targets=tuple(requested),
                dialect=dialect,  # type: ignore[arg-type]
                mp4_profile=mp4_profile,
                mp4_loudness_lufs=mp4_loudness_lufs,
                burn_subtitles=captions,
                audio_source=audio_source,
                look=look,
                mp4_draft=draft,
                mp4_fps=fps,
                mp4_preset=mp4_preset,
                compute_policy=compute_policy,
                allow_slow_cpu_fallback=allow_slow_cpu_fallback,
                mp4_mode=mode,
                mp4_draft_scale=draft_scale,
            ),
        )
        mp4 = (bundle.get("files") or {}).get("mp4") or {}
        path = Path(str(mp4.get("path") or ""))
        if mode == "preview" or qa_mode in {"off", "none", "skip"}:
            qa_mode = "off"
        if not draft and qa_mode != "off" and path.is_file():
            from videoflow.application.qa_final import audit_final

            if qa_mode == "fast":
                report = audit_final(
                    path,
                    output=Path(record.output),
                    state=state,
                    strict=True,
                    mode="fast",
                    fps=_fps_int(fps),
                    expected_frames=bundle.get("mp4_frames"),
                )
                bundle["qa_final"] = report
                bundle["ok"] = bool(bundle.get("ok")) and bool(report.get("ok"))
            elif qa_mode == "full":
                job = manager.start(
                    Path(record.primary_source or record.output),
                    Path(record.output),
                    {
                        "mode": "qa_full",
                        "project_id": record.project_id,
                        "video_path": str(path),
                        "fps": _fps_int(fps),
                        "expected_frames": bundle.get("mp4_frames"),
                    },
                    queue=True,
                    project_id=record.project_id,
                )
                bundle["qa_job"] = _job_payload(job)
            else:
                raise VideoFlowError(f"invalid qa_mode: {qa_mode}")
        return bundle

    @register
    def vf_export(
        action: str = "bundle",
        project_id: str = "",
        job_id: str = "",
        targets: str | list[str] | None = None,
        look: dict[str, Any] | None = None,
        audio_source: str = "mix",
        captions: bool = True,
        draft: bool = False,
        release_kit: bool = False,
        fps: int | str = 30,
        qa_mode: str = "fast",
        preset: str = "veryfast",
        kind: str = "timeline",
        crf: int = 20,
        width: int = 0,
        height: int = 0,
        draft_scale: float = 1.0,
        wait: bool = False,
        timeout_sec: float = 600.0,
        direction: str = "pull",
        nle: str = "fcpxml",
        path: str = "",
        apply: bool = False,
        dialect: str = "1.10",
        mp4_profile: str = "youtube_h264",
        mp4_loudness_lufs: float | None = -16.0,
        burn_subtitles: bool | None = None,
        compute_policy: str = "auto",
        allow_slow_cpu_fallback: bool = True,
        mode: Literal["final", "preview"] = "final",
    ) -> dict[str, Any]:
        """Render a bundle/mp4, start a draft render, validate exports, or run an NLE roundtrip.

        [ACTIONS] bundle, render, mp4, validate, roundtrip.
        """

        if burn_subtitles is not None:
            captions = burn_subtitles
        if action in {"render", "mp4"}:
            render_kind = "preview" if mode == "preview" and kind == "timeline" else kind
            response = legacy["vf_render_start"](
                project_id=project_id,
                kind=render_kind,
                crf=crf,
                preset=preset,
                width=width,
                height=height,
                draft_scale=draft_scale,
                qa_mode=qa_mode,
            )
            response["action"] = action
            if wait and response.get("ok"):
                new_job_id = str((response.get("job") or {}).get("job_id") or "")
                if new_job_id:
                    waited = _wait(manager, project_id, new_job_id, timeout_sec)
                    response["wait"] = waited
                    if isinstance(waited.get("job"), dict):
                        response["job"] = waited["job"]
            return response
        if action == "validate":
            from videoflow.application.delivery_bundle import (
                blocked_paths,
                timeline_frames,
            )
            from videoflow.application.nle_validation import validate_nle_exports
            from videoflow.domains.media import license_blockers

            try:
                record = get_project(project_id)
                state = load_project_state(record)
                exports_dir = (Path(record.output).expanduser() / "exports").resolve()
                report = validate_nle_exports(
                    exports_dir,
                    timeline_frames=(
                        timeline_frames(state) if state.video_segments else None
                    ),
                    blocked_paths=blocked_paths(
                        license_blockers(Path(record.output), state),
                        Path(record.output),
                    ),
                    check_media=True,
                )
            except VideoFlowError as exc:
                return exc.to_dict()
            return {
                "ok": bool(report.get("ok")),
                "directory": str(exports_dir),
                "report": report,
            }
        if action == "roundtrip":
            return legacy["vf_nle_roundtrip"](
                project_id=project_id,
                direction=direction,
                nle=nle,
                path=path,
                apply=apply,
            )
        if action != "bundle":
            return unknown_action(
                "vf_export",
                action,
                ("bundle", "render", "mp4", "validate", "roundtrip"),
            )
        if audio_source not in {"mix", "master", "timeline"}:
            return error("invalid_audio_source", "audio_source must be mix, master, or timeline")
        if qa_mode in {"none", "off", "skip"}:
            qa_mode = "off"
        if qa_mode not in {"fast", "full", "off"}:
            return error(
                "invalid_qa_mode",
                "qa_mode must be fast, full, off, none, or skip",
            )
        if mode not in {"final", "preview"}:
            return error("invalid_mode", "mode must be final or preview")
        started = time.monotonic()
        try:
            bundle = _run_bundle(
                project_id,
                targets=targets,
                look=look,
                audio_source=audio_source,
                captions=captions,
                draft=draft,
                dialect=dialect,
                mp4_profile=mp4_profile,
                mp4_loudness_lufs=mp4_loudness_lufs,
                fps=fps,
                qa_mode=qa_mode,
                mp4_preset=preset,
                compute_policy=compute_policy,
                allow_slow_cpu_fallback=allow_slow_cpu_fallback,
                mode=mode,
                draft_scale=draft_scale,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001 - MCP must return a typed error
            return error(
                "export_failed",
                str(exc) or exc.__class__.__name__,
                fix_hint="Inspect the job log and retry after fixing the export inputs.",
            )
        mp4 = (bundle.get("files") or {}).get("mp4") or {}
        response = {
            "ok": bool(bundle.get("ok")),
            "project_id": project_id,
            "targets": list(bundle.get("targets") or []),
            "mode": mode,
            "elapsed_sec": round(time.monotonic() - started, 3),
            "encoder": str(mp4.get("encoder") or ""),
            "degraded": bool(mp4.get("degraded")),
            "degraded_reason": str(mp4.get("degraded_reason") or ""),
            "bundle": bundle,
        }
        if release_kit:
            from videoflow.application.release_kit import build_release_kit

            try:
                response["release_kit"] = build_release_kit(project_id)
            except (VideoFlowError, OSError) as exc:
                response["release_kit_error"] = str(exc)
        return response
