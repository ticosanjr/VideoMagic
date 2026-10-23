"""Feature and provider discovery for the UI, REST API, and MCP.

The manifest is intentionally data-only. A capability that depends on an
external service is reported as blocked unless the caller explicitly allows it
and the operator has not set the global kill switch.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from urllib.parse import urlparse

from videoflow.domain.errors import CapabilityUnavailableError

_LOCAL_HOSTS = {
    "0.0.0.0",
    "127.0.0.1",
    "::1",
    "host.docker.internal",
    "localhost",
}


def external_services_allowed(requested: bool) -> bool:
    """Return whether external providers may be used for this call."""

    if os.environ.get("VIDEOWFLOW_ALLOW_EXTERNAL", "1") == "0":
        return False
    return bool(requested)


def ensure_external_allowed(
    url: str | None,
    *,
    capability: str,
    allow_external_services: bool,
    allowed_hosts: Sequence[str] = (),
) -> None:
    """Reject a non-local provider URL when external access is not allowed."""

    if not url:
        return
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if host in _LOCAL_HOSTS:
        return
    if not external_services_allowed(allow_external_services):
        raise CapabilityUnavailableError(
            capability,
            "External services are blocked. Enable 'allow_external_services' "
            "for this run or unset VIDEOWFLOW_ALLOW_EXTERNAL=0.",
        )
    allowed = {item.casefold() for item in allowed_hosts if item.strip()}
    if allowed and host not in allowed:
        raise CapabilityUnavailableError(
            capability,
            f"Host '{host}' is not in allowed_external_hosts.",
        )


def capability_manifest(*, allow_external_services: bool = False) -> list[dict[str, object]]:
    """Return the current capability surface with availability and provenance."""

    external = external_services_allowed(allow_external_services)
    return [
        _entry(
            "local_files",
            "Local media",
            "ingest",
            "available",
            "Probe, extract PCM, and keep media inside the path allowlist.",
            "GET /api/v1/media/probe",
            "videoflow_load_media",
        ),
        _entry(
            "recipe_engine",
            "Recipe engine",
            "automation",
            "available",
            "Versioned DAG recipes with typed steps, validation, caching hashes, "
            "CLI, REST, and MCP execution.",
            "POST /api/v1/recipes/run",
            "videoflow_run_recipe",
        ),
        _entry(
            "timeline_editing",
            "Timeline editing",
            "editing",
            "available",
            "Canvas timeline with drag, trim, split, ripple delete, undo, redo, "
            "and JSON project-state revisions.",
            "PATCH /api/v1/jobs/{job_id}/timeline",
            "videoflow_edit_timeline",
        ),
        _entry(
            "timeline_preview",
            "Timeline preview",
            "editing",
            "available",
            "Browser preview MP4 plus waveforms synced to the playhead.",
            "POST /api/v1/jobs/{job_id}/preview",
            "videoflow_create_preview",
        ),
        _entry(
            "broll_approval",
            "B-roll approval",
            "curation",
            "available",
            "Approve, reject, and reorder planned B-roll before Short rendering.",
            "PATCH /api/v1/jobs/{job_id}/broll",
            "videoflow_approve_broll",
        ),
        _entry(
            "providers",
            "Provider configuration",
            "providers",
            "available",
            "Persisted providers.json with defaults and fallback chains per capability.",
            "GET /api/v1/providers",
            "videoflow_list_providers",
        ),
        _entry(
            "audio_master",
            "Audio master",
            "audio",
            "available",
            "High-pass, FFT denoise, and EBU R128 loudness render to master.wav.",
            "POST /api/v1/recipes/run",
            "videoflow_run_recipe",
            requires=["ffmpeg"],
        ),
        _entry(
            "titles",
            "Titles and lower thirds",
            "editing",
            "available",
            "Deterministic title-card and speaker lower-third plan.",
            "POST /api/v1/recipes/run",
            "videoflow_run_recipe",
        ),
        _entry(
            "analytics_import",
            "Analytics import",
            "curation",
            "available",
            "Normalize retention/CTR CSV rows into analytics.json.",
            "POST /api/v1/recipes/run",
            "videoflow_run_recipe",
        ),
        _entry(
            "review",
            "Review checklist",
            "curation",
            "available",
            "Deterministic pre-publish review checks for each run.",
            "POST /api/v1/recipes/run",
            "videoflow_run_recipe",
        ),
        _entry(
            "url_import",
            "URL import",
            "ingest",
            "available",
            "Download public http(s) links through yt-dlp.",
            "POST /api/v1/media/import",
            "videoflow_import_url",
            requires=["yt-dlp", "network access"],
        ),
        _entry(
            "local_transcription",
            "Local transcription",
            "speech",
            "available",
            "Faster-Whisper or whisper.cpp on the local machine.",
            "POST /api/v1/jobs",
            "videoflow_transcribe",
        ),
        _entry(
            "silero_vad",
            "Silero VAD",
            "speech",
            "available",
            "Local speech detection with an FFmpeg fallback.",
            "POST /api/v1/jobs",
            "videoflow_run_vad",
        ),
        _entry(
            "nle_exports",
            "NLE exports",
            "export",
            "available",
            "FCPXML, xmeml, and native Kdenlive MLT from one timeline.",
            "POST /api/v1/recipes/run",
            "videoflow_export_fcpxml",
        ),
        _entry(
            "direct_mp4",
            "Direct MP4 render",
            "export",
            "available",
            "Render the validated main timeline to H.264/AAC with FFmpeg.",
            "POST /api/v1/jobs",
            "videoflow_export_fcpxml",
            requires=["ffmpeg with libx264"],
        ),
        _entry(
            "clip_transitions",
            "Clip transitions",
            "editing",
            "partial",
            "Crossfade and fade-to-black transitions in FCPXML, XMEML, and MP4; "
            "Kdenlive parity is pending.",
            "POST /api/v1/recipes/run",
            "videoflow_run_recipe",
        ),
        _entry(
            "speaker_turns",
            "Speaker turns",
            "captions",
            "partial",
            "Heuristic pause-based speaker ids and speaker-colored ASS captions.",
            "POST /api/v1/recipes/run",
            "videoflow_run_recipe",
        ),
        _entry(
            "broll",
            "Local B-roll",
            "editing",
            "partial",
            "Local asset matching plus full-frame B-roll overlays in rendered Shorts.",
            "POST /api/v1/recipes/run",
            "videoflow_run_recipe",
            requires=["local B-roll asset directory"],
        ),
        _entry(
            "split_screen",
            "Split-screen Shorts",
            "shorts",
            "available",
            "Two-panel split-screen rendering for Shorts.",
            "POST /api/v1/recipes/run",
            "videoflow_run_recipe",
        ),
        _entry(
            "local_tts",
            "Local TTS",
            "audio",
            "partial",
            "Piper CLI voice-over synthesis when a binary and voice model are installed.",
            "POST /api/v1/jobs/{job_id}/shorts/{index}/voiceover",
            "videoflow_generate_short_voiceover",
            requires=["piper", "voice model"],
        ),
        _entry(
            "folder_batch",
            "Folder batch",
            "automation",
            "available",
            "Run one recipe over a folder, one file at a time, with per-item jobs.",
            "POST /api/v1/batches",
            "videoflow_run_batch",
        ),
        _entry(
            "shorts_aspects",
            "Short aspect ratios",
            "shorts",
            "available",
            "Render 9:16, 1:1, or 16:9 vertical/social clips.",
            "POST /api/v1/jobs",
            "videoflow_generate_shorts",
            requires=["ffmpeg"],
        ),
        _entry(
            "shorts_timeframe",
            "Short source window",
            "shorts",
            "available",
            "Limit Short selection to a start/end range of the source.",
            "POST /api/v1/jobs",
            "videoflow_generate_shorts",
        ),
        _entry(
            "intro_outro",
            "Intro/outro cards",
            "shorts",
            "available",
            "PNG/JPEG intro and outro cards with configurable durations.",
            "POST /api/v1/jobs",
            "videoflow_run_pipeline",
        ),
        _entry(
            "vision_llm",
            "LLM vision analysis",
            "editing",
            "partial",
            "Frame sampling plus OpenAI-compatible multimodal chat analysis.",
            "POST /api/v1/jobs/{job_id}/shorts/{index}/analyze/llm",
            "videoflow_analyze_short_llm",
            requires=["vision-capable OpenAI-compatible model", "network access"],
        ),
        _entry(
            "multimodal_analysis",
            "Multimodal analysis",
            "editing",
            "partial",
            "Audio-emotion heuristics and motion/optional face analysis for a Short.",
            "POST /api/v1/jobs/{job_id}/shorts/{index}/analyze",
            "videoflow_analyze_short",
            requires=["optional opencv-python-headless for faces"],
        ),
        _entry(
            "publish_webhook",
            "Webhook publishing",
            "export",
            "available",
            "Schedule generated Short metadata/assets to a configured webhook.",
            "POST /api/v1/jobs/{job_id}/shorts/{index}/publish",
            "videoflow_schedule_short",
            requires=["webhook URL", "network access"],
        ),
        _entry(
            "voiceover",
            "Voice-over",
            "audio",
            "partial",
            "External OpenAI-compatible TTS mixed over a Short.",
            "POST /api/v1/jobs/{job_id}/shorts/{index}/voiceover",
            "videoflow_generate_short_voiceover",
            requires=["external TTS provider", "network access"],
        ),
        _entry(
            "music_bed",
            "Background music",
            "shorts",
            "available",
            "Looping music bed with volume, fades, and optional speech ducking.",
            "POST /api/v1/assets/music",
            "videoflow_upload_music",
        ),
        _entry(
            "watermark",
            "Watermark overlay",
            "shorts",
            "available",
            "PNG/JPEG overlay with position, margin, width ratio, and opacity.",
            "POST /api/v1/assets/images",
            "videoflow_upload_image",
        ),
        _entry(
            "speech_enhancement",
            "Speech enhancement",
            "audio",
            "partial",
            "FFmpeg high-pass, FFT denoise, and loudness normalization for "
            "rendered Shorts. NLE source audio is unchanged.",
            "POST /api/v1/jobs",
            "videoflow_run_pipeline",
        ),
        _entry(
            "custom_fonts",
            "Custom fonts",
            "shorts",
            "available",
            "Upload TTF/OTF files and use their internal family names in ASS.",
            "POST /api/v1/assets/fonts",
            "videoflow_upload_font",
        ),
        _entry(
            "scene_changes",
            "Scene-change analysis",
            "editing",
            "available",
            "FFmpeg scene scores that boost Shorts around visual cuts.",
            "POST /api/v1/jobs",
            "videoflow_run_pipeline",
        ),
        _entry(
            "motion_tracking",
            "Motion tracking",
            "editing",
            "available",
            "Low-resolution frame-difference focus estimation for Short reframing.",
            "POST /api/v1/jobs",
            "videoflow_run_pipeline",
        ),
        _entry(
            "face_tracking",
            "Face tracking",
            "editing",
            "partial",
            "Optional OpenCV Haar face detection; falls back to motion tracking.",
            "POST /api/v1/jobs",
            "videoflow_run_pipeline",
            requires=["opencv-python-headless"],
        ),
        _entry(
            "project_templates",
            "Project templates",
            "configuration",
            "available",
            "Reusable flat job configuration templates.",
            "GET /api/v1/project-templates",
            "videoflow_list_project_templates",
        ),
        _entry(
            "config_io",
            "Configuration import/export",
            "configuration",
            "available",
            "Versioned JSON envelopes with non-secret run options.",
            "POST /api/v1/config/export",
            "videoflow_export_config",
        ),
        _entry(
            "brand_templates",
            "Brand templates",
            "branding",
            "available",
            "Reusable caption, overlay, music, and intro/outro bundles.",
            "GET /api/v1/brand-templates",
            "videoflow_list_brand_templates",
        ),
        _entry(
            "caption_branding",
            "Caption branding",
            "shorts",
            "available",
            "Keyword highlighting, contextual emoji, and brand vocabulary.",
            "POST /api/v1/jobs",
            "videoflow_run_pipeline",
        ),
        _entry(
            "caption_preview",
            "Caption preview",
            "shorts",
            "partial",
            "Approximate 9:16 HTML preview of the ASS caption style.",
            "UI only",
            "not exposed",
        ),
        _external_entry(
            "external_llm",
            "External LLM",
            "providers",
            external,
            "OpenAI-compatible service for retakes, Shorts, and future curation.",
            "POST /api/v1/jobs",
            "videoflow_run_pipeline",
        ),
        _external_entry(
            "external_asr",
            "External ASR",
            "providers",
            external,
            "OpenAI-compatible transcription endpoint.",
            "POST /api/v1/jobs",
            "videoflow_run_pipeline",
        ),
        _entry(
            "shorts_editor",
            "Per-Short editor",
            "shorts",
            "available",
            "Trim, retitle, reframe, and re-render one selected Short.",
            "POST /api/v1/jobs/{job_id}/shorts/{index}/edit",
            "videoflow_edit_short",
        ),
        _entry(
            "prompt_to_clip",
            "Prompt-to-clip",
            "curation",
            "available",
            "Focus Short selection with an explicit topic or instruction.",
            "POST /api/v1/jobs",
            "videoflow_generate_shorts",
        ),
        _entry(
            "reprompt",
            "Reprompt clipping",
            "curation",
            "available",
            "Refine a previous Short selection with a new instruction.",
            "POST /api/v1/jobs",
            "videoflow_generate_shorts",
            requires=["shorts.json from the previous run"],
        ),
        _entry(
            "auto_hook",
            "Auto hook",
            "curation",
            "available",
            "Mark or move the highest-scoring sentence to the first seconds.",
            "POST /api/v1/jobs",
            "videoflow_generate_shorts",
        ),
        _entry(
            "thumbnails",
            "Thumbnail generator",
            "export",
            "available",
            "Extract one Short frame and burn a caption-style title.",
            "POST /api/v1/jobs/{job_id}/shorts/{index}/thumbnail",
            "videoflow_generate_short_thumbnail",
        ),
        _entry(
            "metadata",
            "Social metadata",
            "export",
            "available",
            "Deterministic title, description, and hashtags per platform.",
            "POST /api/v1/jobs/{job_id}/shorts/{index}/metadata",
            "videoflow_generate_short_metadata",
        ),
        _entry(
            "virality_score",
            "Virality score",
            "curation",
            "partial",
            "Explainable heuristic score. Not a platform-trained predictor.",
            "POST /api/v1/jobs",
            "videoflow_generate_shorts",
        ),
        _entry(
            "visual_tracking",
            "Visual tracking",
            "editing",
            "planned",
            "Face/person tracking for reframing and layouts.",
            "planned",
            "planned",
            requires=["optional vision model"],
        ),
        _entry(
            "dubbing",
            "Dubbing",
            "audio",
            "available",
            "Translation plus external TTS dubbing over a Short.",
            "POST /api/v1/jobs/{job_id}/shorts/{index}/dub",
            "videoflow_dub_short",
            requires=["external LLM", "external TTS"],
        ),
    ]


def _entry(
    capability_id: str,
    name: str,
    category: str,
    status: str,
    description: str,
    api: str,
    mcp: str,
    *,
    requires: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": capability_id,
        "name": name,
        "category": category,
        "status": status,
        "description": description,
        "api": api,
        "mcp": mcp,
        "requires": requires or [],
    }


def _external_entry(
    capability_id: str,
    name: str,
    category: str,
    allowed: bool,
    description: str,
    api: str,
    mcp: str,
) -> dict[str, object]:
    entry = _entry(
        capability_id,
        name,
        category,
        "available" if allowed else "blocked",
        description,
        api,
        mcp,
        requires=["network access", "provider configuration"],
    )
    if not allowed:
        entry["reason"] = (
            "External services are disabled. Enable allow_external_services or "
            "unset VIDEOWFLOW_ALLOW_EXTERNAL=0."
        )
    return entry
