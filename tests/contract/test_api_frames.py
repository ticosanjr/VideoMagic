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


def test_frame_uses_the_edited_timeline_mapping(monkeypatch, tmp_path: Path) -> None:
    from videoflow.adapters import ffmpeg as ffmpeg_module
    from videoflow.domain.state import (
        AudioSegment,
        MediaInfo,
        ProjectState,
        VideoSegment,
    )

    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    job = _job(manager, tmp_path)
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=900,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            ),
            VideoSegment(
                clip_id="v2",
                source_in_frame=300,
                source_out_frame=330,
                timeline_in_frame=30,
                timeline_out_frame=60,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            ),
            AudioSegment(
                clip_id="v2",
                source_in_sample=480000,
                source_out_sample=528000,
                timeline_in_sample=48000,
                timeline_out_sample=96000,
            ),
        ],
    )
    (job.output / "project_state.json").write_text(
        state.model_dump_json(), encoding="utf-8"
    )
    moments: list[float] = []

    def fake_thumbnail(self, source_path, destination, *, time_sec, **kwargs):
        moments.append(time_sec)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"jpeg")
        return Path(destination)

    monkeypatch.setattr(ffmpeg_module.FFmpegAdapter, "render_thumbnail", fake_thumbnail)

    single = client.get(
        f"/api/v1/jobs/{job.job_id}/frame", params={"time": 1.5, "height": 180}
    )
    assert single.status_code == 200, single.text
    assert moments[-1] == 10.5

    batch = client.get(
        f"/api/v1/jobs/{job.job_id}/frames",
        params={"start": 1.5, "count": 1, "fps": 2, "height": 180},
    )
    assert batch.status_code == 200, batch.text
    assert moments[-1] == 10.5
