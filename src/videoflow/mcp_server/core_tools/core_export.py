"""VideoFlow core MCP tools: export and delivery bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.agent_helpers import _job_payload
from videoflow.mcp_server.context import error

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
        mp4_loudness_lufs: float | None = -16.5,
        fps: int | str = 30,
        qa_mode: str = "fast",
        mp4_preset: str = "veryfast",
        compute_policy: str = "auto",
        allow_slow_cpu_fallback: bool = True,
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
            ),
        )
        mp4 = (bundle.get("files") or {}).get("mp4") or {}
        path = Path(str(mp4.get("path") or ""))
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
        timeout_sec: float = 1800.0,
        direction: str = "pull",
        nle: str = "fcpxml",
        path: str = "",
        apply: bool = False,
        dialect: str = "1.10",
        mp4_profile: str = "youtube_h264",
        mp4_loudness_lufs: float | None = -16.5,
        burn_subtitles: bool | None = None,
        compute_policy: str = "auto",
        allow_slow_cpu_fallback: bool = True,
    ) -> dict[str, Any]:
        """Render a bundle, start a draft render, validate exports, or run an NLE roundtrip."""

        if burn_subtitles is not None:
            captions = burn_subtitles
        if action == "render":
            response = legacy["vf_render_start"](
                project_id=project_id,
                kind=kind,
                crf=crf,
                preset=preset,
                width=width,
                height=height,
                draft_scale=draft_scale,
            )
            if wait and response.get("ok"):
                new_job_id = str((response.get("job") or {}).get("job_id") or "")
                if new_job_id:
                    response["wait"] = _wait(manager, project_id, new_job_id, timeout_sec)
            return response
        if action == "validate":
            return legacy["vf_validate_exports"](project_id=project_id, job_id=job_id)
        if action == "roundtrip":
            return legacy["vf_nle_roundtrip"](
                project_id=project_id,
                direction=direction,
                nle=nle,
                path=path,
                apply=apply,
            )
        if action != "bundle":
            return error(
                "unknown_action",
                "vf_export supports bundle, render, validate, or roundtrip",
            )
        if audio_source not in {"mix", "master", "timeline"}:
            return error("invalid_audio_source", "audio_source must be mix, master, or timeline")
        if qa_mode not in {"fast", "full", "off"}:
            return error("invalid_qa_mode", "qa_mode must be fast, full, or off")
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
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001 - MCP must return a typed error
            return error(
                "export_failed",
                str(exc) or exc.__class__.__name__,
                fix_hint="Inspect the job log and retry after fixing the export inputs.",
            )
        response = {
            "ok": bool(bundle.get("ok")),
            "project_id": project_id,
            "targets": list(bundle.get("targets") or []),
            "bundle": bundle,
        }
        if release_kit:
            from videoflow.application.release_kit import build_release_kit

            try:
                response["release_kit"] = build_release_kit(project_id)
            except (VideoFlowError, OSError) as exc:
                response["release_kit_error"] = str(exc)
        return response
