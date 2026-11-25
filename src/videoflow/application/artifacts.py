"""Project artifact discovery and safe binary access for the agent surface."""

from __future__ import annotations

import contextlib
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from videoflow.domain.errors import ProjectStateError

_TEXT = {".json", ".txt", ".md", ".srt", ".ass", ".xml", ".fcpxml", ".kdenlive", ".edl"}
_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

_ARTIFACT_DIRS = (
    "exports",
    "shorts",
    "thumbnails",
    "motion",
    "audio",
    "research",
    "storyboard",
    "work/qa",
    "work/preview",
    "preview",
    "broll",
    "delivery",
    "beat_map.json",
    "run.json",
    "shorts.json",
    "project_state.json",
    "job.log",
)


def _kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _IMAGE:
        return "image"
    if suffix in _AUDIO:
        return "audio"
    if suffix in _VIDEO:
        return "video"
    if suffix in _TEXT:
        return "text"
    return "file"


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _relative(output: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(output.resolve()).as_posix()
    except ValueError:
        return path.name


def artifact_id(output: Path, path: Path) -> str:
    return hashlib.sha256(_relative(output, path).encode("utf-8")).hexdigest()[:16]


def list_artifacts(output: Path, *, include_hash: bool = False) -> list[dict[str, Any]]:
    output = Path(output).expanduser()
    output_resolved = output.resolve()
    seen: set[Path] = set()
    items: list[dict[str, Any]] = []
    for entry in _ARTIFACT_DIRS:
        target = output / entry
        candidates = [target] if target.is_file() else []
        if target.is_dir():
            candidates.extend(
                path
                for path in target.rglob("*")
                if path.is_file() and path.name not in {".DS_Store"}
            )
        for path in sorted(candidates):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                relative = resolved.relative_to(output_resolved).as_posix()
            except ValueError:
                relative = path.name
            stat_result = path.stat()
            metadata: dict[str, Any] = {
                "artifact_id": hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16],
                "path": str(path),
                "relative_path": relative,
                "kind": _kind(path),
                "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "size_bytes": stat_result.st_size,
                "name": path.name,
            }
            if include_hash and stat_result.st_size <= 512 * 1024 * 1024:
                metadata["sha256"] = _digest(path)
            items.append(metadata)
    return items


def find_artifact(output: Path, selector: str) -> Path:
    output = Path(output).expanduser()
    selector = selector.strip()
    if not selector:
        raise ProjectStateError("Artifact selector is required")
    direct = Path(selector)
    candidates = [direct] if direct.is_absolute() else [output / selector]
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve().is_relative_to(output.resolve()):
            return candidate
    for item in list_artifacts(output):
        if selector in {str(item["artifact_id"]), str(item["relative_path"]), str(item["name"])}:
            path = Path(str(item["path"]))
            if path.is_file() and path.resolve().is_relative_to(output.resolve()):
                return path
    raise ProjectStateError(f"Unknown artifact: {selector}")


def artifact_payload(output: Path, path: Path) -> dict[str, Any]:
    metadata = {
        "artifact_id": artifact_id(output, path),
        "path": str(path),
        "relative_path": _relative(output, path),
        "kind": _kind(path),
        "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "size_bytes": path.stat().st_size,
        "sha256": _digest(path),
    }
    if metadata["kind"] == "text":
        with contextlib.suppress(OSError):
            metadata["text"] = path.read_text(encoding="utf-8", errors="replace")[:200_000]
    return metadata


def qa_artifacts(output: Path) -> dict[str, Any]:
    """Collect visual/safe-zone reports and failed frame paths."""

    output = Path(output).expanduser()
    defects: list[dict[str, Any]] = []
    reports: dict[str, Any] = {}
    for relative in ("work/qa/qa_report.json", "work/qa/safezone.json"):
        path = output / relative
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            payload = {"error": "unreadable"}
        reports[path.stem] = payload
        if isinstance(payload, dict):
            raw_defects = payload.get("defects")
            defect_rows = raw_defects if isinstance(raw_defects, list) else []
            for item in defect_rows:
                if isinstance(item, dict):
                    defects.append(dict(item))
            for item in (
                payload.get("collisions", []) if isinstance(payload.get("collisions"), list) else []
            ):
                if isinstance(item, dict):
                    defects.append({"kind": "safezone", **item})
    qa_root = output / "exports" / "qa"
    if qa_root.is_dir():
        for path in sorted(qa_root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                payload = {"error": "unreadable"}
            reports[path.stem] = payload
            if isinstance(payload, dict):
                raw_defects = payload.get("defects")
                defect_rows = raw_defects if isinstance(raw_defects, list) else []
                for item in defect_rows:
                    if isinstance(item, dict):
                        defects.append(dict(item))
                raw_issues = payload.get("issues")
                issue_rows = raw_issues if isinstance(raw_issues, list) else []
                for item in issue_rows:
                    if isinstance(item, dict):
                        defects.append(dict(item))

    frames: list[dict[str, Any]] = []
    for directory in (output / "work" / "qa", output / "qa"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _IMAGE:
                continue
            frames.append(
                {
                    "artifact_id": artifact_id(output, path),
                    "path": str(path),
                    "relative_path": _relative(output, path),
                    "kind": "image",
                    "mime_type": mimetypes.guess_type(path.name)[0] or "image/jpeg",
                    "size_bytes": path.stat().st_size,
                }
            )
    return {"defects": defects, "reports": reports, "frames": frames}
