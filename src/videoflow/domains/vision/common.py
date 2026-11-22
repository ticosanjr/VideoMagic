"""Shared constants, probes and payload helpers for the vision domain."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import commands, storage
from .errors import (
    InputNotFoundError,
    InvalidArgumentError,
    MissingCommandError,
    OutputNotProducedError,
    RemoteResultError,
)
from .router import RouterBridge

ROUTER = RouterBridge()
MOTION_ENGINES = {"remotion", "manim", "ffmpeg", "html", "hyperframes"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MOTIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right"}
BROLL_ASPECTS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "3:4": (1080, 1440),
    "2:3": (1080, 1620),
    "1:1": (1080, 1080),
}


def _ffprobe() -> str:
    configured = os.environ.get("VF_FFPROBE")
    if configured:
        return configured
    found = shutil.which("ffprobe")
    if found:
        return found
    raise MissingCommandError(
        "ffprobe is required for upscale validation",
        details={"env": ["VF_FFPROBE"], "executable": "ffprobe"},
    )


def _probe_stream(path: Path) -> dict[str, float]:
    try:
        probe = _ffprobe()
        result = commands.run(
            [
                probe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate",
                "-of",
                "default=noprint_wrappers=1",
                str(path),
            ]
        )
    except Exception:  # noqa: BLE001 - probe is advisory
        return {}
    values: dict[str, float] = {}
    for line in result.stdout.splitlines():
        key, _, raw = line.partition("=")
        if key in {"width", "height"}:
            try:
                values[key] = float(int(raw))
            except ValueError:
                continue
        elif key == "r_frame_rate" and "/" in raw:
            numerator, denominator = raw.split("/", 1)
            try:
                values["fps"] = float(numerator) / max(1e-9, float(denominator))
            except ValueError:
                continue
    return values


def _materialize_remote(
    *,
    project_id: str,
    relative_path: str,
    result: Any,
    capability: str,
    cache_key: str,
    kind: str,
) -> storage.AssetRecord:
    metadata: dict[str, Any] = {"capability": capability, "mode": "remote"}
    if isinstance(result, dict) and isinstance(result.get("metadata"), dict):
        metadata.update(result["metadata"])

    data: bytes | None = None
    if isinstance(result, dict) and result.get("data") is not None:
        raw = result["data"]
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    elif isinstance(result, (bytes, bytearray)):
        data = bytes(result)

    if data is not None:
        return storage.write_output(
            project_id,
            relative_path,
            data=data,
            kind=kind,
            license="generated",
            source=f"remote:{capability}",
            cache_key=cache_key,
            metadata=metadata,
            ai_generated=True,
        )

    source = _path_from_value(result)
    if source is None or not source.is_file():
        raise RemoteResultError(
            f"remote {capability!r} result has no readable file",
            details={"capability": capability, "result_type": type(result).__name__},
        )
    return storage.write_output(
        project_id,
        relative_path,
        source_path=source,
        kind=kind,
        license="generated",
        source=f"remote:{capability}",
        cache_key=cache_key,
        metadata=metadata,
        ai_generated=True,
    )


def _path_from_value(value: Any) -> Path | None:
    if isinstance(value, (str, Path)):
        return Path(str(value)).expanduser()
    if isinstance(value, dict):
        for key in ("path", "output", "asset_path", "file"):
            if value.get(key):
                return Path(str(value[key])).expanduser()
        return None
    for attribute in ("path", "output", "file"):
        raw = getattr(value, attribute, None)
        if raw:
            return Path(str(raw)).expanduser()
    return None


def _payload(
    tool: str,
    project_id: str,
    record: storage.AssetRecord,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "output": str(record.path),
        "relative_path": record.relative_path,
        "cache_key": record.cache_key,
        "cached": record.cached,
        "sidecar": str(record.sidecar),
        "license": record.license,
        "source": record.source,
        "sha256": record.sha256,
    }
    payload.update(extra)
    return payload


def _assets_payload(
    tool: str,
    project_id: str,
    records: Sequence[storage.AssetRecord],
    *,
    mode: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "mode": mode,
        "cached": all(record.cached for record in records),
        "assets": [_payload(tool, project_id, record, mode=mode) for record in records],
    }


def _ensure_input(value: str | Path | None, argument: str) -> Path:
    if value is None or str(value) == "":
        raise InvalidArgumentError(f"{argument} is required", details={"argument": argument})
    resolved = Path(value).expanduser()
    if not resolved.is_file():
        raise InputNotFoundError(
            f"{argument} not found: {resolved}",
            details={"argument": argument, "path": str(resolved)},
        )
    return resolved


def _require_output(path: Path) -> None:
    if not path.is_file():
        raise OutputNotProducedError(
            f"command did not produce {path}",
            details={"path": str(path)},
        )


def _assert_alpha(path: Path) -> None:
    """Fail when a rendered "alpha" intermediate lost its alpha plane."""

    try:
        completed = subprocess.run(
            [
                _ffprobe(),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=pix_fmt:stream_tags=alpha_mode",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        payload = json.loads(completed.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
    except Exception:  # noqa: BLE001 - probe is advisory for exotic codecs
        return
    pix_fmt = str(stream.get("pix_fmt") or "")
    alpha_mode = str((stream.get("tags") or {}).get("alpha_mode") or "")
    has_alpha = pix_fmt.startswith(("yuva", "rgba", "bgra", "argb", "abgr")) or alpha_mode == "1"
    if not has_alpha:
        path.unlink(missing_ok=True)
        raise OutputNotProducedError(
            "alpha_channel_missing: rendered graphic has no alpha plane",
            details={"path": str(path), "pix_fmt": pix_fmt},
        )


def _ffmpeg() -> str:
    configured = os.environ.get("VF_FFMPEG")
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise MissingCommandError(
        "ffmpeg is required for this tool; install it or set VF_FFMPEG",
        details={"env": ["VF_FFMPEG"], "executable": "ffmpeg"},
    )


def _slug(value: str, *, limit: int = 40) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value.lower())
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return (collapsed or "asset")[:limit]


def _is_screen_target(value: str) -> bool:
    text = value.strip().lower()
    return text in {"screen", "desktop", "display"} or text.startswith("screen:")


def _is_css_selector(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    if raw.startswith(("#", ".", "[", "*", ":")):
        return True
    return bool(re.search(r"[>\s]", raw)) or bool(re.search(r"[A-Za-z]", raw))


def _crop_filter(selector: str, width: int, height: int) -> str:
    """Interpret ``x,y,w,h`` as a crop; keep CSS selectors in metadata."""

    raw = str(selector or "").strip()
    if not raw:
        return ""
    parts = [part for part in re.split(r"[x,\s]+", raw) if part]
    if len(parts) == 4:
        try:
            x, y, w, h = (int(part) for part in parts)
        except ValueError:
            return ""
        if w > 0 and h > 0:
            return f"crop={min(w, width)}:{min(h, height)}:{max(0, x)}:{max(0, y)}"
    return ""


def _validate_fps(value: str) -> None:
    try:
        fps = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            f"VF_MATTE_FPS must be a number, got {value!r}",
            details={"env": "VF_MATTE_FPS", "value": value},
        ) from exc
    if not 1.0 <= fps <= 240.0:
        raise InvalidArgumentError(
            f"VF_MATTE_FPS must be between 1 and 240, got {value!r}",
            details={"env": "VF_MATTE_FPS", "value": value},
        )
