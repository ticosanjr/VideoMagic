"""Filesystem browsing and media ingestion routes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.api.errors import status_for
from videoflow.application.filesystem import create_directory, list_directory, roots_payload
from videoflow.application.url_import import import_url
from videoflow.domain.errors import (
    FilesystemError,
    MediaNotFoundError,
    VideoFlowError,
)
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.state import MediaInfo
from videoflow.runtime import allowed_roots

logger = logging.getLogger(__name__)


class MediaImportRequest(BaseModel):
    url: str = Field(min_length=1)
    max_height: int = Field(default=1080, ge=144, le=4320)
    allow_playlist: bool = False
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class NewDirectoryRequest(BaseModel):
    parent: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)


def probe_media(path: Path) -> MediaInfo:
    return FFmpegAdapter().probe(path)


def register_media_routes(app: FastAPI) -> None:
    """Register filesystem browsing, directory creation, and media routes."""

    def fail(exc: VideoFlowError) -> None:
        raise HTTPException(status_code=status_for(exc.code), detail=exc.to_dict()) from exc

    @app.get("/api/v1/fs/roots")
    def fs_roots() -> dict[str, object]:
        return {"ok": True, "roots": roots_payload()}

    @app.get("/api/v1/fs/list")
    def fs_list(
        path: str | None = None,
        mode: Literal["file", "directory"] = "file",
        extensions: str | None = None,
        q: str = "",
        show_hidden: bool = False,
        limit: int = 500,
    ) -> dict[str, object]:
        try:
            suffixes = tuple(
                item.strip() for item in (extensions or "").split(",") if item.strip()
            )
            return {
                "ok": True,
                **list_directory(
                    path,
                    mode=mode,
                    extensions=suffixes,
                    query=q,
                    show_hidden=show_hidden,
                    limit=limit,
                ),
            }
        except VideoFlowError as exc:
            fail(exc)
        except (OSError, ValueError, OverflowError) as exc:
            fail(FilesystemError(f"Could not list this folder: {exc}"))
        except Exception as exc:  # pragma: no cover - defensive local UI boundary
            logger.exception("unhandled filesystem listing error")
            raise HTTPException(
                status_code=500,
                detail={
                    "ok": False,
                    "code": "filesystem_error",
                    "message": f"Could not list this folder: {exc}",
                },
            ) from exc

    @app.post("/api/v1/fs/mkdir", status_code=201)
    def fs_mkdir(request: NewDirectoryRequest) -> dict[str, object]:
        created = create_directory(request.parent, request.name)
        return {"ok": True, "entry": created}

    @app.get("/api/v1/media/probe")
    def media_probe(path: str) -> dict[str, object]:
        source = resolve_allowed(Path(path).expanduser(), allowed_roots())
        if not source.is_file():
            raise MediaNotFoundError(str(source))
        try:
            size = source.stat().st_size
        except OSError as exc:
            raise FilesystemError(f"Could not inspect {source}: {exc}") from exc
        media = probe_media(source)
        return {
            "ok": True,
            "path": str(source),
            "name": source.name,
            "size_bytes": size,
            "media": media.model_dump(mode="json"),
        }

    @app.post("/api/v1/media/import", status_code=201)
    def import_media(request: MediaImportRequest) -> dict[str, object]:
        path = import_url(
            request.url,
            max_height=request.max_height,
            allow_playlist=request.allow_playlist,
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
        )
        media = FFmpegAdapter().probe(path)
        return {"ok": True, "path": str(path), "media": media.model_dump(mode="json")}
