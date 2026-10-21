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
            "POST /api/v1/projects/{project_id}/exports",
            "videoflow_export_fcpxml",
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
            "planned",
            "Optional external or local voice-preserving dubbing.",
            "planned",
            "planned",
            requires=["external provider or local model"],
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
