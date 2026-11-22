"""Stock media provider clients with injectable HTTP transports.

Every network client accepts a pre-built ``httpx.Client`` (and therefore a fake
``httpx.MockTransport`` in tests). Subprocess providers use argument lists and
``shell=False`` exclusively.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..errors import (
    DownloadError,
    ProviderResponseError,
    UrlNotAllowedError,
)

PEXELS_API = "https://api.pexels.com"
PIXABAY_API = "https://pixabay.com/api"
FREESOUND_API = "https://freesound.org/apiv2"
USER_AGENT = "VideoFlow/3.16 (+https://github.com/videoflow-ai/videoflow)"
PEXELS_LICENSE = "Pexels License"
PEXELS_LICENSE_URL = "https://www.pexels.com/license/"
PIXABAY_LICENSE = "Pixabay Content License"
PIXABAY_LICENSE_URL = "https://pixabay.com/service/license-summary/"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp", ".tif", ".tiff"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def env_value(env: Mapping[str, str], name: str) -> str:
    return str(env.get(name, "")).strip()


def parse_allowed_hosts(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    hosts = []
    for part in value.split(","):
        host = part.strip().lower()
        if host:
            hosts.append(host)
    return tuple(hosts)


def validate_external_url(url: str, allowed_hosts: Sequence[str] = ()) -> str:
    """Validate an http(s) URL and, when configured, its host allowlist."""

    candidate = str(url or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UrlNotAllowedError(
            f"Unsupported URL {url!r}: only absolute http(s) URLs are allowed."
        )
    host = parsed.hostname.lower().rstrip(".")
    if allowed_hosts:
        allowed = tuple(item.lower().rstrip(".") for item in allowed_hosts)
        if not any(host == item or host.endswith(f".{item}") for item in allowed):
            raise UrlNotAllowedError(
                f"Host {host!r} is not in VF_ALLOWED_EXTERNAL_HOSTS ({', '.join(allowed)})."
            )
    return candidate


def _suffix_for(url: str, fallback: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    return suffix if suffix and len(suffix) <= 8 else fallback


@dataclass(slots=True)
class RemoteAsset:
    """A provider search result before it is downloaded."""

    provider: str
    media_type: str
    download_url: str
    page_url: str
    creator: str
    license: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    suggested_filename: str = ""
    license_name: str = ""
    license_url: str = ""
    status: str = "cleared"
    attribution_required: bool = False

    def to_license(self) -> dict[str, Any]:
        payload = {
            "provider": self.provider,
            "license": self.license_name,
            "license_url": self.license_url,
            "status": self.status,
            "commercial_use": self.status == "cleared",
            "attribution_required": self.attribution_required,
        }
        payload.update(self.license)
        return payload


@dataclass(slots=True)
class LocalAsset:
    """A local provider candidate."""

    path: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    license: dict[str, Any] = field(default_factory=dict)


class HttpClient:
    """Small httpx wrapper shared by the keyed providers."""

    provider_name = "http"

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._timeout = timeout

    def _request_headers(self, headers: Mapping[str, str] | None) -> dict[str, str]:
        merged = {"User-Agent": USER_AGENT}
        if headers:
            merged.update({str(key): str(value) for key, value in headers.items()})
        return merged

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        response = None
        attempts = 2 if self.provider_name in {"openverse", "wikimedia"} else 1
        for attempt in range(attempts):
            try:
                response = self._client.get(
                    url, params=params, headers=self._request_headers(headers)
                )
            except httpx.HTTPError as exc:
                raise ProviderResponseError(
                    f"{self.provider_name} request failed: {exc}",
                    detail={"url": url},
                ) from exc
            if response.status_code < 500 or attempt == attempts - 1:
                break
            time.sleep(0.6 * (attempt + 1))
        assert response is not None
        if response.status_code >= 400:
            snippet = response.text[:240].replace("\n", " ")
            raise ProviderResponseError(
                f"{self.provider_name} returned HTTP {response.status_code}: {snippet}",
                detail={"url": url, "status": response.status_code},
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError(
                f"{self.provider_name} returned invalid JSON", detail={"url": url}
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError(
                f"{self.provider_name} returned an unexpected payload", detail={"url": url}
            )
        return payload

    def download(
        self,
        url: str,
        destination: str | Path,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.stream(
                "GET", url, headers=self._request_headers(headers), follow_redirects=True
            ) as response:
                if response.status_code >= 400:
                    raise DownloadError(
                        f"{self.provider_name} download returned HTTP {response.status_code}",
                        detail={"url": url, "status": response.status_code},
                    )
                with target.open("wb") as handle:
                    for chunk in response.iter_bytes(64 * 1024):
                        handle.write(chunk)
        except DownloadError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            target.unlink(missing_ok=True)
            raise DownloadError(
                f"{self.provider_name} download failed: {exc}", detail={"url": url}
            ) from exc
        if not target.is_file() or target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            raise DownloadError(f"{self.provider_name} returned an empty file", detail={"url": url})
        return target


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def safe_filename(name: str, *, fallback: str = "asset") -> str:
    """Return a single safe path component."""
    candidate = Path(str(name or "")).name
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._-")
    if not candidate:
        candidate = fallback
    if len(candidate) > 140:
        suffix = Path(candidate).suffix[:16]
        stem = Path(candidate).stem[: 140 - len(suffix)]
        candidate = f"{stem}{suffix}"
    return candidate

