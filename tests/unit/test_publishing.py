from datetime import UTC, datetime
from pathlib import Path

import httpx

from videoflow.application.publishing import (
    PublishTarget,
    cancel_publish,
    dispatch_due,
    enqueue_publish,
    list_queue,
    save_target,
)


def test_publish_queue_dispatches_to_webhook(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    save_target(
        PublishTarget(name="hook", webhook_url="https://example.com/hook")
    )
    asset = tmp_path / "short.mp4"
    asset.write_bytes(b"video")
    enqueue_publish(
        target_name="hook",
        asset_path=asset,
        title="Title",
        description="Description",
        hashtags=["#One"],
        scheduled_at="2020-01-01T00:00:00+00:00",
        job_id="job",
        short_index=0,
    )
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    items = dispatch_due(
        now=datetime.now(UTC),
        allow_external_services=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert items[0]["status"] == "sent"
    assert str(seen["url"]) == "https://example.com/hook"
    assert b"Title" in seen["body"]  # type: ignore[operator]
    assert list_queue()[0]["status"] == "sent"


def test_publish_queue_can_be_cancelled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    save_target(PublishTarget(name="hook", webhook_url="https://example.com/hook"))
    asset = tmp_path / "short.mp4"
    asset.write_bytes(b"video")
    item = enqueue_publish(target_name="hook", asset_path=asset, title="Title")
    cancelled = cancel_publish(item["id"])
    assert cancelled["status"] == "cancelled"
