"""HTTP status mapping for typed VideoFlow failures.

Keeping the mapping outside the route module lets the app install one
exception handler instead of repeating ``try/except VideoFlowError`` in every
route. Codes not listed here are client errors (400) by default.
"""

from __future__ import annotations

STATUS_BY_CODE: dict[str, int] = {
    "videoflow_error": 400,
    "path_not_allowed": 403,
    "path_not_found": 404,
    "not_a_directory": 422,
    "directory_exists": 409,
    "invalid_directory_name": 422,
    "permission_denied": 403,
    "filesystem_error": 500,
    "asset_not_found": 404,
    "job_queue_full": 429,
    "job_not_found": 404,
    "job_already_running": 409,
    "job_cancelled": 409,
    "approval_required": 409,
    "human_input_required": 409,
    "hilt_response_invalid": 409,
    "hilt_attachment_invalid": 422,
    "hilt_expired": 410,
    "search_failed": 502,
    "search_blocked": 403,
    "upstream_dirty": 409,
    "project_not_found": 404,
    "project_exists": 409,
    "project_state_invalid": 500,
    "schema_too_new": 409,
    "preset_not_found": 404,
    "preset_invalid": 422,
    "invalid_preset_name": 422,
    "unknown_module": 404,
    "module_bypassed": 409,
    "media_not_found": 422,
    "media_not_registered": 409,
    "state_not_ready": 409,
    "short_edit_failed": 422,
    "tts_failed": 502,
    "llm_failed": 502,
    "llm_timeout": 502,
    "transcription_failed": 502,
    "transcript_not_found": 404,
    "transcript_required": 422,
    "invalid_transcript": 422,
    "invalid_retake_ids": 422,
    "invalid_override": 422,
    "word_overrides_not_supported": 422,
    "invalid_time": 422,
    "invalid_config": 422,
    "recipe_invalid": 422,
    "step_failed": 422,
    "batch_invalid": 422,
    "export_failed": 422,
    "ingest_failed": 422,
    "render_failed": 500,
    "waveform_failed": 422,
    "overlay_failed": 422,
    "backup_failed": 500,
    "plugin_not_found": 404,
    "external_service_blocked": 403,
    "precondition_failed": 412,
    "gpu_worker_offline": 503,
    "gpu_required_for_operation": 503,
    "alpha_channel_missing": 422,
    "insufficient_contiguous_speech": 422,
    "beatmap_conflict": 409,
    "insufficient_disk_space": 507,
    "capability_unavailable": 501,
    "not_implemented": 501,
}


def status_for(code: str) -> int:
    """Return the HTTP status for a typed failure code."""

    return STATUS_BY_CODE.get(code, 400)
