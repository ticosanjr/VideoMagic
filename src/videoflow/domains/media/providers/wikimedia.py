"""Keyless Wikimedia Commons provider."""

# ruff: noqa: F405

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .base import *  # noqa: F401,F403,F405
from .base import _suffix_for


class WikimediaClient(HttpClient):
    """Keyless Wikimedia Commons image search with license metadata."""

    provider_name = "wikimedia"
    api = "https://commons.wikimedia.org/w/api.php"

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
