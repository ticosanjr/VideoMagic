"""Pexels and Pixabay keyed providers."""

# ruff: noqa: F405

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..errors import (
    ProviderUnavailableError,
)
from .base import *  # noqa: F401,F403,F405
from .base import _suffix_for


class PexelsClient(HttpClient):
    """Pexels video and photo search."""

    provider_name = "pexels"

    def __init__(self, api_key: str, **kwargs: Any) -> None:
        if not api_key:
            raise ProviderUnavailableError("PEXELS_API_KEY is not set.")
        super().__init__(**kwargs)
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.api_key}

    def search_videos(
        self,
        query: str,
        *,
        orientation: str = "landscape",
        min_duration: int = 4,
        max_results: int = 5,
    ) -> list[RemoteAsset]:
        payload = self.get_json(
            f"{PEXELS_API}/videos/search",
            params={
                "query": query,
                "orientation": orientation,
                "per_page": max(3, min(max_results * 3, 80)),
            },
            headers=self._headers(),
        )
        results: list[RemoteAsset] = []
        for video in payload.get("videos", []):
            if not isinstance(video, dict):
                continue
            duration = int(video.get("duration") or 0)
            if duration < min_duration:
                continue
            file_info = _pick_pexels_video_file(video.get("video_files") or [])
            if file_info is None:
                continue
            creator = str((video.get("user") or {}).get("name") or "Pexels contributor")
            suffix = _suffix_for(file_info["link"], ".mp4")
            results.append(
                RemoteAsset(
                    provider="pexels",
                    media_type="video",
                    download_url=str(file_info["link"]),
                    page_url=str(video.get("url") or ""),
                    creator=creator,
                    license_name=PEXELS_LICENSE,
                    license_url=PEXELS_LICENSE_URL,
                    status="cleared",
                    attribution_required=False,
                    license={
                        "attribution": f"Video by {creator} on Pexels",
                        "license_id": "pexels",
                    },
                    metadata={
                        "id": video.get("id"),
                        "duration": duration,
                        "width": file_info.get("width"),
                        "height": file_info.get("height"),
                        "fps": video.get("fps"),
                        "quality": file_info.get("quality"),
                        "creator": creator,
                    },
                    suggested_filename=f"pexels-{video.get('id', 'video')}{suffix}",
                )
            )
            if len(results) >= max_results:
                break
        return results

    def search_images(
        self,
        query: str,
        *,
        count: int = 5,
        orientation: str = "landscape",
    ) -> list[RemoteAsset]:
        payload = self.get_json(
            f"{PEXELS_API}/v1/search",
            params={
                "query": query,
                "orientation": orientation,
                "per_page": max(1, min(count, 80)),
            },
            headers=self._headers(),
        )
        results: list[RemoteAsset] = []
        for photo in payload.get("photos", []):
            if not isinstance(photo, dict):
                continue
            sources = photo.get("src") or {}
            link = sources.get("large2x") or sources.get("original") or sources.get("large")
            if not link:
                continue
            creator = str(photo.get("photographer") or "Pexels contributor")
            suffix = _suffix_for(str(link), ".jpg")
            results.append(
                RemoteAsset(
                    provider="pexels",
                    media_type="image",
                    download_url=str(link),
                    page_url=str(photo.get("url") or ""),
                    creator=creator,
                    license_name=PEXELS_LICENSE,
                    license_url=PEXELS_LICENSE_URL,
                    status="cleared",
                    attribution_required=False,
                    license={
                        "attribution": f"Photo by {creator} on Pexels",
                        "license_id": "pexels",
                    },
                    metadata={
                        "id": photo.get("id"),
                        "width": photo.get("width"),
                        "height": photo.get("height"),
                        "creator": creator,
                    },
                    suggested_filename=f"pexels-{photo.get('id', 'photo')}{suffix}",
                )
            )
            if len(results) >= count:
                break
        return results


def _pick_pexels_video_file(files: Sequence[Any]) -> dict[str, Any] | None:
    usable = [item for item in files if isinstance(item, dict) and item.get("link")]
    if not usable:
        return None
    preferred = [item for item in usable if int(item.get("width") or 0) <= 1920]
    pool = preferred or usable
    return max(
        pool,
        key=lambda item: (
            int(item.get("width") or 0),
            str(item.get("quality") or "") == "hd",
        ),
    )


class PixabayClient(HttpClient):
    """Pixabay video and image search."""

    provider_name = "pixabay"

    def __init__(self, api_key: str, **kwargs: Any) -> None:
        if not api_key:
            raise ProviderUnavailableError("PIXABAY_API_KEY is not set.")
        super().__init__(**kwargs)
        self.api_key = api_key

    def search_videos(
        self,
        query: str,
        *,
        orientation: str = "landscape",
        min_duration: int = 4,
        max_results: int = 5,
    ) -> list[RemoteAsset]:
        payload = self.get_json(
            f"{PIXABAY_API}/videos/",
            params={
                "key": self.api_key,
                "q": query,
                "video_type": "film",
                "safesearch": "true",
                "per_page": max(3, min(max_results * 3, 100)),
            },
        )
        results: list[RemoteAsset] = []
        for hit in payload.get("hits", []):
            if not isinstance(hit, dict):
                continue
            duration = int(hit.get("duration") or 0)
            if duration < min_duration:
                continue
            width = int(hit.get("width") or 0)
            height = int(hit.get("height") or 0)
            if orientation == "landscape" and width < height:
                continue
            if orientation == "portrait" and width > height:
                continue
            variants = hit.get("videos") or {}
            variant = _pick_pixabay_video(variants)
            if variant is None:
                continue
            creator = str(hit.get("user") or "Pixabay contributor")
            suffix = _suffix_for(str(variant["url"]), ".mp4")
            results.append(
                RemoteAsset(
                    provider="pixabay",
                    media_type="video",
                    download_url=str(variant["url"]),
                    page_url=str(hit.get("pageURL") or ""),
                    creator=creator,
                    license_name=PIXABAY_LICENSE,
                    license_url=PIXABAY_LICENSE_URL,
                    status="cleared",
                    attribution_required=False,
                    license={
                        "attribution": f"Video by {creator} on Pixabay",
                        "license_id": "pixabay",
                    },
                    metadata={
                        "id": hit.get("id"),
                        "duration": duration,
                        "width": variant.get("width"),
                        "height": variant.get("height"),
                        "tags": hit.get("tags"),
                        "creator": creator,
                    },
                    suggested_filename=f"pixabay-{hit.get('id', 'video')}{suffix}",
                )
            )
            if len(results) >= max_results:
                break
        return results

    def search_images(
        self,
        query: str,
        *,
        count: int = 5,
        orientation: str = "landscape",
    ) -> list[RemoteAsset]:
        payload = self.get_json(
            f"{PIXABAY_API}/",
            params={
                "key": self.api_key,
                "q": query,
                "image_type": "photo",
                "safesearch": "true",
                "per_page": max(3, min(count * 3, 200)),
                "orientation": {
                    "landscape": "horizontal",
                    "portrait": "vertical",
                    "square": "all",
                }.get(orientation, "all"),
            },
        )
        results: list[RemoteAsset] = []
        for hit in payload.get("hits", []):
            if not isinstance(hit, dict):
                continue
            link = hit.get("largeImageURL") or hit.get("webformatURL")
            if not link:
                continue
            creator = str(hit.get("user") or "Pixabay contributor")
            suffix = _suffix_for(str(link), ".jpg")
            results.append(
                RemoteAsset(
                    provider="pixabay",
                    media_type="image",
                    download_url=str(link),
                    page_url=str(hit.get("pageURL") or ""),
                    creator=creator,
                    license_name=PIXABAY_LICENSE,
                    license_url=PIXABAY_LICENSE_URL,
                    status="cleared",
                    attribution_required=False,
                    license={
                        "attribution": f"Image by {creator} on Pixabay",
                        "license_id": "pixabay",
                    },
                    metadata={
                        "id": hit.get("id"),
                        "width": hit.get("imageWidth"),
                        "height": hit.get("imageHeight"),
                        "tags": hit.get("tags"),
                        "creator": creator,
                    },
                    suggested_filename=f"pixabay-{hit.get('id', 'image')}{suffix}",
                )
            )
            if len(results) >= count:
                break
        return results


def _pick_pixabay_video(variants: Mapping[str, Any]) -> dict[str, Any] | None:
    usable: list[dict[str, Any]] = []
    for key in ("large", "medium", "small", "tiny"):
        item = variants.get(key)
        if isinstance(item, dict) and item.get("url"):
            usable.append(item)
    if not usable:
        return None
    preferred = [item for item in usable if int(item.get("width") or 0) <= 1920]
    return (preferred or usable)[0]
