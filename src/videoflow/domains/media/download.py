"""Download asset candidates into the local output tree."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path

import httpx

from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.settings import AppSettings, load_settings
from videoflow.application.url_safety import assert_public_url
from videoflow.domain.errors import CapabilityUnavailableError, IngestError
from videoflow.domains.media.models import AssetCandidate
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


def _probe_video(path: Path) -> tuple[float, int, bool]:
    binary = find_binary("ffprobe")
    if binary is None:
        return 0.0, 0, False
    completed = subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        return 0.0, 0, False
    try:
        payload = json.loads(completed.stdout or "{}")
    except ValueError:
        return 0.0, 0, False
    streams = payload.get("streams") or []
    video = next(
        (item for item in streams if item.get("codec_type") == "video"),
        {},
    )
    has_audio = any(item.get("codec_type") == "audio" for item in streams)
    try:
        duration = float((payload.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    try:
        height = int(video.get("height") or 0)
    except (TypeError, ValueError):
        height = 0
    return max(0.0, duration), height, has_audio


def trim_stock_video(
    path: Path | str,
    *,
    max_duration_sec: float = 12.0,
    clip_sec: float = 8.0,
    max_height: int = 1080,
    destination: Path | str | None = None,
) -> Path:
    """Trim a long or oversized stock clip to a light 1080p excerpt."""

    source = Path(path).expanduser()
    duration, height, has_audio = _probe_video(source)
    if duration <= max_duration_sec and height <= max_height:
        return source
    ffmpeg = find_binary("ffmpeg")
    if ffmpeg is None:
        return source
    target = (
        Path(destination).expanduser()
        if destination is not None
        else source.with_name(f"{source.stem}-clip{int(round(clip_sec))}.mp4")
    )
    start = 2.0 if duration > max_duration_sec else 0.0
    if duration > 0:
        start = max(0.0, min(start, max(0.0, duration - clip_sec)))
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{max(0.1, clip_sec):.3f}",
        "-vf",
        f"scale='min({int(max_height)},iw)':-2,fps=30",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "23",
    ]
    if has_audio:
        command.extend(["-map", "0:v:0", "-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"])
    else:
        command.append("-an")
    command.extend(["-movflags", "+faststart", str(target)])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0 or not target.is_file():
        target.unlink(missing_ok=True)
        return source
    return target


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
    if candidate.kind == "video":
        path = trim_stock_video(path)
    data = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            data.update(chunk)
    candidate.downloaded_path = str(path)
    candidate.sha256 = data.hexdigest()
    candidate.retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return candidate
