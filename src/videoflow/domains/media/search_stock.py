"""Keyed Pexels and Pixabay searches."""

from __future__ import annotations

import re
from collections.abc import Iterable

import httpx

from videoflow.application.secrets import get_secret
from videoflow.application.settings import AppSettings
from videoflow.domain.errors import CapabilityUnavailableError, SearchError
from videoflow.domains.media.models import AssetCandidate, _candidate

from .search_base import _check_provider

_HTML = re.compile(r"<[^>]+>")


def _pexels(
    query: str,
    *,
    settings: AppSettings,
    limit: int,
    media: str,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
) -> list[AssetCandidate]:
    key = get_secret(settings.stock.pexels_key_env)
    if not key:
        raise CapabilityUnavailableError(
            "pexels", f"Missing API key secret {settings.stock.pexels_key_env}."
        )
    _check_provider(
        "https://api.pexels.com",
        allow_external_services=allow_external_services,
        allowed_external_hosts=allowed_external_hosts,
    )
    headers = {"Authorization": key}
    results: list[AssetCandidate] = []
    if media in {"all", "video"}:
        response = httpx.get(
            "https://api.pexels.com/videos/search",
            params={"query": query, "per_page": limit, "orientation": "landscape"},
            headers=headers,
            timeout=20,
        )
        if response.status_code >= 400:
            raise SearchError(f"Pexels video search returned HTTP {response.status_code}.")
        for video in response.json().get("videos", [])[:limit]:
            files = video.get("video_files") or []
            chosen = next(
                (
                    item
                    for item in files
                    if item.get("link")
                    and int(item.get("width") or 0) <= 1920
                ),
                files[0] if files else None,
            )
            if not chosen:
                continue
            user = video.get("user") or {}
            results.append(
                _candidate(
                    provider="pexels",
                    title=str(
                        video.get("url", "").rstrip("/").split("/")[-1]
                        or "Pexels video"
                    ),
                    page_url=str(video.get("url") or ""),
                    download_url=str(chosen.get("link") or ""),
                    query=query,
                    kind="video",
                    license_text="Pexels License",
                    license_url="https://www.pexels.com/license/",
                    creator=str(user.get("name") or ""),
                    duration_sec=float(video.get("duration") or 0),
                    width=int(chosen.get("width") or 0),
                    height=int(chosen.get("height") or 0),
                )
            )
    if media in {"all", "image"} and len(results) < limit:
        response = httpx.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": limit},
            headers=headers,
            timeout=20,
        )
        if response.status_code < 400:
            for photo in response.json().get("photos", [])[:limit]:
                src = photo.get("src") or {}
                results.append(
                    _candidate(
                        provider="pexels",
                        title=str(photo.get("alt") or "Pexels photo"),
                        page_url=str(photo.get("url") or ""),
                        download_url=str(
                            src.get("large2x") or src.get("original") or ""
                        ),
                        query=query,
                        kind="image",
                        license_text="Pexels License",
                        license_url="https://www.pexels.com/license/",
                        creator=str(photo.get("photographer") or ""),
                        width=int(photo.get("width") or 0),
                        height=int(photo.get("height") or 0),
                    )
                )
    return results[:limit]


def _pixabay(
    query: str,
    *,
    settings: AppSettings,
    limit: int,
    media: str,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
) -> list[AssetCandidate]:
    key = get_secret(settings.stock.pixabay_key_env)
    if not key:
        raise CapabilityUnavailableError(
            "pixabay", f"Missing API key secret {settings.stock.pixabay_key_env}."
        )
    _check_provider(
        "https://pixabay.com",
        allow_external_services=allow_external_services,
        allowed_external_hosts=allowed_external_hosts,
    )
    results: list[AssetCandidate] = []
    if media in {"all", "video"}:
        response = httpx.get(
            "https://pixabay.com/api/videos/",
            params={"key": key, "q": query, "per_page": limit, "safesearch": "true"},
            timeout=20,
        )
        if response.status_code < 400:
            for hit in response.json().get("hits", [])[:limit]:
                videos = hit.get("videos") or {}
                chosen = videos.get("medium") or videos.get("small") or {}
                results.append(
                    _candidate(
                        provider="pixabay",
                        title=str(hit.get("tags") or "Pixabay video"),
                        page_url=str(hit.get("pageURL") or ""),
                        download_url=str(chosen.get("url") or ""),
                        query=query,
                        kind="video",
                        license_text="Pixabay Content License",
                        license_url="https://pixabay.com/service/license-summary/",
                        creator=str(hit.get("user") or ""),
                        duration_sec=float(hit.get("duration") or 0),
                        width=int(chosen.get("width") or 0),
                        height=int(chosen.get("height") or 0),
                    )
                )
    if media in {"all", "image"} and len(results) < limit:
        response = httpx.get(
            "https://pixabay.com/api/",
            params={
                "key": key,
                "q": query,
                "per_page": limit,
                "image_type": "photo",
                "safesearch": "true",
            },
            timeout=20,
        )
        if response.status_code < 400:
            for hit in response.json().get("hits", [])[:limit]:
                results.append(
                    _candidate(
                        provider="pixabay",
                        title=str(hit.get("tags") or "Pixabay photo"),
                        page_url=str(hit.get("pageURL") or ""),
                        download_url=str(
                            hit.get("largeImageURL") or hit.get("webformatURL") or ""
                        ),
                        query=query,
                        kind="image",
                        license_text="Pixabay Content License",
                        license_url="https://pixabay.com/service/license-summary/",
                        creator=str(hit.get("user") or ""),
                        width=int(hit.get("imageWidth") or 0),
                        height=int(hit.get("imageHeight") or 0),
                    )
                )
    return results[:limit]


