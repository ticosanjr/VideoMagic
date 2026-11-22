"""Freesound SFX provider."""

# ruff: noqa: F405

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import (
    InvalidRequestError,
    ProviderUnavailableError,
)
from .base import *  # noqa: F401,F403,F405
from .base import _suffix_for


class FreesoundClient(HttpClient):
    """Freesound CC-licensed sound search."""

    provider_name = "freesound"

    def __init__(self, api_key: str, **kwargs: Any) -> None:
        if not api_key:
            raise ProviderUnavailableError("FREESOUND_API_KEY is not set.")
        super().__init__(**kwargs)
        self.api_key = api_key

    def search_sfx(
        self,
        query: str,
        *,
        max_duration: float = 5.0,
        license_filter: str = "cc0",
        max_results: int = 5,
    ) -> list[RemoteAsset]:
        filters: list[str] = []
        if max_duration > 0:
            filters.append(f"duration:[0 TO {max_duration:g}]")
        license_query = freesound_license_filter(license_filter)
        if license_query:
            filters.append(license_query)
        params: dict[str, Any] = {
            "query": query,
            "fields": "id,name,previews,duration,license,username,url",
            "page_size": max(1, min(max_results, 150)),
            "token": self.api_key,
        }
        if filters:
            params["filter"] = " ".join(filters)
        payload = self.get_json(f"{FREESOUND_API}/search/text/", params=params)
        results: list[RemoteAsset] = []
        for sound in payload.get("results", []):
            if not isinstance(sound, dict):
                continue
            duration = float(sound.get("duration") or 0.0)
            if max_duration > 0 and duration > max_duration:
                continue
            previews = sound.get("previews") or {}
            link = _pick_freesound_preview(previews)
            if not link:
                continue
            license_url = str(sound.get("license") or "")
            if not _freesound_license_allowed(license_filter, license_url):
                continue
            license_name = freesound_license_name(license_url)
            creator = str(sound.get("username") or "Freesound contributor")
            suffix = _suffix_for(link, ".mp3")
            status = "cleared" if "publicdomain/zero" in license_url else "cc_review"
            results.append(
                RemoteAsset(
                    provider="freesound",
                    media_type="audio",
                    download_url=link,
                    page_url=str(sound.get("url") or ""),
                    creator=creator,
                    license_name=license_name,
                    license_url=license_url,
                    status=status,
                    attribution_required="publicdomain/zero" not in license_url,
                    license={
                        "attribution": f"Sound by {creator} on Freesound",
                        "license_id": "freesound",
                    },
                    metadata={
                        "id": sound.get("id"),
                        "name": sound.get("name"),
                        "duration": duration,
                        "creator": creator,
                    },
                    suggested_filename=f"freesound-{sound.get('id', 'sound')}{suffix}",
                )
            )
            if len(results) >= max_results:
                break
        return results


def freesound_license_filter(value: str) -> str:
    normalized = (value or "any").strip().lower()
    if normalized in {"", "any", "all"}:
        return ""
    if normalized in {"cc0", "cc-0", "public-domain", "publicdomain"}:
        return 'license:"Creative Commons 0"'
    if normalized in {"cc-by", "cc_by", "ccby", "attribution"}:
        return 'license:"Attribution"'
    raise InvalidRequestError(f"Unknown license_filter {value!r}; use 'cc0', 'cc-by', or 'any'.")


def freesound_license_name(url: str) -> str:
    lowered = url.lower()
    if "publicdomain/zero" in lowered:
        return "CC0 1.0"
    if "/licenses/by/" in lowered:
        return "CC BY 4.0"
    if "/licenses/by-nc/" in lowered:
        return "CC BY-NC 4.0"
    return "Freesound license"


def _freesound_license_allowed(value: str, license_url: str) -> bool:
    normalized = (value or "any").strip().lower().replace("_", "-")
    if normalized in {"cc0", "cc-0", "public-domain", "publicdomain"}:
        return "publicdomain/zero" in license_url.lower()
    if normalized in {"cc-by", "ccby", "attribution"}:
        return "/licenses/by/" in license_url.lower()
    return True


def _pick_freesound_preview(previews: Mapping[str, Any]) -> str:
    for key in ("preview-hq-mp3", "preview-lq-mp3", "preview-hq-ogg", "preview-lq-ogg"):
        value = previews.get(key)
        if isinstance(value, str) and value:
            return value
    return ""
