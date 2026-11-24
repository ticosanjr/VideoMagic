"""Curation media previews: paths, posters, MIME, Range, and decisions."""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.curation_board import publish_board, save_decisions
from videoflow.application.projects import init_project

FFMPEG = shutil.which("ffmpeg")


def _png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (32, 32), (30, 120, 220)).save(path)


def _wav24(path: Path) -> None:
    sample = (1000 << 8).to_bytes(3, "little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(3)
        handle.setframerate(48000)
        handle.writeframes(sample * 4800)


def _video(path: Path) -> None:
    assert FFMPEG is not None
    subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:r=30:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    record, _ = init_project(output=tmp_path / "project")
    return record


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_media_poster_mime_range_and_decision_fields(project: Path) -> None:
    output = Path(project.output)
    assets = output / "assets"
    assets.mkdir(parents=True)
    image = assets / "frame.png"
    audio = assets / "music24.wav"
    video = assets / "clip.mp4"
    _png(image)
    _wav24(audio)
    _video(video)
    items = [
        {
            "item_id": "image-1",
            "category": "image",
            "scene_id": "scene-a",
            "title": "Frame",
            "media_type": "image",
            "local_path": "assets/frame.png",
        },
        {
            "item_id": "audio-1",
            "category": "music",
            "scene_id": "scene-a",
            "title": "Music",
            "media_type": "audio",
            "local_path": "assets/music24.wav",
        },
        {
            "item_id": "video-1",
            "category": "broll",
            "scene_id": "scene-b",
            "title": "Clip",
            "media_type": "video",
            "local_path": "assets/clip.mp4",
        },
        {
            "item_id": "canal-paula-reels",
            "category": "style",
            "title": "Canal Paula Reels",
            "media_type": "style",
        },
    ]
    board = publish_board(output, project.project_id, items)
    by_id = {item.item_id: item for item in board.items}
    assert by_id["image-1"].local_path == str(image.resolve())
    assert by_id["image-1"].media_url.endswith("/media/image-1")
    assert "poster" in by_id["video-1"].poster_url
    assert by_id["canal-paula-reels"].preview_meta["palette"]

    client = TestClient(create_app())
    board_payload = client.get(f"/api/v1/curation/{project.project_id}").json()["board"]
    assert board_payload["items"][0]["media_url"]

    image_response = client.get(
        f"/api/v1/curation/{project.project_id}/media/image-1"
    )
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/png")

    audio_response = client.get(
        f"/api/v1/curation/{project.project_id}/media/audio-1"
    )
    assert audio_response.status_code == 200
    assert audio_response.headers["content-type"].startswith("audio/mpeg")

    ranged = client.get(
        f"/api/v1/curation/{project.project_id}/media/image-1",
        headers={"Range": "bytes=0-10"},
    )
    assert ranged.status_code == 206

    poster = client.get(
        f"/api/v1/curation/{project.project_id}/poster/video-1"
    )
    assert poster.status_code == 200
    assert poster.headers["content-type"].startswith("image/jpeg")

    updated = save_decisions(
        output,
        selected_ids=["image-1"],
        rejected_ids=[],
    )
    selected = next(item for item in updated.items if item.item_id == "image-1")
    assert selected.scene_id == "scene-a"
    assert selected.local_path == str(image.resolve())
    read = client.get(f"/api/v1/curation/{project.project_id}").json()["board"]
    kept = next(item for item in read["items"] if item["item_id"] == "image-1")
    assert kept["scene_id"] == "scene-a"
    assert kept["local_path"] == str(image.resolve())


def test_media_outside_allowed_roots_is_blocked(project: Path) -> None:
    items = [
        {
            "item_id": "outside-1",
            "category": "image",
            "title": "Outside",
            "media_type": "image",
            "local_path": "/etc/hosts",
        }
    ]
    publish_board(Path(project.output), project.project_id, items)
    client = TestClient(create_app())
    response = client.get(
        f"/api/v1/curation/{project.project_id}/media/outside-1"
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "path_not_allowed"
