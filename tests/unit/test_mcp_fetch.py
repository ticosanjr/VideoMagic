"""Unit tests for the isolated VideoFlow 2.90 fetch MCP package."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

PACKAGES = Path(__file__).resolve().parents[2] / "packages"
for package_source in (PACKAGES / "vf-contracts" / "src", PACKAGES / "mcp-fetch" / "src"):
    if str(package_source) not in sys.path:
        sys.path.insert(0, str(package_source))

from mcp_fetch.errors import (  # noqa: E402
    ProviderUnavailableError,
    UrlNotAllowedError,
)
from mcp_fetch.server import FetchService, build_server  # noqa: E402

from videoflow.domains.media import providers  # noqa: E402

PEXELS_VIDEO = {
    "videos": [
        {
            "id": 101,
            "width": 1920,
            "height": 1080,
            "duration": 12,
            "fps": 25,
            "url": "https://www.pexels.com/video/101/",
            "user": {"name": "Ada Creator"},
            "video_files": [
                {
                    "id": 1,
                    "quality": "sd",
                    "file_type": "video/mp4",
                    "width": 960,
                    "height": 540,
                    "link": "https://cdn.example.test/videos/101-sd.mp4",
                },
                {
                    "id": 2,
                    "quality": "hd",
                    "file_type": "video/mp4",
                    "width": 1920,
                    "height": 1080,
                    "link": "https://cdn.example.test/videos/101-hd.mp4",
                },
            ],
        },
        {
            "id": 102,
            "width": 1920,
            "height": 1080,
            "duration": 2,
            "url": "https://www.pexels.com/video/102/",
            "user": {"name": "Too Short"},
            "video_files": [
                {
                    "id": 3,
                    "quality": "hd",
                    "file_type": "video/mp4",
                    "width": 1920,
                    "height": 1080,
                    "link": "https://cdn.example.test/videos/102-hd.mp4",
                }
            ],
        },
    ]
}

PEXELS_IMAGES = {
    "photos": [
        {
            "id": 201,
            "width": 1920,
            "height": 1080,
            "url": "https://www.pexels.com/photo/201/",
            "photographer": "Grace Shooter",
            "src": {
                "original": "https://cdn.example.test/photos/201.jpg",
                "large2x": "https://cdn.example.test/photos/201-large.jpg",
            },
        }
    ]
}


def pexels_transport(
    requests: list[httpx.Request],
    *,
    media: bytes = b"asset-bytes",
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "api.pexels.com" and request.url.path == "/videos/search":
            assert request.headers["authorization"] == "test-pexels-key"
            return httpx.Response(200, json=PEXELS_VIDEO)
        if request.url.host == "api.pexels.com" and request.url.path == "/v1/search":
            assert request.headers["authorization"] == "test-pexels-key"
            return httpx.Response(200, json=PEXELS_IMAGES)
        if request.url.host == "cdn.example.test":
            return httpx.Response(200, content=media)
        return httpx.Response(404, json={"error": "unexpected"})

    return httpx.MockTransport(handler)


def make_service(
    tmp_path: Path,
    requests: list[httpx.Request],
    *,
    env: dict[str, str] | None = None,
    media: bytes = b"asset-bytes",
) -> FetchService:
    return FetchService(
        workspace_root=tmp_path,
        transport=pexels_transport(requests, media=media),
        env=env if env is not None else {"PEXELS_API_KEY": "test-pexels-key"},
    )


def test_fetch_stock_broll_downloads_metadata_and_license_sidecar(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    service = make_service(tmp_path, requests)

    result = service.fetch_stock_broll("project-1", "city skyline", min_duration=4)

    assert result["ok"] is True
    assert result["provider"] == "pexels"
    assert result["cached"] is False
    assert len(result["assets"]) == 1
    asset = result["assets"][0]
    path = Path(asset["path"])
    assert path.is_absolute()
    assert path.is_file()
    assert path.read_bytes() == b"asset-bytes"
    assert path.parent == (tmp_path / "projects" / "project-1" / "assets" / "broll").resolve()
    assert asset["kind"] == "broll"
    assert asset["metadata"]["duration"] == 12
    assert asset["metadata"]["provider"] == "pexels"
    assert asset["metadata"]["query"] == "city skyline"
    assert asset["metadata"]["sha256"]

    sidecar = Path(asset["sidecar"])
    assert sidecar.is_file()
    assert sidecar.name.endswith(".meta.json")
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["path"] == f"assets/broll/{path.name}"
    assert sidecar_payload["license"] == "pexels"
    assert sidecar_payload["provider"] == "pexels"
    assert sidecar_payload["params_hash"]

    metadata_sidecar = Path(asset["metadata_sidecar"])
    assert metadata_sidecar.is_file()
    metadata_payload = json.loads(metadata_sidecar.read_text(encoding="utf-8"))
    assert metadata_payload["id"] == 101
    assert metadata_payload["query"] == "city skyline"

    license_sidecar = Path(asset["license_sidecar"])
    assert license_sidecar.is_file()
    license_payload = json.loads(license_sidecar.read_text(encoding="utf-8"))
    assert license_payload["provider"] == "pexels"
    assert license_payload["license"] == "Pexels License"
    assert license_payload["status"] == "cleared"
    assert license_payload["license_url"] == "https://www.pexels.com/license/"


def test_fetch_stock_images_uses_pexels_and_writes_image_asset(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    service = make_service(tmp_path, requests, media=b"jpeg-data")

    result = service.fetch_stock_images("project-1", "interview b-roll", count=2)

    assert result["provider"] == "pexels"
    asset = result["assets"][0]
    path = Path(asset["path"])
    assert path.read_bytes() == b"jpeg-data"
    assert path.parent == (tmp_path / "projects" / "project-1" / "assets" / "images").resolve()
    assert asset["kind"] == "images"
    assert asset["metadata"]["creator"] == "Grace Shooter"
    license_payload = json.loads(Path(asset["license_sidecar"]).read_text(encoding="utf-8"))
    assert license_payload["status"] == "cleared"
    assert license_payload["license"] == "Pexels License"
    assert any(request.url.path == "/v1/search" for request in requests)


def test_repeated_request_reuses_cached_asset_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[httpx.Request] = []
    service = make_service(tmp_path, requests)

    first = service.fetch_stock_broll("project-1", "ocean waves")
    request_count = len(requests)
    manifest_files = list((tmp_path / "projects" / "project-1" / ".cache").glob("*.json"))
    assert len(manifest_files) == 1
    key = json.loads(manifest_files[0].read_text(encoding="utf-8"))["idempotency_key"]

    monkeypatch.setenv("VF_WORKSPACE_ROOT", str(tmp_path))
    contracts_src = PACKAGES / "vf-contracts" / "src"
    if contracts_src.is_dir():
        from vf_shared.contracts.assets import find_cached

        record = find_cached("project-1", "broll", key)
        assert record is not None
        assert (tmp_path / "projects" / "project-1" / record.path).is_file()
        assert record.params_hash == key

    # The contract sidecar alone is enough to reuse the asset.
    manifest_files[0].unlink()
    second = service.fetch_stock_broll("project-1", "ocean waves")

    assert len(requests) == request_count
    assert second["cached"] is True
    assert second["assets"] == [
        {**first["assets"][0], "cached": True},
    ]


def test_rip_video_segment_builds_yt_dlp_command_without_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((command, kwargs))
        template = command[command.index("-o") + 1]
        destination = Path(template).parent
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "clip.mp4").write_bytes(b"segment")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(providers.video.subprocess, "run", fake_run)
    service = FetchService(workspace_root=tmp_path, env={})

    result = service.rip_video_segment(
        "project-1",
        "https://www.youtube.com/watch?v=abc123",
        1.5,
        4.25,
        max_height=720,
    )

    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[0] == "yt-dlp"
    assert command[-1] == "https://www.youtube.com/watch?v=abc123"
    assert "--download-sections" in command
    assert command[command.index("--download-sections") + 1] == "*00:00:01.500-00:00:04.250"
    assert "--force-keyframes-at-cuts" in command
    assert "bv*[height<=720]+ba/b[height<=720]/b" in command
    assert kwargs["shell"] is False
    assert command == [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "--no-progress",
        "--force-keyframes-at-cuts",
        "--download-sections",
        "*00:00:01.500-00:00:04.250",
        "-o",
        command[command.index("-o") + 1],
        "-f",
        "bv*[height<=720]+ba/b[height<=720]/b",
        "https://www.youtube.com/watch?v=abc123",
    ]

    asset = result["assets"][0]
    path = Path(asset["path"])
    assert path.read_bytes() == b"segment"
    assert path.parent == (tmp_path / "projects" / "project-1" / "assets" / "broll").resolve()
    license_payload = json.loads(Path(asset["license_sidecar"]).read_text(encoding="utf-8"))
    assert license_payload["status"] == "fair_use_review"
    assert license_payload["attribution_required"] is True


def test_rip_video_segment_rejects_non_http_and_disallowed_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def fake_run(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        nonlocal called
        called = True
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(providers.video.shutil, "which", lambda _binary: "/usr/bin/yt-dlp")
    monkeypatch.setattr(providers.video.subprocess, "run", fake_run)

    with pytest.raises(UrlNotAllowedError):
        FetchService(workspace_root=tmp_path, env={}).rip_video_segment(
            "project-1", "file:///etc/passwd", 0, 2
        )

    restricted = FetchService(
        workspace_root=tmp_path,
        env={"VF_ALLOWED_EXTERNAL_HOSTS": "youtube.com"},
    )
    with pytest.raises(UrlNotAllowedError):
        restricted.rip_video_segment("project-1", "https://evil.example.test/clip", 0, 2)
    assert called is False


def test_fetch_sfx_uses_local_provider_directory(tmp_path: Path) -> None:
    sfx_dir = tmp_path / "sfx-library"
    sfx_dir.mkdir()
    source = sfx_dir / "whoosh-hit.wav"
    source.write_bytes(b"RIFF-localsfx")
    (sfx_dir / "whoosh-hit.wav.json").write_text(
        json.dumps(
            {
                "license": "CC0 1.0",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "status": "cleared",
                "duration": 1.2,
            }
        ),
        encoding="utf-8",
    )
    service = FetchService(
        workspace_root=tmp_path,
        env={"VF_SFX_DIR": str(sfx_dir)},
    )

    result = service.fetch_sfx("project-1", "whoosh", license_filter="cc0")

    assert result["provider"] == "local"
    asset = result["assets"][0]
    path = Path(asset["path"])
    assert path.read_bytes() == b"RIFF-localsfx"
    assert path.parent == (tmp_path / "projects" / "project-1" / "assets" / "sfx").resolve()
    assert source.is_file(), "local provider must copy, never move, the source"
    license_payload = json.loads(Path(asset["license_sidecar"]).read_text(encoding="utf-8"))
    assert license_payload["license"] == "CC0 1.0"
    assert license_payload["status"] == "cleared"


def test_keyless_images_report_typed_error_when_gallery_dl_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise ProviderUnavailableError("keyless provider unavailable")

    monkeypatch.setattr("mcp_fetch.server.OpenverseClient", unavailable)
    monkeypatch.setattr("mcp_fetch.server.WikimediaClient", unavailable)
    service = FetchService(
        workspace_root=tmp_path,
        env={},
        gallery_dl_binary="vf-missing-gallery-dl",
    )

    with pytest.raises(ProviderUnavailableError, match="gallery-dl"):
        service.fetch_stock_images("project-1", "https://images.example.test/cat.jpg")


def test_build_server_registers_the_four_tools(tmp_path: Path) -> None:
    service = FetchService(workspace_root=tmp_path, env={})
    server = build_server(service)

    tools = asyncio.run(server.list_tools())

    assert {tool.name for tool in tools} == {
        "fetch_stock_broll",
        "fetch_stock_images",
        "rip_video_segment",
        "fetch_sfx",
    }
