"""Download a public URL into the local media workspace."""

from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from videoflow.application.capabilities import ensure_external_allowed
from videoflow.domain.errors import CapabilityUnavailableError, IngestError
from videoflow.runtime import find_binary, portable_home


def downloads_dir() -> Path:
    directory = portable_home() / "downloads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def import_url(
    url: str,
    *,
    max_height: int = 1080,
    allow_playlist: bool = False,
    allow_external_services: bool = False,
    allowed_external_hosts: tuple[str, ...] = (),
    timeout: float = 900.0,
) -> Path:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise IngestError("Only http(s) URLs are supported.")
    ensure_external_allowed(
        url,
        capability="url_import",
        allow_external_services=allow_external_services,
        allowed_hosts=allowed_external_hosts,
    )
    binary = find_binary("yt-dlp")
    if binary is None:
        raise CapabilityUnavailableError(
            "url_import",
            "yt-dlp is not installed. Install it or use a local file.",
        )
    directory = downloads_dir()
    stem = f"url-{uuid4().hex[:12]}"
    template = directory / f"{stem}.%(ext)s"
    command = [
        binary,
        "--no-warnings",
        "--no-progress",
        "--newline",
        "--no-playlist" if not allow_playlist else "--yes-playlist",
        "--socket-timeout",
        "30",
        "--merge-output-format",
        "mp4",
        "-f",
        f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
        "-o",
        str(template),
    ]
    ffmpeg = find_binary("ffmpeg")
    if ffmpeg is not None:
        command.extend(["--ffmpeg-location", str(Path(ffmpeg).parent)])
    command.append(url.strip())
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IngestError(f"URL import failed: {exc}") from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()[:300]
        raise IngestError(f"yt-dlp failed: {message or 'unknown error'}")
    files = sorted(directory.glob(f"{stem}.*"))
    if not files:
        raise IngestError("yt-dlp finished without a media file.")
    return files[0]
