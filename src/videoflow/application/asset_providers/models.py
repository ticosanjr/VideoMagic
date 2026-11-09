"""Normalized asset candidates and license classification."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

_LICENSE_CC0 = {"cc0", "public domain", "publicdomain", "pdm", "no known copyright"}
_LICENSE_FAIR = {"fair use", "fairuse", "youtube standard license"}


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
