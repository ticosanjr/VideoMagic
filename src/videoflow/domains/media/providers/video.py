"""Gallery-dl and yt-dlp video providers."""

# ruff: noqa: F405

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote_plus

from ..errors import (
    DownloadError,
    InvalidRequestError,
    ProviderUnavailableError,
)
from .base import *  # noqa: F401,F403,F405


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
