"""Shared imports for the output route modules."""


# ruff: noqa: F401
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.api.errors import status_for
from videoflow.application.caption_ai import apply_llm_emoji
from videoflow.application.clock import now_iso
from videoflow.application.deliverables import (
    add_review_comment,
    approve_review,
    list_review_comments,
    list_thumbnails,
    record_thumbnail_metric,
    review_payload,
    select_thumbnail,
    thumbnail_metrics,
)
from videoflow.application.dubbing import generate_short_dubbing
from videoflow.application.intelligence import build_intelligence
from videoflow.application.jobs import Job, JobManager
from videoflow.application.live_source import live_sources
from videoflow.application.multimodal import analyze_short_entry
from videoflow.application.multimodal_llm import analyze_short_llm_entry
from videoflow.application.previews import (
    build_preview,
    preview_paths,
    previews,
    write_preview_manifest,
)
from videoflow.application.providers import first_provider
from videoflow.application.render_queue import renders
from videoflow.application.secrets import get_secret
from videoflow.application.settings import load_settings
from videoflow.application.short_editor import ShortEditOptions
from videoflow.application.short_editor import edit_short as edit_short_service
from videoflow.application.short_metadata import generate_short_metadata
from videoflow.application.state_cache import load_state
from videoflow.application.step_outputs import (
    load_step_outputs,
    save_step_outputs,
    step_output_port,
    summarize_step_outputs,
)
from videoflow.application.thumbnail import generate_short_thumbnail
from videoflow.application.voiceover import generate_short_voiceover
from videoflow.domain.config import DubbingConfig, TtsConfig
from videoflow.domain.errors import (
    CapabilityUnavailableError,
    RecipeError,
    StateNotReadyError,
    VideoFlowError,
)
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.state import ProjectState
from videoflow.domains.media.broll_approval import (
    load_approvals,
    redo_approval,
    save_approval,
    undo_approval,
)
from videoflow.runtime import allowed_roots
