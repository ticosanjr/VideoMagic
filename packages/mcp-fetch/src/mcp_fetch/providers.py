"""Stock media provider clients with injectable HTTP transports.

Every network client accepts a pre-built ``httpx.Client`` (and therefore a fake
``httpx.MockTransport`` in tests). Subprocess providers use argument lists and
``shell=False`` exclusively.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlsplit

import httpx

from .errors import (
    DownloadError,
    InvalidRequestError,
    ProviderResponseError,
    ProviderUnavailableError,
    UrlNotAllowedError,
)
from .workspace import safe_filename, utc_now

PEXELS_API = "https://api.pexels.com"
PIXABAY_API = "https://pixabay.com/api"
FREESOUND_API = "https://freesound.org/apiv2"
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

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderResponseError(
                f"{self.provider_name} request failed: {exc}", detail={"url": url}
            ) from exc
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
                "GET", url, headers=headers, follow_redirects=True
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


class GalleryDLClient:
    """Keyless image downloader backed by the gallery-dl executable."""

    provider_name = "gallery-dl"

    def __init__(self, *, binary: str = "gallery-dl", timeout: float = 300.0) -> None:
        self.binary = binary
        self.timeout = timeout

    def ensure_available(self) -> str:
        resolved = shutil.which(self.binary)
        if resolved is None:
            raise ProviderUnavailableError(
                "gallery-dl is not installed; install gallery-dl, set "
                "PEXELS_API_KEY/PIXABAY_API_KEY, or request a keyed provider."
            )
        return resolved

    def fetch_images(
        self,
        query: str,
        *,
        count: int,
        destination: str | Path,
        allowed_hosts: Sequence[str] = (),
        url_template: str = "",
    ) -> list[Path]:
        binary = self.binary
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        if "://" in query:
            url = query
        elif url_template:
            url = url_template.replace("{query}", quote_plus(query))
        else:
            raise ProviderUnavailableError(
                "Keyless image search needs a direct image URL or "
                "VF_GALLERY_DL_URL_TEMPLATE with a {query} placeholder."
            )
        url = validate_external_url(url, allowed_hosts)
        command = [
            binary,
            "--dest",
            str(target),
            "--range",
            f"1-{max(1, count)}",
            url,
        ]
        completed = _run_subprocess(
            command,
            timeout=self.timeout,
            failure=(
                "gallery-dl is not installed; install gallery-dl or set "
                "PEXELS_API_KEY/PIXABAY_API_KEY"
            ),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-400:]
            raise DownloadError(
                f"gallery-dl exited with {completed.returncode}: {detail}",
                detail={"url": url},
            )
        images = find_media_files(target, IMAGE_SUFFIXES)
        if not images:
            raise DownloadError(
                "gallery-dl completed without producing an image.",
                detail={"url": url},
            )
        return images[:count]


class YtDlpClient:
    """Download one bounded segment with yt-dlp."""

    provider_name = "yt-dlp"

    def __init__(self, *, binary: str = "yt-dlp", timeout: float = 900.0) -> None:
        self.binary = binary
        self.timeout = timeout

    def ensure_available(self) -> str:
        resolved = shutil.which(self.binary)
        if resolved is None:
            raise ProviderUnavailableError(
                "yt-dlp is not installed; install yt-dlp to use rip_video_segment."
            )
        return resolved

    def download_segment(
        self,
        url: str,
        *,
        start_time: float,
        end_time: float,
        audio_only: bool,
        max_height: int,
        destination: str | Path,
        allowed_hosts: Sequence[str] = (),
    ) -> Path:
        binary = self.binary
        url = validate_external_url(url, allowed_hosts)
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        template = str(target / "%(title).80s-%(id)s.%(ext)s")
        command = [
            binary,
            "--no-playlist",
            "--no-warnings",
            "--no-progress",
            "--force-keyframes-at-cuts",
            "--download-sections",
            f"*{format_time(start_time)}-{format_time(end_time)}",
            "-o",
            template,
        ]
        if audio_only:
            command.extend(["-x", "--audio-format", "m4a"])
        else:
            command.extend(
                [
                    "-f",
                    f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
                ]
            )
        command.append(url)
        completed = _run_subprocess(
            command,
            timeout=self.timeout,
            failure="yt-dlp is not installed; install yt-dlp to use rip_video_segment",
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-400:]
            raise DownloadError(
                f"yt-dlp exited with {completed.returncode}: {detail}",
                detail={"url": url},
            )
        suffixes = AUDIO_SUFFIXES if audio_only else VIDEO_SUFFIXES
        files = find_media_files(target, suffixes)
        if not files:
            raise DownloadError(
                "yt-dlp completed without producing a media file.", detail={"url": url}
            )
        return files[0]


def format_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS or HH:MM:SS.mmm for yt-dlp sections."""

    if seconds < 0:
        raise InvalidRequestError("Time values must be non-negative.")
    whole = int(seconds)
    millis = round((seconds - whole) * 1000)
    if millis >= 1000:
        whole += 1
        millis = 0
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    base = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{base}.{millis:03d}" if millis else base


def _run_subprocess(
    command: list[str],
    *,
    timeout: float,
    failure: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise DownloadError(f"{failure}: timed out after {timeout:g}s") from exc
    except OSError as exc:
        raise ProviderUnavailableError(f"{failure}: {exc}") from exc


def find_media_files(directory: Path, suffixes: set[str]) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file()
        and path.suffix.lower() in suffixes
        and not path.name.endswith((".part", ".ytdl"))
    )


class LocalSfxProvider:
    """Search a user-managed SFX directory."""

    provider_name = "local"

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).expanduser().resolve()
        if not self.directory.is_dir():
            raise ProviderUnavailableError(
                f"VF_SFX_DIR does not exist or is not a directory: {self.directory}"
            )

    def search(
        self,
        query: str,
        *,
        max_duration: float = 5.0,
        license_filter: str = "cc0",
        max_results: int = 5,
    ) -> list[LocalAsset]:
        files = find_media_files(self.directory, AUDIO_SUFFIXES)
        if not files:
            return []
        tokens = [token for token in re.split(r"\W+", query.lower()) if token]
        ranked: list[tuple[int, Path]] = []
        for path in files:
            label = str(path.relative_to(self.directory)).lower()
            score = sum(1 for token in tokens if token in label)
            if tokens and score == 0:
                continue
            ranked.append((score, path))
        ranked.sort(key=lambda item: (-item[0], str(item[1])))
        results: list[LocalAsset] = []
        for _, path in ranked:
            metadata = self._metadata(path)
            duration = metadata.get("duration")
            if isinstance(duration, (int, float)) and max_duration > 0 and duration > max_duration:
                continue
            license_doc = self._license(path)
            wanted = (license_filter or "any").strip().lower().replace("_", "-")
            if wanted in {"cc0", "cc-0", "public-domain", "publicdomain"}:
                wanted = "cc0"
            elif wanted in {"cc-by", "ccby", "attribution"}:
                wanted = "by"
            declared = str(license_doc.get("license") or "").lower()
            explicit = license_doc.get("license_source") == "sidecar"
            if wanted not in {"", "any"} and explicit and wanted not in declared:
                continue
            results.append(
                LocalAsset(
                    path=path,
                    metadata=metadata,
                    license=license_doc,
                )
            )
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _sidecar(path: Path) -> dict[str, Any]:
        for candidate in (
            path.with_name(f"{path.name}.json"),
            path.with_suffix(".json"),
        ):
            if candidate.is_file():
                try:
                    payload = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(payload, dict):
                    return payload
        return {}

    def _metadata(self, path: Path) -> dict[str, Any]:
        payload = self._sidecar(path)
        metadata = payload.get("metadata")
        result = dict(metadata) if isinstance(metadata, dict) else {}
        duration = payload.get("duration")
        if isinstance(duration, (int, float)):
            result.setdefault("duration", float(duration))
        result.setdefault("name", path.name)
        result.setdefault("source_path", str(path))
        return result

    def _license(self, path: Path) -> dict[str, Any]:
        payload = self._sidecar(path)
        nested = payload.get("license")
        result = dict(nested) if isinstance(nested, dict) else {}
        for key in ("license", "license_url", "status", "attribution"):
            if key in payload and key not in result:
                result[key] = payload[key]
        if result:
            result["license_source"] = "sidecar"
        result.setdefault("license", "local")
        result.setdefault("license_url", "")
        result.setdefault("status", "unknown")
        result.setdefault("commercial_use", False)
        result.setdefault("attribution_required", False)
        result.setdefault("provider", "local")
        return result


def resolve_keyed_provider(
    requested: str,
    *,
    env: Mapping[str, str],
    media: str,
    client: httpx.Client | None = None,
) -> tuple[str, PexelsClient | PixabayClient]:
    """Resolve ``auto``/explicit names to an available keyed provider."""

    name = (requested or "auto").strip().lower()
    candidates = ("pexels", "pixabay") if name == "auto" else (name,)
    if name not in {"auto", "pexels", "pixabay"}:
        raise InvalidRequestError(
            f"Unknown provider {requested!r}; use 'auto', 'pexels', or 'pixabay'."
        )
    for candidate in candidates:
        if candidate == "pexels":
            key = env_value(env, "PEXELS_API_KEY")
            if key:
                return candidate, PexelsClient(key, client=client)
        else:
            key = env_value(env, "PIXABAY_API_KEY")
            if key:
                return candidate, PixabayClient(key, client=client)
    needed = "PEXELS_API_KEY or PIXABAY_API_KEY"
    if media == "images":
        needed += " (or enable keyless gallery-dl)"
    raise ProviderUnavailableError(f"No keyed {media} provider is configured; set {needed}.")


def resolve_sfx_provider(
    requested: str,
    *,
    env: Mapping[str, str],
    client: httpx.Client | None = None,
) -> tuple[str, FreesoundClient | LocalSfxProvider]:
    name = (requested or "auto").strip().lower()
    if name not in {"auto", "freesound", "local", "directory"}:
        raise InvalidRequestError(
            f"Unknown SFX provider {requested!r}; use 'auto', 'freesound', or 'local'."
        )
    if name in {"auto", "freesound"}:
        key = env_value(env, "FREESOUND_API_KEY")
        if key:
            return "freesound", FreesoundClient(key, client=client)
        if name == "freesound":
            raise ProviderUnavailableError("FREESOUND_API_KEY is not set.")
    directory = env_value(env, "VF_SFX_DIR")
    if directory and Path(directory).expanduser().is_dir():
        return "local", LocalSfxProvider(directory)
    if name in {"local", "directory"}:
        raise ProviderUnavailableError("VF_SFX_DIR is not set or does not point to a directory.")
    raise ProviderUnavailableError(
        "No SFX provider is configured; set FREESOUND_API_KEY or VF_SFX_DIR."
    )


__all__ = [
    "FreesoundClient",
    "GalleryDLClient",
    "HttpClient",
    "LocalAsset",
    "LocalSfxProvider",
    "PexelsClient",
    "PixabayClient",
    "RemoteAsset",
    "YtDlpClient",
    "env_value",
    "find_media_files",
    "format_time",
    "parse_allowed_hosts",
    "resolve_keyed_provider",
    "resolve_sfx_provider",
    "safe_filename",
    "utc_now",
    "validate_external_url",
]
