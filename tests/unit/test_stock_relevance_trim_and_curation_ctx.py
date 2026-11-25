"""v4.7.0 stock relevance, auto-trim, Ken Burns, and curation context."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from videoflow.application.curation_board import load_board, publish_board
from videoflow.domains.media.download import trim_stock_video
from videoflow.domains.media.fetch_service import FetchService
from videoflow.domains.media.models import AssetCandidate
from videoflow.domains.media.search_keyless import _filter_stock
from videoflow.domains.vision.broll import build_broll_filter

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def _candidate(
    *,
    title: str,
    duration: float,
    size_bytes: int,
    description: str = "",
) -> AssetCandidate:
    return AssetCandidate(
        asset_id=title,
        provider="internet_archive",
        title=title,
        page_url="https://example.test/item",
        download_url="https://example.test/item.mp4",
        kind="video",
        duration_sec=duration,
        metadata={
            "size_bytes": size_bytes,
            "description": description,
        },
    )


def test_filter_stock_drops_long_heavy_and_irrelevant_candidates() -> None:
    candidates = [
        _candidate(
            title="White House chip policy briefing",
            duration=45.0,
            size_bytes=12 * 1024 * 1024,
        ),
        _candidate(
            title="2025 Easter Egg Roll",
            duration=10_800.0,
            size_bytes=2_400 * 1024 * 1024,
        ),
        _candidate(
            title="Spring garden tour",
            duration=30.0,
            size_bytes=8 * 1024 * 1024,
        ),
        _candidate(
            title="Ocean waves",
            duration=20.0,
            size_bytes=4 * 1024 * 1024,
        ),
    ]
    kept = _filter_stock(candidates, "White House chip policy")
    assert [item.title for item in kept] == ["White House chip policy briefing"]
    assert kept[0].metadata["relevance_score"] == 1.0


@pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not installed")
def test_trim_stock_video_cuts_to_a_light_excerpt(tmp_path: Path) -> None:
    source = tmp_path / "long.mp4"
    completed = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=30:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    target = tmp_path / "clip.mp4"
    result = trim_stock_video(
        source,
        max_duration_sec=1.0,
        clip_sec=0.5,
        destination=target,
    )
    assert result == target
    probe = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    assert 0.3 <= duration <= 0.8


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_fetch_stock_broll_drops_the_three_hour_easter_egg_roll(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "commons.wikimedia.org":
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "1": {
                                "pageid": 1,
                                "title": "File:Chip policy briefing.webm",
                                "imageinfo": [
                                    {
                                        "url": "https://upload.wikimedia.org/briefing.webm",
                                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:briefing.webm",
                                        "duration": 42.0,
                                        "size": 12_000_000,
                                        "extmetadata": {
                                            "LicenseShortName": {"value": "CC0"},
                                            "Artist": {"value": "Ada"},
                                            "ImageDescription": {
                                                "value": "White House chip policy briefing"
                                            },
                                        },
                                    }
                                ],
                            },
                            "2": {
                                "pageid": 2,
                                "title": "File:2025 Easter Egg Roll.webm",
                                "imageinfo": [
                                    {
                                        "url": "https://upload.wikimedia.org/easter.webm",
                                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:easter.webm",
                                        "duration": 10_800.0,
                                        "size": 2_400_000_000,
                                        "extmetadata": {
                                            "LicenseShortName": {"value": "CC0"},
                                            "Artist": {"value": "USDA"},
                                        },
                                    }
                                ],
                            },
                        }
                    }
                },
            )
        if request.url.host == "upload.wikimedia.org":
            name = Path(request.url.path).name
            return httpx.Response(200, content=b"video-" + name.encode())
        return httpx.Response(404, json={})

    service = FetchService(
        workspace_root=tmp_path,
        transport=httpx.MockTransport(handler),
        env={},
    )
    result = service.fetch_stock_broll(
        "demo",
        "White House chip policy",
        min_duration=0,
    )
    assert result["ok"] is True
    assert result["provider"] == "wikimedia"
    assert len(result["assets"]) == 1
    assert result["assets"][0]["metadata"]["relevance_score"] == 1.0
    downloaded = [item for item in requests if item.url.host == "upload.wikimedia.org"]
    assert [Path(item.url.path).name for item in downloaded] == ["briefing.webm"]


def test_broll_filter_keeps_ken_burns_within_six_percent() -> None:
    zoom_in = build_broll_filter(
        motion="zoom_in", duration=4.0, width=1080, height=1920
    )
    zoom_out = build_broll_filter(
        motion="zoom_out", duration=4.0, width=1080, height=1920
    )
    pan = build_broll_filter(
        motion="pan_left", duration=4.0, width=1080, height=1920
    )
    assert "1.06" in zoom_in and "1.25" not in zoom_in
    assert "1.06" in zoom_out and "1.25" not in zoom_out
    assert "1.06" in pan and "1.15" not in pan


def test_curation_item_keeps_temporal_and_spoken_context(tmp_path: Path) -> None:
    asset = tmp_path / "assets" / "broll" / "chip.jpg"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"jpeg")
    board = publish_board(
        tmp_path,
        "demo",
        [
            {
                "item_id": "broll-1",
                "category": "broll",
                "title": "Chip policy b-roll",
                "media_type": "image",
                "local_path": str(asset),
                "start_sec": 2.0,
                "end_sec": 8.0,
                "spoken_context": "Quando a Nvidia trava os chips",
                "note": "Entra na frase sobre export controls",
                "reason": "Ilustra o assunto falado",
            }
        ],
    )
    loaded = load_board(tmp_path)
    assert loaded is not None
    item = loaded.items[0]
    assert item.start_sec == 2.0
    assert item.end_sec == 8.0
    assert item.spoken_context == "Quando a Nvidia trava os chips"
    assert item.note == "Entra na frase sobre export controls"
    assert board.board_id == loaded.board_id
