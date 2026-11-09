"""Licensed media discovery and harvesting.

Providers return a normalized candidate with an explicit license status. The
ledger is the source of truth for export: ``unknown`` and unapproved
``fair_use_review`` assets block the final NLE export.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.search import assert_public_url
from videoflow.application.secrets import get_secret
from videoflow.application.settings import AppSettings, load_settings
from videoflow.domain.errors import CapabilityUnavailableError, IngestError, SearchError
from videoflow.runtime import find_binary

_LICENSE_CC0 = {"cc0", "public domain", "publicdomain", "pdm", "no known copyright"}
_LICENSE_FAIR = {"fair use", "fairuse", "youtube standard license"}
_HTML = re.compile(r"<[^>]+>")


@dataclass
class AssetCandidate:
    asset_id: str
    provider: str
    title: str
    page_url: str
    download_url: str
    kind: str = "video"
    license: str = ""
    license_url: str = ""
    license_status: str = "unknown"
    allowed_commercial: bool = False
    attribution_required: bool = True
    creator: str = ""
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    query: str = ""
    unit_id: str = ""
    clip_start_sec: float = 0.0
    clip_end_sec: float = 0.0
    fair_use_rationale: str = ""
    downloaded_path: str = ""
    sha256: str = ""
    retrieved_at: str = ""
    approved: bool = False
    approval_id: str = ""
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "provider": self.provider,
            "title": self.title,
            "page_url": self.page_url,
            "download_url": self.download_url,
            "kind": self.kind,
            "license": self.license,
            "license_url": self.license_url,
            "license_status": self.license_status,
            "allowed_commercial": self.allowed_commercial,
            "attribution_required": self.attribution_required,
            "creator": self.creator,
            "duration_sec": self.duration_sec,
            "width": self.width,
            "height": self.height,
            "query": self.query,
            "unit_id": self.unit_id,
            "clip_start_sec": self.clip_start_sec,
            "clip_end_sec": self.clip_end_sec,
            "fair_use_rationale": self.fair_use_rationale,
            "downloaded_path": self.downloaded_path,
            "sha256": self.sha256,
            "retrieved_at": self.retrieved_at,
            "approved": self.approved,
            "approval_id": self.approval_id,
            "notes": self.notes,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AssetCandidate:
        allowed = {
            "asset_id",
            "provider",
            "title",
            "page_url",
            "download_url",
            "kind",
            "license",
            "license_url",
            "license_status",
            "allowed_commercial",
            "attribution_required",
            "creator",
            "duration_sec",
            "width",
            "height",
            "query",
            "unit_id",
            "clip_start_sec",
            "clip_end_sec",
            "fair_use_rationale",
            "downloaded_path",
            "sha256",
            "retrieved_at",
            "approved",
            "approval_id",
            "notes",
            "metadata",
        }
        return cls(**{key: value for key, value in payload.items() if key in allowed})


def _asset_id(provider: str, url: str) -> str:
    return f"{provider[:8]}-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}"


def classify_license(
    license_text: str, *, provider: str = "", license_url: str = ""
) -> tuple[str, bool, bool]:
    """Return status, allowed_for_commercial, attribution_required."""

    lowered = f"{license_text} {provider} {license_url}".casefold()
    if provider in {"pexels", "pixabay"}:
        return "cleared", True, False
    if any(token in lowered for token in _LICENSE_FAIR) or provider == "youtube":
        return "fair_use_review", False, True
    if any(token in lowered for token in _LICENSE_CC0):
        return "cleared", True, False
    if "cc" in lowered or "creative commons" in lowered:
        allowed = not any(token in lowered for token in ("nc", "noncommercial", "nd"))
        return "cc_review", allowed, True
    if license_text.strip():
        return "cc_review", False, True
    return "unknown", False, True


def _candidate(
    *,
    provider: str,
    title: str,
    page_url: str,
    download_url: str,
    query: str,
    kind: str = "video",
    license_text: str = "",
    license_url: str = "",
    creator: str = "",
    duration_sec: float = 0.0,
    width: int = 0,
    height: int = 0,
    metadata: dict[str, Any] | None = None,
) -> AssetCandidate:
    status, commercial, attribution = classify_license(
        license_text, provider=provider, license_url=license_url
    )
    return AssetCandidate(
        asset_id=_asset_id(provider, page_url or download_url),
        provider=provider,
        title=title,
        page_url=page_url,
        download_url=download_url,
        kind=kind,
        license=license_text,
        license_url=license_url,
        license_status=status,
        allowed_commercial=commercial,
        attribution_required=attribution,
        creator=creator,
        duration_sec=duration_sec,
        width=width,
        height=height,
        query=query,
        fair_use_rationale=(
            "Short excerpt used for commentary, criticism, or contextual "
            "documentation; human approval required."
            if status == "fair_use_review"
            else ""
        ),
        metadata=metadata or {},
    )


def _check_provider(
    url: str,
    *,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
) -> None:
    ensure_external_allowed(
        url,
        capability="stock_assets",
        allow_external_services=allow_external_services,
        allowed_hosts=tuple(allowed_external_hosts),
    )


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
                    title=str(video.get("url", "").rstrip("/").split("/")[-1] or "Pexels video"),
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
                        download_url=str(src.get("large2x") or src.get("original") or ""),
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


def _openverse(
    query: str,
    *,
    settings: AppSettings,
    limit: int,
    media: str,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
) -> list[AssetCandidate]:
    _check_provider(
        "https://api.openverse.org",
        allow_external_services=allow_external_services,
        allowed_external_hosts=allowed_external_hosts,
    )
    token = get_secret(settings.stock.openverse_token_env)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    results: list[AssetCandidate] = []
    for kind, endpoint in (("image", "images"), ("audio", "audio")):
        if media not in {"all", kind}:
            continue
        response = httpx.get(
            f"https://api.openverse.org/v1/{endpoint}/",
            params={"q": query, "page_size": limit},
            headers=headers,
            timeout=20,
        )
        if response.status_code >= 400:
            continue
        for item in response.json().get("results", [])[:limit]:
            results.append(
                _candidate(
                    provider="openverse",
                    title=str(item.get("title") or "Openverse asset"),
                    page_url=str(item.get("foreign_landing_url") or ""),
                    download_url=str(item.get("url") or ""),
                    query=query,
                    kind=kind,
                    license_text=str(item.get("license") or ""),
                    license_url=str(item.get("license_url") or ""),
                    creator=str(item.get("creator") or ""),
                )
            )
    return results[:limit]


def _wikimedia(
    query: str,
    *,
    limit: int,
    media: str,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
) -> list[AssetCandidate]:
    _check_provider(
        "https://commons.wikimedia.org",
        allow_external_services=allow_external_services,
        allowed_external_hosts=allowed_external_hosts,
    )
    response = httpx.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "format": "json",
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise SearchError(f"Wikimedia returned HTTP {response.status_code}.")
    results: list[AssetCandidate] = []
    for page in (response.json().get("query") or {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        url = str(info.get("url") or "")
        if not url:
            continue
        ext = (info.get("extmetadata") or {})
        license_text = str(
            (ext.get("LicenseShortName") or {}).get("value") or ""
        )
        license_url = str((ext.get("LicenseUrl") or {}).get("value") or "")
        artist = _HTML.sub("", str((ext.get("Artist") or {}).get("value") or ""))
        suffix = Path(urlparse(url).path).suffix.casefold()
        kind = "image" if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else "video"
        if media not in {"all", kind}:
            continue
        results.append(
            _candidate(
                provider="wikimedia",
                title=str(page.get("title") or "Wikimedia asset").removeprefix("File:"),
                page_url=str(info.get("descriptionurl") or ""),
                download_url=url,
                query=query,
                kind=kind,
                license_text=license_text,
                license_url=license_url,
                creator=artist,
            )
        )
    return results[:limit]


def _internet_archive(
    query: str,
    *,
    limit: int,
    media: str,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
) -> list[AssetCandidate]:
    _check_provider(
        "https://archive.org",
        allow_external_services=allow_external_services,
        allowed_external_hosts=allowed_external_hosts,
    )
    response = httpx.get(
        "https://archive.org/advancedsearch.php",
        params={
            "q": query,
            "fl[]": ["identifier", "title", "mediatype", "licenseurl", "creator", "date"],
            "rows": limit,
            "page": 1,
            "output": "json",
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise SearchError(f"Internet Archive returned HTTP {response.status_code}.")
    results: list[AssetCandidate] = []
    for doc in (response.json().get("response") or {}).get("docs", [])[:limit]:
        identifier = str(doc.get("identifier") or "")
        if not identifier:
            continue
        mediatype = str(doc.get("mediatype") or "")
        kind = "video" if mediatype == "movies" else "image" if mediatype == "image" else ""
        if not kind or media not in {"all", kind}:
            continue
        metadata = httpx.get(
            f"https://archive.org/metadata/{identifier}", timeout=20
        )
        if metadata.status_code >= 400:
            continue
        files = metadata.json().get("files") or []
        chosen = next(
            (
                item
                for item in files
                if Path(str(item.get("name") or "")).suffix.casefold()
                in (
                    {".mp4", ".mov", ".m4v"}
                    if kind == "video"
                    else {".jpg", ".jpeg", ".png", ".webp"}
                )
            ),
            None,
        )
        if not chosen:
            continue
        results.append(
            _candidate(
                provider="internet_archive",
                title=str(doc.get("title") or identifier),
                page_url=f"https://archive.org/details/{identifier}",
                download_url=f"https://archive.org/download/{identifier}/{chosen['name']}",
                query=query,
                kind=kind,
                license_text=str(doc.get("licenseurl") or ""),
                license_url=str(doc.get("licenseurl") or ""),
                creator=str(doc.get("creator") or ""),
            )
        )
    return results[:limit]


def _youtube(
    query: str,
    *,
    limit: int,
    media: str,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
) -> list[AssetCandidate]:
    if media not in {"all", "video"}:
        return []
    binary = find_binary("yt-dlp")
    if binary is None:
        raise CapabilityUnavailableError("youtube", "yt-dlp is not installed.")
    _check_provider(
        "https://www.youtube.com",
        allow_external_services=allow_external_services,
        allowed_external_hosts=allowed_external_hosts,
    )
    completed = subprocess.run(
        [
            binary,
            "--flat-playlist",
            "--no-warnings",
            "--print",
            "%(id)s\t%(title)s\t%(duration)s\t%(uploader)s",
            f"ytsearch{limit}:{query}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise SearchError(f"YouTube search failed: {completed.stderr[:300]}")
    results: list[AssetCandidate] = []
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        video_id, title, duration, uploader = parts[:4]
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            duration_sec = float(duration)
        except ValueError:
            duration_sec = 0.0
        results.append(
            _candidate(
                provider="youtube",
                title=title,
                page_url=url,
                download_url=url,
                query=query,
                kind="video",
                license_text="YouTube Standard License",
                license_url="https://www.youtube.com/static?template=terms",
                creator=uploader,
                duration_sec=duration_sec,
            )
        )
    return results[:limit]


PROVIDERS: dict[str, Any] = {
    "pexels": _pexels,
    "pixabay": _pixabay,
    "openverse": _openverse,
    "wikimedia": _wikimedia,
    "internet_archive": _internet_archive,
    "youtube": _youtube,
}


def search_assets(
    query: str,
    *,
    providers: Iterable[str],
    settings: AppSettings | None = None,
    media: str = "all",
    limit: int = 3,
    allow_external_services: bool = False,
    allowed_external_hosts: Iterable[str] = (),
) -> list[AssetCandidate]:
    current = settings or load_settings()
    results: list[AssetCandidate] = []
    errors: list[str] = []
    for name in providers:
        provider = name.strip().casefold()
        function = PROVIDERS.get(provider)
        if function is None:
            continue
        try:
            if provider in {"pixabay", "openverse"} or provider == "pexels":
                batch = function(
                    query,
                    settings=current,
                    limit=limit,
                    media=media,
                    allow_external_services=allow_external_services,
                    allowed_external_hosts=allowed_external_hosts,
                )
            else:
                batch = function(
                    query,
                    limit=limit,
                    media=media,
                    allow_external_services=allow_external_services,
                    allowed_external_hosts=allowed_external_hosts,
                )
            results.extend(batch)
        except Exception as exc:  # noqa: BLE001 - try the next provider
            errors.append(f"{provider}: {exc}")
    if not results and errors:
        raise SearchError("No asset provider returned results: " + " | ".join(errors))
    return results[:limit]


def _clip_bounds(candidate: AssetCandidate, clip_seconds: int) -> tuple[float, float]:
    if candidate.kind != "video" or candidate.provider != "youtube":
        return 0.0, 0.0
    duration = max(0.0, candidate.duration_sec)
    clip = float(max(1, clip_seconds))
    if duration and duration <= clip:
        return 0.0, duration
    start = candidate.clip_start_sec or (duration * 0.1 if duration else 0.0)
    if duration:
        start = max(0.0, min(start, duration - clip))
    return round(start, 3), round(start + clip, 3)


def _download_http(
    url: str,
    destination: Path,
    *,
    settings: AppSettings,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
) -> Path:
    assert_public_url(url, allowed_external_hosts)
    ensure_external_allowed(
        url,
        capability="stock_assets",
        allow_external_services=allow_external_services,
        allowed_hosts=tuple(allowed_external_hosts),
    )
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.part")
    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": "VideoFlowAssetHarvest/1.0"},
        timeout=60,
        follow_redirects=True,
    ) as response:
        if response.status_code >= 400:
            raise IngestError(f"Asset download returned HTTP {response.status_code}.")
        size = 0
        with temporary.open("wb") as handle:
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 2 * 1024 * 1024 * 1024:
                    raise IngestError("Asset download exceeded the 2 GB limit.")
                handle.write(chunk)
    temporary.replace(target)
    return target


def _download_youtube(
    candidate: AssetCandidate,
    destination: Path,
    *,
    settings: AppSettings,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
    clip_seconds: int,
) -> tuple[Path, float, float]:
    ensure_external_allowed(
        candidate.page_url,
        capability="stock_assets",
        allow_external_services=allow_external_services,
        allowed_hosts=tuple(allowed_external_hosts),
    )
    binary = find_binary("yt-dlp")
    if binary is None:
        raise CapabilityUnavailableError("youtube", "yt-dlp is not installed.")
    start, end = _clip_bounds(candidate, clip_seconds)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    template = target.with_suffix(".%(ext)s")
    command = [
        binary,
        "--no-warnings",
        "--no-progress",
        "--no-playlist",
        "--force-keyframes-at-cuts",
        "--download-sections",
        f"*{start}-{end}",
        "--merge-output-format",
        "mp4",
        "-f",
        "bv*[height<=1080]+ba/b[height<=1080]/b",
        "-o",
        str(template),
    ]
    ffmpeg = find_binary("ffmpeg")
    if ffmpeg is not None:
        command.extend(["--ffmpeg-location", str(Path(ffmpeg).parent)])
    command.append(candidate.page_url)
    completed = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
    if completed.returncode != 0:
        raise IngestError(f"YouTube excerpt failed: {completed.stderr[:300]}")
    files = sorted(target.parent.glob(f"{target.stem}.*"))
    if not files:
        raise IngestError("YouTube excerpt finished without a media file.")
    return files[0], start, end


def download_asset(
    candidate: AssetCandidate,
    destination: Path,
    *,
    settings: AppSettings | None = None,
    allow_external_services: bool = False,
    allowed_external_hosts: Iterable[str] = (),
    clip_seconds: int | None = None,
) -> AssetCandidate:
    current = settings or load_settings()
    clip = clip_seconds or current.stock.youtube_fair_use_seconds
    if candidate.provider == "youtube":
        path, start, end = _download_youtube(
            candidate,
            destination,
            settings=current,
            allow_external_services=allow_external_services,
            allowed_external_hosts=allowed_external_hosts,
            clip_seconds=clip,
        )
        candidate.clip_start_sec = start
        candidate.clip_end_sec = end
    else:
        path = _download_http(
            candidate.download_url,
            destination,
            settings=current,
            allow_external_services=allow_external_services,
            allowed_external_hosts=allowed_external_hosts,
        )
    data = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            data.update(chunk)
    candidate.downloaded_path = str(path)
    candidate.sha256 = data.hexdigest()
    candidate.retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return candidate


def ledger_payload(candidates: Iterable[AssetCandidate]) -> dict[str, Any]:
    records = [candidate.to_dict() for candidate in candidates]
    blockers = [
        record
        for record in records
        if record["license_status"] in {"unknown", "cc_review"}
        or (
            record["license_status"] == "fair_use_review"
            and not record["approved"]
        )
    ]
    return {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "assets": records,
        "blockers": blockers,
        "counts": {
            status: sum(1 for item in records if item["license_status"] == status)
            for status in sorted({item["license_status"] for item in records})
        },
    }


def write_ledger(output: Path, candidates: Iterable[AssetCandidate]) -> Path:
    payload = ledger_payload(candidates)
    directory = Path(output) / "assets"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "licenses.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Asset licenses", ""]
    for record in payload["assets"]:
        lines.append(
            f"- **{record['title']}** — {record['license_status']} — "
            f"{record['license'] or 'no license metadata'} — {record['page_url']}"
        )
    if payload["blockers"]:
        lines.extend(["", "## Needs review", *[
            f"- {item['title']} ({item['license_status']})" for item in payload["blockers"]
        ]])
    (directory / "licenses.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def read_ledger(output: Path) -> dict[str, Any]:
    path = Path(output) / "assets" / "licenses.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"assets": [], "blockers": []}
    return payload if isinstance(payload, dict) else {"assets": [], "blockers": []}


def license_blockers(output: Path) -> list[dict[str, Any]]:
    payload = read_ledger(output)
    blockers = []
    for record in payload.get("assets", []):
        if record.get("license_status") in {"unknown", "cc_review"} or (
            record.get("license_status") == "fair_use_review"
            and not record.get("approved")
        ):
            blockers.append(record)
    return blockers


def mark_approved(output: Path, *, approval_id: str, reviewer: str = "") -> Path:
    payload = read_ledger(output)
    for record in payload.get("assets", []):
        if record.get("license_status") in {"fair_use_review", "cc_review", "unknown"}:
            record["approved"] = True
            record["approval_id"] = approval_id
            record["notes"] = (
                f"{record.get('notes', '')}\nApproved by {reviewer or 'human'} at {approval_id}."
            ).strip()
    payload["blockers"] = [
        record
        for record in payload.get("assets", [])
        if record.get("license_status") in {"unknown", "cc_review"}
        or (
            record.get("license_status") == "fair_use_review"
            and not record.get("approved")
        )
    ]
    payload["counts"] = {
        status: sum(
            1 for item in payload.get("assets", []) if item.get("license_status") == status
        )
        for status in sorted(
            {str(item.get("license_status") or "unknown") for item in payload.get("assets", [])}
        )
    }
    return write_ledger_from_payload(output, payload)


def write_ledger_from_payload(output: Path, payload: dict[str, Any]) -> Path:
    path = Path(output) / "assets" / "licenses.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
