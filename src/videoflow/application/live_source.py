"""Browser-safe source proxies for live timeline playback."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.runtime import find_binary

LiveStatus = Literal["missing", "preparing", "ready", "failed"]
BROWSER_VIDEO = {"h264", "vp8", "vp9", "av1"}
BROWSER_AUDIO = {"aac", "mp3", "opus", "vorbis", "none", ""}
MAX_LIVE_HEIGHT = 1080


@dataclass
class LiveSourceState:
    status: LiveStatus = "missing"
    url: str = ""
    reason: str = ""
    path: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "url": self.url,
            "reason": self.reason,
            "path": self.path,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class LiveSourceManager:
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _states: dict[str, LiveSourceState] = field(default_factory=dict)
    _threads: dict[str, threading.Thread] = field(default_factory=dict)
    _compat: dict[str, tuple[bool, str]] = field(default_factory=dict)

    def _now(self) -> str:
        return datetime.now(UTC).isoformat(timespec="milliseconds")

    def _fingerprint(self, source: Path) -> str:
        try:
            stat = source.stat()
        except OSError:
            return str(source)
        return f"{source.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"

    def _probe(self, source: Path, height: int) -> tuple[bool, str]:
        fingerprint = self._fingerprint(source)
        with self._lock:
            cached = self._compat.get(fingerprint)
        if cached is not None:
            return cached
        if height > MAX_LIVE_HEIGHT:
            result = (False, f"source height {height}px exceeds the live limit")
        else:
            result = self._probe_codecs(source)
        with self._lock:
            self._compat[fingerprint] = result
        return result

    def _probe_codecs(self, source: Path) -> tuple[bool, str]:
        ffprobe = find_binary("ffprobe")
        if ffprobe is None:
            return False, "ffprobe is unavailable"
        try:
            completed = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,codec_name:format=format_name",
                    "-of",
                    "json",
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"could not probe the source: {exc}"
        if completed.returncode != 0:
            return False, "ffprobe could not read the source"
        try:
            payload = json.loads(completed.stdout)
            streams = payload.get("streams", [])
            format_name = str((payload.get("format") or {}).get("format_name") or "")
        except (ValueError, AttributeError):
            return False, "ffprobe returned invalid JSON"
        video = next(
            (item for item in streams if item.get("codec_type") == "video"), {}
        )
        audio = next(
            (item for item in streams if item.get("codec_type") == "audio"), {}
        )
        video_codec = str(video.get("codec_name") or "")
        audio_codec = str(audio.get("codec_name") or "none")
        containers = {item.strip() for item in format_name.split(",") if item.strip()}
        browser_containers = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "webm"}
        if not containers & browser_containers:
            return False, f"container {format_name or 'unknown'} is not browser-safe"
        if "webm" not in containers and video_codec not in BROWSER_VIDEO:
            return False, f"video codec {video_codec or 'unknown'} is not browser-safe"
        if "webm" in containers and video_codec not in {"vp8", "vp9", "av1"}:
            return False, f"video codec {video_codec or 'unknown'} is not webm-safe"
        if audio_codec not in BROWSER_AUDIO:
            return False, f"audio codec {audio_codec} is not browser-safe"
        return True, "source codec and container are browser-compatible"

    def _proxy_paths(self, job: Any) -> tuple[Path, Path]:
        directory = job.output / "work"
        return directory / "live-source.mp4", directory / "live-source.json"

    def _proxy_ready(self, job: Any) -> bool:
        proxy, manifest = self._proxy_paths(job)
        if not proxy.is_file() or not manifest.is_file():
            return False
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        source = Path(str((job.result or {}).get("source") or job.source))
        return str(payload.get("fingerprint") or "") == self._fingerprint(source)

    def status(self, job: Any, *, height: int = 0) -> LiveSourceState:
        source = Path(
            str((job.options or {}).get("source") or job.source)
        ).expanduser()
        with self._lock:
            state = self._states.get(str(job.job_id))
            if state and state.status in {"preparing", "failed"}:
                return state
        if not source.is_file():
            return LiveSourceState(status="failed", reason="source media is offline")
        if not height:
            try:
                height = int((job.result or {}).get("media", {}).get("height") or 0)
            except (TypeError, ValueError):
                height = 0
        compatible, reason = self._probe(source, height)
        if compatible:
            return LiveSourceState(
                status="ready",
                url=f"/api/v1/jobs/{job.job_id}/source/file",
                reason=reason,
                path=str(source),
            )
        if self._proxy_ready(job):
            proxy, _ = self._proxy_paths(job)
            return LiveSourceState(
                status="ready",
                url=f"/api/v1/jobs/{job.job_id}/live-source/file",
                reason="using a browser-safe H.264/AAC proxy",
                path=str(proxy),
            )
        return LiveSourceState(status="missing", reason=reason)

    def start(self, job: Any, *, height: int = 0) -> LiveSourceState:
        state = self.status(job, height=height)
        if state.status == "ready":
            return state
        if state.status == "preparing":
            return state
        with self._lock:
            existing = self._states.get(str(job.job_id))
            if existing and existing.status == "preparing":
                return existing
            state = LiveSourceState(
                status="preparing",
                reason=state.reason or "building a browser-safe proxy",
                started_at=self._now(),
            )
            self._states[str(job.job_id)] = state
            thread = threading.Thread(
                target=self._build,
                args=(job,),
                name=f"videoflow-live-source-{job.job_id}",
                daemon=True,
            )
            self._threads[str(job.job_id)] = thread
            thread.start()
        return state

    def _build(self, job: Any) -> None:
        state = self._states[str(job.job_id)]
        proxy, manifest = self._proxy_paths(job)
        proxy.parent.mkdir(parents=True, exist_ok=True)
        temporary = proxy.with_name(f".{proxy.name}.part.mp4")
        source = Path(str((job.options or {}).get("source") or job.source))
        try:
            adapter = FFmpegAdapter()
            adapter.render(
                [
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-vf",
                    "scale=w='min(1280,iw)':h=-2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "160k",
                    "-movflags",
                    "+faststart",
                    str(temporary),
                ],
                timeout=3600,
            )
            os.replace(temporary, proxy)
            manifest.write_text(
                json.dumps(
                    {
                        "fingerprint": self._fingerprint(source),
                        "built_at": self._now(),
                        "source": str(source),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            state.status = "ready"
            state.url = f"/api/v1/jobs/{job.job_id}/live-source/file"
            state.reason = "browser-safe H.264/AAC proxy ready"
            state.path = str(proxy)
            state.finished_at = self._now()
        except Exception as exc:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
            state.status = "failed"
            state.error = str(exc)
            state.reason = "could not build the browser-safe proxy"
            state.finished_at = self._now()
        finally:
            with self._lock:
                self._threads.pop(str(job.job_id), None)

    def file(self, job: Any, *, height: int = 0) -> Path | None:
        state = self.status(job, height=height)
        if state.status != "ready":
            return None
        path = Path(state.path) if state.path else None
        if path is not None and path.is_file():
            return path
        return None


live_sources = LiveSourceManager()
