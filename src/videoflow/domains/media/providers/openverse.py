"""Keyless Openverse provider."""

# ruff: noqa: F405

from __future__ import annotations

import re

from .base import *  # noqa: F401,F403,F405
from .base import _suffix_for


class OpenverseClient(HttpClient):
    """Keyless Openverse image search with license metadata."""

    provider_name = "openverse"
    api = "https://api.openverse.org"

    def search_images(
        self,
        query: str,
        *,
        count: int = 5,
        orientation: str = "landscape",
    ) -> list[RemoteAsset]:
        payload = self.get_json(
            f"{self.api}/v1/images/",
            params={"q": query, "page_size": max(1, min(count * 3, 50))},
        )
        results: list[RemoteAsset] = []
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            link = str(item.get("url") or item.get("thumbnail") or "").strip()
            if not link:
                continue
            license_code = str(item.get("license") or "").strip().lower()
            reviewed = bool(
                re.search(r"nc|nd|noncommercial|noderiv", license_code)
                or re.search(r"nc|nd", str(item.get("license_version") or ""))
            )
            creator = str(item.get("creator") or "Openverse contributor")
            attribution = str(item.get("attribution") or f"{creator} (Openverse)")
            suffix = _suffix_for(link, ".jpg")
            results.append(
                RemoteAsset(
                    provider="openverse",
                    media_type="image",
                    download_url=link,
                    page_url=str(item.get("foreign_landing_url") or item.get("detail_url") or ""),
                    creator=creator,
                    license_name=str(item.get("license") or "unknown"),
                    license_url=str(item.get("license_url") or ""),
                    status="cc_review" if reviewed else "cleared",
                    attribution_required=True,
                    license={
                        "license_id": license_code or "unknown",
                        "license_version": item.get("license_version"),
                        "attribution": attribution,
                    },
                    metadata={
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "creator": creator,
                        "source": item.get("source"),
                        "width": item.get("width"),
                        "height": item.get("height"),
                    },
                    suggested_filename=f"openverse-{item.get('id', 'image')}{suffix}",
                )
            )
            if len(results) >= count:
                break
        return results
