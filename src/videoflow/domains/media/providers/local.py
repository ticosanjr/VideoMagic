"""Local SFX directory provider."""

# ruff: noqa: F405

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..errors import (
    ProviderUnavailableError,
)
from .base import *  # noqa: F401,F403,F405
from .video import find_media_files


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
