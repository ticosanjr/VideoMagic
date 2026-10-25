from __future__ import annotations

from pathlib import Path

from tests.contract.test_api_timeline import _client, _job


def _short_job(monkeypatch, tmp_path: Path):
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    media = tmp_path / "out" / "short-1.mp4"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"short")
    thumb = tmp_path / "out" / "thumb-1.png"
    thumb.write_bytes(b"png")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x")
    job.result["shorts"] = [
        {
            "title": "Hook",
            "path": str(media),
            "thumbnail": str(thumb),
            "duration_sec": 12,
        },
        {"title": "Broken", "path": "", "thumbnail": str(outside)},
    ]
    return client, job, media, thumb, outside


def test_short_download_and_thumbnail_variants(monkeypatch, tmp_path: Path) -> None:
    client, job, media, thumb, outside = _short_job(monkeypatch, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}/shorts"

    assert client.get(f"{base}/0").status_code == 200
    assert client.get(f"{base}/99").status_code == 404
    assert client.get(f"{base}/1").status_code == 404
    assert client.get(f"{base}/0/file").status_code == 200
    assert client.get(f"{base}/1/file").status_code == 404
    assert client.get(f"{base}/0/thumbnail").status_code == 200

    job.result["shorts"][0]["thumbnail"] = str(outside)
    assert client.get(f"{base}/0/thumbnail").status_code == 403
    job.result["shorts"][0]["path"] = str(outside)
    assert client.get(f"{base}/0").status_code == 403
    job.result["shorts"][0]["path"] = ""
    assert client.get(f"{base}/0").status_code == 404


def test_artifacts_thumbnails_and_clip_thumbnail(monkeypatch, tmp_path: Path) -> None:
    from videoflow.adapters import ffmpeg as ffmpeg_module

    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    artifact = tmp_path / "out" / "final.mp4"
    artifact.write_bytes(b"mp4")
    job.result["artifacts"] = {"final.mp4": str(artifact), "empty": ""}

    assert client.get(f"/api/v1/jobs/{job.job_id}/artifacts/final.mp4").status_code == 200
    assert client.get(f"/api/v1/jobs/{job.job_id}/artifacts/empty").status_code == 404
    assert client.get(f"/api/v1/jobs/{job.job_id}/artifacts/nope").status_code == 404
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x")
    job.result["artifacts"]["bad"] = str(outside)
    assert client.get(f"/api/v1/jobs/{job.job_id}/artifacts/bad").status_code == 404

    def fake_thumbnail(self, source, destination, *, time_sec, **kwargs):
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"jpeg")
        return Path(destination)

    monkeypatch.setattr(ffmpeg_module.FFmpegAdapter, "render_thumbnail", fake_thumbnail)
    assert client.get(f"/api/v1/jobs/{job.job_id}/clips/v1/thumbnail").status_code == 200
    assert client.get(f"/api/v1/jobs/{job.job_id}/clips/missing/thumbnail").status_code == 409

    (tmp_path / "out" / "thumbnails").mkdir(exist_ok=True)
    (tmp_path / "out" / "thumbnails" / "a.png").write_bytes(b"png")
    assert client.get(f"/api/v1/jobs/{job.job_id}/thumbnails/a.png").status_code == 200
    assert client.get(f"/api/v1/jobs/{job.job_id}/thumbnails/none.png").status_code == 404
    assert client.get(f"/api/v1/jobs/{job.job_id}/thumbnails/..%2Fsecret").status_code in {400, 404}
