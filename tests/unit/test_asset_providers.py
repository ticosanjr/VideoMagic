from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from videoflow.application.asset_providers import (
    AssetCandidate,
    classify_license,
    download_asset,
    license_blockers,
    mark_approved,
    search_assets,
    write_ledger,
)
from videoflow.application.asset_providers.download import (
    _clip_bounds,
    _download_http,
    _download_youtube,
)
from videoflow.application.settings import AppSettings
from videoflow.domain.errors import CapabilityUnavailableError, IngestError


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
        "videoflow.application.asset_providers.search.httpx.get",
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
        "videoflow.application.asset_providers.download._download_http", fake_download
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
        "videoflow.application.asset_providers.download._download_youtube", fake_download
    )
    result = download_asset(
        candidate, tmp_path / "clip.mp4", settings=AppSettings(), clip_seconds=15
    )
    assert result.clip_start_sec == 60.0
    assert result.clip_end_sec == 75.0
    assert result.sha256


def test_clip_bounds_for_youtube_candidates() -> None:
    youtube = _candidate(provider="youtube", duration_sec=600)
    assert _clip_bounds(youtube, 15) == (60.0, 75.0)
    assert _clip_bounds(_candidate(provider="pexels"), 15) == (0.0, 0.0)
    assert _clip_bounds(_candidate(provider="youtube", duration_sec=10), 15) == (
        0.0,
        10.0,
    )
    assert _clip_bounds(_candidate(provider="youtube", duration_sec=0), 15) == (
        0.0,
        15.0,
    )
    explicit = _candidate(provider="youtube", duration_sec=100, clip_start_sec=99)
    assert _clip_bounds(explicit, 15) == (85.0, 100.0)


class _StreamResponse:
    def __init__(self, status_code=200, chunks=(b"video",)) -> None:
        self.status_code = status_code
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def iter_bytes(self):
        yield from self._chunks


def test_download_http_writes_atomically(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.assert_public_url",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.ensure_external_allowed",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.httpx.stream",
        lambda *args, **kwargs: _StreamResponse(),
    )
    target = tmp_path / "nested" / "clip.mp4"
    result = _download_http(
        "https://cdn.example.com/clip.mp4",
        target,
        settings=AppSettings(),
        allow_external_services=True,
        allowed_external_hosts=(),
    )
    assert result == target
    assert target.read_bytes() == b"video"
    assert not target.with_name("clip.mp4.part").exists()


def test_download_http_rejects_http_errors(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.assert_public_url",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.ensure_external_allowed",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.httpx.stream",
        lambda *args, **kwargs: _StreamResponse(status_code=404),
    )
    with pytest.raises(IngestError, match="HTTP 404"):
        _download_http(
            "https://cdn.example.com/clip.mp4",
            tmp_path / "clip.mp4",
            settings=AppSettings(),
            allow_external_services=True,
            allowed_external_hosts=(),
        )


def test_download_http_enforces_the_size_limit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.assert_public_url",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.ensure_external_allowed",
        lambda *args, **kwargs: None,
    )

    class Huge(bytes):
        def __len__(self) -> int:
            return 2 * 1024 * 1024 * 1024 + 1

    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.httpx.stream",
        lambda *args, **kwargs: _StreamResponse(chunks=(Huge(b"x"),)),
    )
    with pytest.raises(IngestError, match="2 GB"):
        _download_http(
            "https://cdn.example.com/clip.mp4",
            tmp_path / "clip.mp4",
            settings=AppSettings(),
            allow_external_services=True,
            allowed_external_hosts=(),
        )


def test_download_youtube_runs_ytdlp(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(str(tmp_path / "clip.mp4")).write_bytes(b"excerpt")
        return type("Completed", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.find_binary",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else "/usr/bin/yt-dlp",
    )
    monkeypatch.setattr("videoflow.application.asset_providers.download.subprocess.run", fake_run)
    candidate = _candidate(
        provider="youtube",
        duration_sec=600,
        page_url="https://www.youtube.com/watch?v=abc",
    )
    path, start, end = _download_youtube(
        candidate,
        tmp_path / "clip.mp4",
        settings=AppSettings(),
        allow_external_services=True,
        allowed_external_hosts=(),
        clip_seconds=15,
    )
    assert path == tmp_path / "clip.mp4"
    assert (start, end) == (60.0, 75.0)
    assert "--ffmpeg-location" in calls[0]
    assert calls[0][-1] == "https://www.youtube.com/watch?v=abc"


def test_download_youtube_reports_failures(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.find_binary",
        lambda name: "/usr/bin/yt-dlp",
    )
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.subprocess.run",
        lambda *args, **kwargs: type("Completed", (), {"returncode": 1, "stderr": "boom"})(),
    )
    with pytest.raises(IngestError, match="boom"):
        _download_youtube(
            _candidate(provider="youtube"),
            tmp_path / "clip.mp4",
            settings=AppSettings(),
            allow_external_services=True,
            allowed_external_hosts=(),
            clip_seconds=15,
        )

    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.subprocess.run",
        lambda *args, **kwargs: type("Completed", (), {"returncode": 0, "stderr": ""})(),
    )
    with pytest.raises(IngestError, match="without a media file"):
        _download_youtube(
            _candidate(provider="youtube"),
            tmp_path / "missing.mp4",
            settings=AppSettings(),
            allow_external_services=True,
            allowed_external_hosts=(),
            clip_seconds=15,
        )


def test_download_youtube_requires_ytdlp(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "videoflow.application.asset_providers.download.find_binary", lambda name: None
    )
    with pytest.raises(CapabilityUnavailableError):
        _download_youtube(
            _candidate(provider="youtube"),
            tmp_path / "clip.mp4",
            settings=AppSettings(),
            allow_external_services=True,
            allowed_external_hosts=(),
            clip_seconds=15,
        )


def test_workspace_asset_license_blocks_export(tmp_path: Path, monkeypatch) -> None:
    from vf_contracts.assets import write_asset
    from vf_contracts.workspace import ensure_project

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    output = tmp_path / "out"
    output.mkdir()
    project_id = "11111111-1111-1111-1111-111111111111"
    ensure_project(project_id, name="License", output=str(output))
    (output / "project.json").write_text(json.dumps({"project_id": project_id}), encoding="utf-8")
    write_asset(
        project_id,
        "broll",
        b"asset",
        {"license": "unknown", "source": "stock", "ext": ".mp4"},
    )
    blockers = license_blockers(output)
    assert len(blockers) == 1
    assert blockers[0]["license_status"] == "unknown"
    write_asset(
        project_id,
        "broll",
        b"safe",
        {"license": "cc0", "source": "local", "ext": ".mp4"},
    )
    assert len(license_blockers(output)) == 1


def test_license_expiry_parser_edges() -> None:
    from videoflow.application.asset_providers.ledger import _expired

    assert _expired("not-a-date") is False
    assert _expired("2020-01-01T00:00:00") is True


def test_workspace_fair_use_asset_blocks(tmp_path: Path, monkeypatch) -> None:
    from vf_contracts.assets import write_asset
    from vf_contracts.workspace import ensure_project

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home-fair"))
    output = tmp_path / "out-fair"
    output.mkdir()
    project_id = "22222222-2222-2222-2222-222222222222"
    ensure_project(project_id, name="Fair", output=str(output))
    (output / "project.json").write_text(json.dumps({"project_id": project_id}), encoding="utf-8")
    write_asset(
        project_id,
        "broll",
        b"fair",
        {"license": "youtube_fair_use", "source": "youtube", "ext": ".mp4"},
    )
    blockers = license_blockers(output)
    assert blockers[0]["license_status"] == "fair_use_review"
