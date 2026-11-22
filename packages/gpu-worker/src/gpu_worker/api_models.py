"""Request bodies for worker upload and job routes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UploadInit(BaseModel):
    """Request body for a resumable upload."""

    filename: str = "upload.bin"
    size: int = Field(ge=0)
    sha256: str = ""
    chunk_size: int = Field(default=8 * 1024 * 1024, ge=1, le=64 * 1024 * 1024)


class JobSubmission(BaseModel):
    """Request body for ``POST /jobs/{capability}``."""

    params: dict[str, Any] = Field(default_factory=dict)
    inputs: list[str] = Field(default_factory=list)
    shared: bool = False
    shared_inputs: list[str] = Field(default_factory=list)
    shared_outputs: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=-100, le=100)
