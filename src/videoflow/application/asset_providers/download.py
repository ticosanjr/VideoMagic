"""Download asset candidates into the local output tree."""

from __future__ import annotations

import hashlib
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path

import httpx

from videoflow.application.asset_providers.models import AssetCandidate
from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.search import assert_public_url
from videoflow.application.settings import AppSettings, load_settings
from videoflow.domain.errors import CapabilityUnavailableError, IngestError
from videoflow.runtime import find_binary


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
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=900, check=False
    )
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
