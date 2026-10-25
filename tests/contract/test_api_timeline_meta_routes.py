from __future__ import annotations

from pathlib import Path

from tests.contract.test_api_timeline import _client, _job


def test_timeline_meta_markers_overlays_comments_and_captions(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    meta = client.get(f"{base}/timeline/meta")
    assert meta.status_code == 200
    saved = client.put(
        f"{base}/timeline/meta",
        json={"markers": [], "tracks": {"video": {"muted": True}}, "comments": []},
    )
    assert saved.status_code == 200
    assert client.get(f"{base}/timeline/meta").json()["tracks"]["video"]["muted"] is True

    marker = client.post(f"{base}/timeline/markers", json={"time_sec": 0.5, "label": "intro"})
    assert marker.status_code == 201
    marker_id = marker.json()["markers"][0]["id"]
    assert client.delete(f"{base}/timeline/markers/{marker_id}").status_code == 200
    assert client.delete(f"{base}/timeline/markers/missing").status_code == 200

    image = tmp_path / "overlay.png"
    image.write_bytes(b"png")
    overlay = client.post(
        f"{base}/timeline/overlays",
        json={"path": str(image), "start_sec": 0.2, "duration_sec": 0.5},
    )
    assert overlay.status_code == 201
    overlay_id = overlay.json()["overlays"][-1]["overlay_id"]
    assert client.delete(f"{base}/timeline/overlays/{overlay_id}").status_code == 200
    assert client.delete(f"{base}/timeline/overlays/missing").status_code == 409

    comment = client.post(
        f"{base}/timeline/comments",
        json={"clip_id": "v1", "text": "tighten"},
    )
    assert comment.status_code == 201
    comment_id = comment.json()["comments"][-1]["id"]
    assert client.delete(f"{base}/timeline/comments/{comment_id}").status_code == 200
    assert client.delete(f"{base}/timeline/comments/missing").status_code == 200

    review_comment = client.post(
        f"{base}/review/comments", json={"text": "looks good", "time_sec": 0.1}
    )
    assert review_comment.status_code == 201
    assert client.get(f"{base}/review/comments").status_code == 200

    batch = client.patch(
        f"{base}/timeline/batch",
        json={"edits": [{"clip_id": "v1", "action": "move", "delta_sec": 0.1}]},
    )
    assert batch.status_code == 200
    assert client.post(f"{base}/timeline/undo").status_code == 200
    assert client.post(f"{base}/timeline/redo").status_code == 200

    caption = client.patch(f"{base}/captions/0", json={"text": "hello"})
    assert caption.status_code < 500
    clip = client.patch(f"{base}/timeline/clip/v1", json={"scale": 1.2})
    assert clip.status_code < 500
