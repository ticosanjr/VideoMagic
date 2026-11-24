"""Keyless Internet Archive video provider."""

# ruff: noqa: F405

from __future__ import annotations

from pathlib import Path

from .base import *  # noqa: F401,F403,F405
from .base import _suffix_for

_VIDEO_SUFFIXES = {".mp4", ".m4v", ".mov", ".webm", ".ogv", ".mkv"}


class InternetArchiveClient(HttpClient):
    """Search the Internet Archive movie collection without an API key."""

    provider_name = "internet_archive"
    search_api = "https://archive.org/advancedsearch.php"

    def search_videos(
        self,
        query: str,
        *,
        max_results: int = 5,
        min_duration: float = 0.0,
        orientation: str = "landscape",
    ) -> list[RemoteAsset]:
        payload = self.get_json(
            self.search_api,
            params={
                "q": f"mediatype:movies AND ({query})",
                "fl[]": [
                    "identifier",
                    "title",
                    "mediatype",
                    "licenseurl",
                    "creator",
                    "date",
                ],
                "rows": max(1, min(max_results * 3, 50)),
                "page": 1,
                "output": "json",
            },
        )
        docs = (payload.get("response") or {}).get("docs") or []
        results: list[RemoteAsset] = []
        for doc in docs[: max_results * 3]:
            identifier = str(doc.get("identifier") or "").strip()
            if not identifier:
                continue
            metadata = self.get_json(f"https://archive.org/metadata/{identifier}")
            files = metadata.get("files") or []
            chosen = next(
                (
                    item
                    for item in files
                    if Path(str(item.get("name") or "")).suffix.casefold()
                    in _VIDEO_SUFFIXES
                ),
                None,
            )
            if chosen is None:
                continue
            duration = 0.0
            try:
                duration = float(metadata.get("metadata", {}).get("length") or 0.0)
            except (TypeError, ValueError):
                duration = 0.0
            if min_duration and duration and duration < min_duration:
                continue
            name = str(chosen.get("name") or f"{identifier}.mp4")
            suffix = _suffix_for(name, ".mp4")
            creator = str(doc.get("creator") or "Internet Archive contributor")
            license_url = str(doc.get("licenseurl") or "")
            results.append(
                RemoteAsset(
                    provider="internet_archive",
                    media_type="video",
                    download_url=f"https://archive.org/download/{identifier}/{name}",
                    page_url=f"https://archive.org/details/{identifier}",
                    creator=creator,
                    license_name=license_url or "Internet Archive",
                    license_url=license_url,
                    status="cleared",
                    attribution_required=True,
                    license={
                        "license_id": license_url or "internet_archive",
                        "attribution": f"{creator} / Internet Archive",
                    },
                    metadata={
                        "id": identifier,
                        "title": doc.get("title"),
                        "creator": creator,
                        "duration": duration,
                    },
                    suggested_filename=f"archive-{identifier}{suffix}",
                )
            )
            if len(results) >= max_results:
                break
        return results
