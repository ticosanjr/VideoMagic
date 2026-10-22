"""Local and stock B-roll providers used by the ``broll.plan`` step."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from videoflow.domain.errors import CapabilityUnavailableError, IngestError

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True, slots=True)
class BrollAsset:
    provider: str
    path: Path | None = None
    url: str = ""
    attribution: str = ""
    license: str = ""
    source_url: str = ""


class LocalBrollProvider:
    provider = "local"

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory).expanduser()
        if not self.directory.is_dir():
            raise IngestError(f"B-roll directory does not exist: {self.directory}")

    def search(self, query: str, *, limit: int) -> list[BrollAsset]:
        assets = [
            path
            for path in sorted(self.directory.iterdir())
            if path.is_file() and path.suffix.casefold() in VIDEO_SUFFIXES | IMAGE_SUFFIXES
        ]
        words = {token for token in query.casefold().replace("_", " ").split() if token}
        ranked = sorted(
            assets,
            key=lambda asset: (
                -sum(1 for word in words if word in asset.stem.casefold()),
                asset.name.casefold(),
            ),
        )
        return [
            BrollAsset(provider="local", path=asset, attribution="local asset", license="operator")
            for asset in ranked[:limit]
        ]


class PexelsBrollProvider:
    provider = "pexels"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.pexels.com",
        client: httpx.Client | Any | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not api_key:
            raise CapabilityUnavailableError("stock_broll", "A Pexels API key is required.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=timeout)
        self.timeout = timeout

    def search(self, query: str, *, limit: int) -> list[BrollAsset]:
        response = self.client.get(
            f"{self.base_url}/videos/search",
            params={"query": query, "per_page": max(1, limit), "orientation": "portrait"},
            headers={"Authorization": self.api_key},
        )
        if response.status_code != 200:
            raise CapabilityUnavailableError(
                "stock_broll",
                f"Pexels search failed with HTTP {response.status_code}.",
            )
        payload = response.json()
        assets: list[BrollAsset] = []
        for video in payload.get("videos", []):
            files = video.get("video_files") or []
            chosen = _best_pexels_file(files)
            if not chosen:
                continue
            user = video.get("user") or {}
            assets.append(
                BrollAsset(
                    provider="pexels",
                    url=str(chosen.get("link", "")),
                    attribution=str(user.get("name", "Pexels")),
                    license="Pexels License",
                    source_url=str(video.get("url", "")),
                )
            )
        return assets[:limit]

    def download(self, asset: BrollAsset, destination: Path) -> Path:
        if not asset.url:
            raise IngestError("Stock B-roll asset has no download URL.")
        response = self.client.get(asset.url, headers={"Authorization": self.api_key})
        if response.status_code != 200:
            raise IngestError(f"Could not download B-roll asset: HTTP {response.status_code}")
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target


def _best_pexels_file(files: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    videos = [
        item
        for item in files
        if item.get("file_type") == "video/mp4" and item.get("link")
    ]
    if not videos:
        return None
    return min(
        videos,
        key=lambda item: abs(int(item.get("width") or 0) - 1280),
    )
