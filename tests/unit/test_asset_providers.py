from __future__ import annotations

import hashlib
import json
from pathlib import Path

from videoflow.application.asset_providers import (
    AssetCandidate,
    classify_license,
    download_asset,
    license_blockers,
    mark_approved,
    search_assets,
    write_ledger,
)
from videoflow.application.settings import AppSettings


def _candidate(**overrides) -> AssetCandidate:
    payload = {
        "asset_id": "pexels-abc",
        "provider": "pexels",
        "title": "A clip",
        "page_url": "https://pexels.com/video/1",
        "download_url": "https://cdn.example.com/clip.mp4",
        "kind": "video",
        "license": "Pexels License",
        "license_status": "cleared",
        "allowed_commercial": True,
        "attribution_required": False,
    }
    payload.update(overrides)
    return AssetCandidate(**payload)


def test_license_classification() -> None:
    assert classify_license("Pexels License", provider="pexels")[0] == "cleared"
    assert classify_license("Pixabay Content License", provider="pixabay")[0] == "cleared"
    assert classify_license("CC0")[0] == "cleared"
    assert classify_license("CC BY-SA 4.0")[0] == "cc_review"
    assert classify_license("YouTube Standard License", provider="youtube")[0] == "fair_use_review"
    assert classify_license("")[0] == "unknown"


def test_ledger_blocks_and_approval(tmp_path: Path) -> None:
    output = tmp_path / "out"
    fair = _candidate(
        asset_id="yt-1",
        provider="youtube",
        title="Excerpt",
        license="YouTube Standard License",
        license_status="fair_use_review",
        allowed_commercial=False,
    )
    path = write_ledger(output, [fair])
    payload = json.loads(path.read_text())
    assert payload["blockers"]
    assert len(license_blockers(output)) == 1
    mark_approved(output, approval_id="hilt-assets", reviewer="editor")
    assert license_blockers(output) == []
    assert json.loads(path.read_text())["assets"][0]["approved"] is True


def test_pexels_search_returns_license_metadata(monkeypatch) -> None:
    class Response:
        status_code = 200

        def json(self):
            return {
                "videos": [
                    {
                        "url": "https://www.pexels.com/video/1/",
                        "duration": 12,
                        "user": {"name": "Creator"},
                        "video_files": [
                            {
                                "link": "https://cdn.example.com/clip.mp4",
                                "width": 1280,
                                "height": 720,
                            }
                        ],
                    }
                ]
            }

    monkeypatch.setenv("PEXELS_API_KEY", "key")
    monkeypatch.setattr(
        "videoflow.application.asset_providers.httpx.get",
        lambda *args, **kwargs: Response(),
    )
    results = search_assets(
        "evidence",
        providers=["pexels"],
        settings=AppSettings(),
        limit=1,
        allow_external_services=True,
    )
    assert results[0].provider == "pexels"
    assert results[0].license_status == "cleared"
    assert results[0].download_url.endswith(".mp4")


def test_download_hashes_the_file(monkeypatch, tmp_path: Path) -> None:
    candidate = _candidate()
    target = tmp_path / "clip.mp4"

    def fake_download(url, destination, **kwargs):
        Path(destination).write_bytes(b"video")
        return Path(destination)

    monkeypatch.setattr(
        "videoflow.application.asset_providers._download_http", fake_download
    )
    result = download_asset(candidate, target, settings=AppSettings(), clip_seconds=15)
    assert result.downloaded_path == str(target)
    assert result.sha256 == hashlib.sha256(b"video").hexdigest()


def test_youtube_clip_is_short(monkeypatch, tmp_path: Path) -> None:
    candidate = _candidate(
        asset_id="yt-1",
        provider="youtube",
        title="Excerpt",
        page_url="https://www.youtube.com/watch?v=abc",
        download_url="https://www.youtube.com/watch?v=abc",
        license="YouTube Standard License",
        license_status="fair_use_review",
        duration_sec=600,
    )

    def fake_download(candidate, destination, **kwargs):
        Path(destination).write_bytes(b"clip")
        return Path(destination), 60.0, 75.0

    monkeypatch.setattr(
        "videoflow.application.asset_providers._download_youtube", fake_download
    )
    result = download_asset(
        candidate, tmp_path / "clip.mp4", settings=AppSettings(), clip_seconds=15
    )
    assert result.clip_start_sec == 60.0
    assert result.clip_end_sec == 75.0
    assert result.sha256
