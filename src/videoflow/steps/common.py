"""Shared helpers for recipe steps."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError


def adapter_for(context: PipelineContext, io: Any) -> Any:
    if io.adapter is not None:
        return io.adapter
    return FFmpegAdapter(log=lambda level, message: io.emit(level, message, module="ffmpeg"))


def require_media(context: PipelineContext) -> Any:
    if context.media is None:
        raise IngestError("The ingest step must run before this step")
    return context.media


def digest_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
