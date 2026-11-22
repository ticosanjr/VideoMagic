"""Public fetch entry points for the unified media domain."""

from __future__ import annotations

from typing import Any

from .fetch_service import FetchService


def fetch_stock_broll(
    project_id: str,
    query: str,
    orientation: str = "landscape",
    min_duration: int = 4,
    max_results: int = 5,
    provider: str = "auto",
) -> dict[str, Any]:
    """Fetch stock B-roll video into the project workspace."""

    with FetchService() as service:
        return service.fetch_stock_broll(
            project_id,
            query,
            orientation,
            min_duration,
            max_results,
            provider,
        )


def fetch_stock_images(
    project_id: str,
    query: str,
    count: int = 5,
    keyless: bool = True,
    provider: str = "auto",
) -> dict[str, Any]:
    """Fetch stock images into the project workspace."""

    with FetchService() as service:
        return service.fetch_stock_images(project_id, query, count, keyless, provider)


def rip_video_segment(
    project_id: str,
    url: str,
    start_time: float,
    end_time: float,
    audio_only: bool = False,
    max_height: int = 1080,
) -> dict[str, Any]:
    """Download a bounded external video/audio segment."""

    with FetchService() as service:
        return service.rip_video_segment(
            project_id,
            url,
            start_time,
            end_time,
            audio_only,
            max_height,
        )


def fetch_sfx(
    project_id: str,
    query: str,
    max_duration: float = 5.0,
    license_filter: str = "cc0",
    provider: str = "auto",
) -> dict[str, Any]:
    """Fetch a sound effect into the project workspace."""

    with FetchService() as service:
        return service.fetch_sfx(
            project_id,
            query,
            max_duration,
            license_filter,
            provider,
        )


__all__ = [
    "FetchService",
    "fetch_sfx",
    "fetch_stock_broll",
    "fetch_stock_images",
    "rip_video_segment",
]
