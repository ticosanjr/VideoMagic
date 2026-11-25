"""Keyless Wikimedia Commons provider."""

# ruff: noqa: F405

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .base import *  # noqa: F401,F403,F405
from .base import _suffix_for

_VIDEO_SUFFIXES = {".webm", ".ogv", ".ogg", ".mp4", ".m4v", ".mov", ".mkv"}


class WikimediaClient(HttpClient):
    """Keyless Wikimedia Commons image and video search with license metadata."""

    provider_name = "wikimedia"
    api = "https://commons.wikimedia.org/w/api.php"

    def search_videos(
        self,
        query: str,
        *,
        max_results: int = 5,
        min_duration: float = 0.0,
        orientation: str = "landscape",
    ) -> list[RemoteAsset]:
        """Search Commons for freely licensed video clips."""

        payload = self.get_json(
            self.api,
            params={
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": f"filetype:video {query}",
                "gsrnamespace": 6,
                "gsrlimit": max(1, min(max_results * 3, 50)),
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|size",
            },
        )
        pages = (payload.get("query") or {}).get("pages") or {}
        results: list[RemoteAsset] = []
        for page in pages.values() if isinstance(pages, dict) else []:
            if not isinstance(page, dict):
                continue
            info = (page.get("imageinfo") or [{}])[0]
            link = str(info.get("url") or "").strip()
            suffix = _suffix_for(link, ".webm")
            if not link or suffix not in _VIDEO_SUFFIXES:
                continue
            duration = float(info.get("duration") or 0.0)
            if min_duration and duration and duration < min_duration:
                continue
            meta = info.get("extmetadata") or {}
            license_name = _commons_value(meta, "LicenseShortName") or "unknown"
            license_url = _commons_value(meta, "LicenseUrl")
            creator = _commons_value(meta, "Artist") or "Wikimedia Commons contributor"
            reviewed = bool(
                re.search(r"non-?commercial|no.?deriv|fair.?use", license_name, re.I)
            )
            results.append(
                RemoteAsset(
                    provider="wikimedia",
                    media_type="video",
                    download_url=link,
                    page_url=str(
                        info.get("descriptionurl") or page.get("title") or ""
                    ),
                    creator=creator,
                    license_name=license_name,
                    license_url=license_url,
                    status="cc_review" if reviewed else "cleared",
                    attribution_required=True,
                    license={
                        "license_id": str(
                            meta.get("License", {}).get("value") or license_name
                        ),
                        "attribution": f"{creator} / Wikimedia Commons ({license_name})",
                    },
                    metadata={
                        "id": page.get("pageid"),
                        "title": page.get("title"),
                        "creator": creator,
                        "width": info.get("width"),
                        "height": info.get("height"),
                        "duration": duration,
                        "size_bytes": info.get("size") or 0,
                        "description": _commons_value(meta, "ImageDescription"),
                    },
                    suggested_filename=(
                        f"wikimedia-{page.get('pageid', 'video')}{suffix}"
                    ),
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
            self.api,
            params={
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap {query}",
                "gsrnamespace": 6,
                "gsrlimit": max(1, min(count * 3, 50)),
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|size",
                "iiurlwidth": 1600,
            },
        )
        pages = (payload.get("query") or {}).get("pages") or {}
        results: list[RemoteAsset] = []
        for page in pages.values() if isinstance(pages, dict) else []:
            if not isinstance(page, dict):
                continue
            info = (page.get("imageinfo") or [{}])[0]
            link = str(info.get("thumburl") or info.get("url") or "").strip()
            if not link:
                continue
            meta = info.get("extmetadata") or {}
            license_name = _commons_value(meta, "LicenseShortName") or "unknown"
            license_url = _commons_value(meta, "LicenseUrl")
            creator = _commons_value(meta, "Artist") or "Wikimedia Commons contributor"
            reviewed = bool(re.search(r"non-?commercial|no.?deriv|fair.?use", license_name, re.I))
            suffix = _suffix_for(link, ".jpg")
            results.append(
                RemoteAsset(
                    provider="wikimedia",
                    media_type="image",
                    download_url=link,
                    page_url=str(info.get("descriptionurl") or page.get("title") or ""),
                    creator=creator,
                    license_name=license_name,
                    license_url=license_url,
                    status="cc_review" if reviewed else "cleared",
                    attribution_required=True,
                    license={
                        "license_id": str(meta.get("License", {}).get("value") or license_name),
                        "attribution": f"{creator} / Wikimedia Commons ({license_name})",
                    },
                    metadata={
                        "id": page.get("pageid"),
                        "title": page.get("title"),
                        "creator": creator,
                        "width": info.get("width"),
                        "height": info.get("height"),
                        "size_bytes": info.get("size") or 0,
                        "description": _commons_value(meta, "ImageDescription"),
                    },
                    suggested_filename=f"wikimedia-{page.get('pageid', 'image')}{suffix}",
                )
            )
            if len(results) >= count:
                break
        return results


def _commons_value(meta: Mapping[str, Any], key: str) -> str:
    value = meta.get(key)
    raw = (
        str(value.get("value") or "")
        if isinstance(value, dict)
        else str(value or "")
    )
    return re.sub(r"<[^>]+>", "", raw).strip()
