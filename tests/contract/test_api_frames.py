from __future__ import annotations

from pathlib import Path

from tests.contract.test_api_timeline import _client, _job


def test_batch_frame_prefetch_uses_the_revision_cache(monkeypatch, tmp_path: Path) -> None:
    from videoflow.adapters import ffmpeg as ffmpeg_module

    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    calls: list[Path] = []

    def fake_thumbnail(self, source, destination, *, time_sec, **kwargs):
        calls.append(Path(destination))
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"jpeg")
        return Path(destination)

    monkeypatch.setattr(ffmpeg_module.FFmpegAdapter, "render_thumbnail", fake_thumbnail)
    first = client.get(
        f"/api/v1/jobs/{job.job_id}/frames",
        params={"start": 0, "count": 3, "fps": 2, "height": 180},
    )
    assert first.status_code == 200, first.text
    payload = first.json()
    assert len(payload["frames"]) == 3
    assert [item["cached"] for item in payload["frames"]] == [False, False, False]
    assert all("height=180" in item["url"] for item in payload["frames"])
    assert len(calls) == 3

    second = client.get(
        f"/api/v1/jobs/{job.job_id}/frames",
        params={"start": 0, "count": 3, "fps": 2, "height": 180},
    )
    assert second.status_code == 200
    assert [item["cached"] for item in second.json()["frames"]] == [True, True, True]
    assert len(calls) == 3
    assert second.headers["x-frame-cache"] == "3/3"

    clamped = client.get(f"/api/v1/jobs/{job.job_id}/frames", params={"count": 999, "fps": 999})
    assert len(clamped.json()["frames"]) == 12
