from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tests.contract.test_api_timeline import _client, _job


def _error(response) -> dict:
    payload = response.json()
    detail = payload.get("detail", payload)
    return detail if isinstance(detail, dict) else {"errors": detail}


def test_live_source_routes_and_errors(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes_outputs as routes_module
    from videoflow.application.live_source import LiveSourceState

    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    state = LiveSourceState(status="preparing", reason="probing", path="")

    class Fake:
        def status(self, job, *, height):
            return state

        def start(self, job, *, height):
            return LiveSourceState(status="ready", url="/live", path=str(tmp_path / "x.mp4"))

        def file(self, job, *, height):
            return None

    monkeypatch.setattr(routes_module, "live_sources", Fake())
    assert client.get(f"{base}/live-source/status").json()["live_source"]["status"] == "preparing"
    assert client.post(f"{base}/live-source").json()["live_source"]["status"] == "ready"
    missing = client.get(f"{base}/live-source/file")
    assert missing.status_code == 409
    assert _error(missing)["code"] == "state_not_ready"

    target = tmp_path / "live.mp4"
    target.write_bytes(b"live")
    Fake.file = lambda self, job, *, height: target
    monkeypatch.setattr(routes_module, "live_sources", Fake())
    served = client.get(f"{base}/live-source/file")
    assert served.status_code == 200

    monkeypatch.setattr(routes_module, "live_sources", Fake())
    monkeypatch.setattr(
        routes_module,
        "load_state",
        lambda path: (_ for _ in ()).throw(OSError("bad state")),
    )
    assert client.get(f"{base}/live-source/status").json()["live_source"]["status"] == "preparing"
    monkeypatch.setattr(
        routes_module,
        "load_state",
        lambda path: SimpleNamespace(media_info=SimpleNamespace(height=720)),
    )

    class BrokenFile:
        def file(self, job, *, height):
            raise OSError("bad state")

    monkeypatch.setattr(routes_module, "live_sources", BrokenFile())
    failed = client.get(f"{base}/live-source/file")
    assert failed.status_code == 422
    assert _error(failed)["code"] == "live_source_failed"


def test_source_file_missing_media_and_missing_file(monkeypatch, tmp_path: Path) -> None:
    from videoflow.domain.state import MediaInfo, ProjectState

    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    ok = client.get(f"{base}/source/file")
    assert ok.status_code == 200

    state_path = Path(job.result["state_path"])
    state_path.write_text(ProjectState().model_dump_json(), encoding="utf-8")
    no_media = client.get(f"{base}/source/file")
    assert no_media.status_code == 409
    assert _error(no_media)["code"] == "state_not_ready"

    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(tmp_path / "gone.mp4"),
            duration_frames=1,
            fps_num=30,
            fps_den=1,
            width=10,
            height=10,
            audio_sample_rate=48000,
        )
    )
    state_path.write_text(state.model_dump_json(), encoding="utf-8")
    offline = client.get(f"{base}/source/file")
    assert offline.status_code == 409
    assert _error(offline)["code"] == "state_not_ready"


def test_render_and_preview_stale_states(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import previews as previews_module
    from videoflow.application import render_queue
    from videoflow.application.worker_state import WorkerState

    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    render_queue.renders._items[str(job.job_id)] = WorkerState(
        job_id=str(job.job_id), status="ready"
    )
    stale = client.get(f"{base}/render/status").json()
    assert stale["status"] == "failed"
    assert stale["error_details"]["code"] == "render_stale"

    previews_module.previews._items[str(job.job_id)] = WorkerState(
        job_id=str(job.job_id), status="ready"
    )
    stale_preview = client.get(f"{base}/preview/status").json()
    assert stale_preview["status"] == "stale"
    assert stale_preview["message"] == "Preview is stale"


def test_step_outputs_validation_edges(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}/steps/bad%5Cid"

    assert client.get(f"{base}/outputs").status_code == 422
    assert client.get(f"{base}/outputs/port").status_code == 422
    assert client.get(f"{base}/files/x.txt").status_code == 422
    assert client.post(f"{base}/save", json={"target_dir": str(tmp_path)}).status_code == 422

    good = f"/api/v1/jobs/{job.job_id}/steps/ingest"
    assert client.get(f"{good}/outputs").status_code == 404
    assert client.get(f"{good}/outputs/port").status_code == 404
    assert client.get(f"{good}/files/x.txt").status_code == 404
    assert (
        client.post(f"{good}/save", json={"target_dir": str(tmp_path)}).status_code
        == 404
    )


def test_timeline_helper_functions(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes_timeline as module
    from videoflow.domain.state import (
        AudioSegment,
        MediaInfo,
        ProjectState,
        VideoSegment,
    )

    body = module.LenientJsonBody.decode_body('{"a": 1}')
    assert body == {"a": 1}
    for value in ["[]", "{bad"]:
        try:
            module.LenientJsonBody.decode_body(value)
        except ValueError as exc:
            assert "JSON object" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("expected ValueError")

    output = tmp_path / "out"
    output.mkdir()
    (output / "titles.ass").write_text("x", encoding="utf-8")
    assert module._live_titles(output) == ([], False)
    (output / "titles.json").write_text("{bad", encoding="utf-8")
    assert module._live_titles(output) == ([], False)
    (output / "titles.json").write_text(
        json.dumps(
            {
                "title_cards": [
                    "bad",
                    {"kind": "short", "text": "skip"},
                    {"text": "", "start_sec": 0},
                    {"text": "Title", "start_sec": 1, "duration_sec": 1},
                ],
                "lower_thirds": [
                    "bad",
                    {"text": "", "start_sec": 0},
                    {"text": "Lower", "start_sec": 2, "end_sec": 4},
                ],
            }
        ),
        encoding="utf-8",
    )
    cues, ready = module._live_titles(output)
    assert ready is True
    assert [cue["text"] for cue in cues] == ["Title", "Lower"]

    assert module._live_playback(ProjectState(), None) == (False, "no media info")
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(tmp_path / "gone.mp4"),
            duration_frames=10,
            fps_num=30,
            fps_den=1,
            width=10,
            height=10,
            audio_sample_rate=48000,
        )
    )
    assert module._live_playback(state, None) == (False, "source media is offline")

    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    state.media_info = state.media_info.model_copy(update={"source_path": str(source)})
    state.video_segments = [
        VideoSegment(
            clip_id="v1",
            source_in_frame=0,
            source_out_frame=10,
            timeline_in_frame=0,
            timeline_out_frame=10,
        )
    ]
    assert module._live_playback(state, None) == (
        False,
        "audio/video segments are not paired",
    )
    state.audio_segments = [
        AudioSegment(
            clip_id="v1",
            source_in_sample=0,
            source_out_sample=10,
            timeline_in_sample=0,
            timeline_out_sample=10,
        )
    ]
    assert module._live_playback(state, None)[0] is True
    state.video_segments[0].transform = state.video_segments[0].transform.model_copy(
        update={"scale": 1.2}
    )
    assert module._live_playback(state, None) == (
        False,
        "clip transforms require the rendered preview",
    )


def test_snapshot_and_overlay_error_routes(monkeypatch, tmp_path: Path) -> None:
    from videoflow.domain.state import OverlayClip, ProjectState

    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    assert client.get("/api/v1/timelines/bad..id/file").status_code == 422
    assert client.get("/api/v1/timelines/missing/file").status_code == 404
    assert client.delete("/api/v1/timelines/bad..id").status_code == 422
    assert client.delete("/api/v1/timelines/missing").status_code == 404
    assert client.post("/api/v1/timelines/import", json={"payload": []}).status_code == 422

    unknown = client.get(f"{base}/overlays/missing/file")
    assert unknown.status_code == 409
    assert _error(unknown)["code"] == "state_not_ready"

    state_path = Path(job.result["state_path"])
    state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
    overlay = tmp_path / "overlay.png"
    overlay.write_bytes(b"png")
    state.overlays.append(
        OverlayClip(
            overlay_id="o1",
            path=str(overlay),
            start_frame=0,
            duration_frames=10,
        )
    )
    state_path.write_text(state.model_dump_json(), encoding="utf-8")
    served = client.get(f"{base}/overlays/o1/file")
    assert served.status_code == 200
    assert served.content == b"png"
    overlay.unlink()
    offline = client.get(f"{base}/overlays/o1/file")
    assert offline.status_code == 409
