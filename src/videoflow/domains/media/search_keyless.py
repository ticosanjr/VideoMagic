"""Keyless Openverse, Wikimedia, Internet Archive and YouTube searches."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

import httpx

from videoflow.application.secrets import get_secret
from videoflow.application.settings import AppSettings
from videoflow.domain.errors import CapabilityUnavailableError, SearchError
from videoflow.domains.media.models import AssetCandidate, _candidate
from videoflow.runtime import find_binary

from .search_base import _check_provider

_HTML = re.compile(r"<[^>]+>")


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
            "gsrsearch": f"filetype:{'video' if media == 'video' else 'bitmap'} {query}",
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
        ext = info.get("extmetadata") or {}
        license_text = str((ext.get("LicenseShortName") or {}).get("value") or "")
        license_url = str((ext.get("LicenseUrl") or {}).get("value") or "")
        artist = _HTML.sub("", str((ext.get("Artist") or {}).get("value") or ""))
        suffix = Path(urlparse(url).path).suffix.casefold()
        kind = (
            "image"
            if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
            else "video"
        )
        if media not in {"all", kind}:
            continue
        results.append(
            _candidate(
                provider="wikimedia",
                title=str(page.get("title") or "Wikimedia asset").removeprefix(
                    "File:"
                ),
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
            "q": f"mediatype:movies AND ({query})" if media == "video" else query,
            "fl[]": [
                "identifier",
                "title",
                "mediatype",
                "licenseurl",
                "creator",
                "date",
            ],
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
        kind = (
            "video"
            if mediatype == "movies"
            else "image"
            if mediatype == "image"
            else ""
        )
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


