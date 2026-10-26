"""Publish targets, queue retries, webhook auth, and scheduler lifecycle."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from videoflow.application import publishing
from videoflow.application.publishing import (
    PublishScheduler,
    PublishTarget,
    cancel_publish,
    delete_target,
    dispatch_due,
    enqueue_publish,
    list_queue,
    list_targets,
    save_target,
    start_scheduler,
    stop_scheduler,
)
from videoflow.domain.errors import StateNotReadyError


def past() -> str:
    return (datetime.now(UTC) - timedelta(minutes=1)).isoformat()


def add_target(name: str = "hook", *, enabled: bool = True) -> None:
    save_target(
        PublishTarget(
            name=name,
            webhook_url="https://example.com/hook",
            enabled=enabled,
        )
    )


def add_item(tmp_path: Path, **kwargs: object) -> dict[str, object]:
    asset = tmp_path / "asset.mp4"
    asset.write_bytes(b"video")
    return enqueue_publish(
        target_name="hook",
        asset_path=asset,
        title="Title",
        **kwargs,  # type: ignore[arg-type]
    )


def test_targets_round_trip_and_delete(tmp_path: Path) -> None:
    add_target("Hook")
    add_target("Other")

    assert [item["name"] for item in list_targets()] == ["Hook", "Other"]

    save_target(
        PublishTarget(name="hook", webhook_url="https://example.com/v2")
    )
    assert [item["webhook_url"] for item in list_targets()] == [
        "https://example.com/hook",
        "https://example.com/v2",
    ]

    delete_target("HOOK")
    assert [item["name"] for item in list_targets()] == ["Other"]


def test_enqueue_requires_an_enabled_target_and_asset(tmp_path: Path) -> None:
    with pytest.raises(StateNotReadyError, match="unavailable"):
        enqueue_publish(
            target_name="missing",
            asset_path=tmp_path / "asset.mp4",
            title="Title",
        )

    add_target(enabled=False)
    with pytest.raises(StateNotReadyError, match="unavailable"):
        enqueue_publish(
            target_name="hook",
            asset_path=tmp_path / "asset.mp4",
            title="Title",
        )

    add_target()
    with pytest.raises(StateNotReadyError, match="does not exist"):
        enqueue_publish(
            target_name="hook",
            asset_path=tmp_path / "missing.mp4",
            title="Title",
        )


def test_enqueue_defaults_and_cancel(tmp_path: Path) -> None:
    add_target()
    item = add_item(tmp_path, hashtags=["#One"])

    assert item["status"] == "pending"
    assert item["platform"] == "youtube"
    assert item["hashtags"] == ["#One"]
    assert list_queue()[0]["id"] == item["id"]

    cancelled = cancel_publish(str(item["id"]))
    assert cancelled["status"] == "cancelled"

    with pytest.raises(StateNotReadyError, match="not found"):
        cancel_publish("missing")


def test_dispatch_skips_future_and_non_pending_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_target()
    future = add_item(
        tmp_path,
        scheduled_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    cancel_publish(str(future["id"]))
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    sent = dispatch_due(
        allow_external_services=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert sent == []
    assert seen == []


def test_dispatch_sends_auth_headers_and_accepts_invalid_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_target()
    item = add_item(tmp_path, scheduled_at="not-a-date")
    monkeypatch.setenv("VIDEOWFLOW_PUBLISH_TOKEN", "secret-token")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(204)

    sent = dispatch_due(
        allow_external_services=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert seen["auth"] == "Bearer secret-token"
    assert seen["body"]["id"] == item["id"]  # type: ignore[index]
    assert sent[0]["status"] == "sent"


def test_dispatch_retries_then_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_target()
    item = add_item(tmp_path, scheduled_at=past())

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    statuses = []
    for _ in range(3):
        statuses.append(
            dispatch_due(allow_external_services=True, client=client)[0]["status"]
        )

    assert statuses == ["pending", "pending", "failed"]
    stored = next(entry for entry in list_queue() if entry["id"] == item["id"])
    assert stored["attempts"] == 3
    assert "503" in str(stored["last_error"])


def test_dispatch_fails_missing_or_disabled_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_target()
    item = add_item(tmp_path, scheduled_at=past())
    delete_target("hook")

    client = httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200))
    )
    sent = dispatch_due(allow_external_services=True, client=client)

    assert sent[0]["id"] == item["id"]
    assert sent[0]["status"] == "failed"
    assert sent[0]["last_error"] == "target missing or disabled"


def test_dispatch_treats_naive_timestamps_as_utc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_target()
    add_item(tmp_path, scheduled_at="2020-01-01T00:00:00")

    sent = dispatch_due(
        allow_external_services=True,
        client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(200))),
    )

    assert sent[0]["status"] == "sent"


def test_corrupt_store_files_are_ignored(tmp_path: Path) -> None:
    publishing.targets_path().parent.mkdir(parents=True, exist_ok=True)
    publishing.targets_path().write_text("not json", encoding="utf-8")
    publishing.queue_path().write_text("[]", encoding="utf-8")

    assert list_targets() == []
    assert list_queue() == []


def test_scheduler_start_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeThread:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def start(self) -> None:
            return None

        def is_alive(self) -> bool:
            return True

    monkeypatch.setattr(publishing.threading, "Thread", FakeThread)
    scheduler = PublishScheduler(interval=0.01)
    assert scheduler.start() is scheduler
    assert scheduler.start() is scheduler
    scheduler.stop()
    assert scheduler._stop.is_set()


def test_scheduler_run_dispatches_until_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = PublishScheduler(interval=0.01)
    calls: list[str] = []

    class Stop:
        def __init__(self) -> None:
            self.count = 0

        def wait(self, _interval: float) -> bool:
            self.count += 1
            return self.count > 1

    scheduler._stop = Stop()  # type: ignore[assignment]
    monkeypatch.setattr(
        publishing, "dispatch_due", lambda: calls.append("dispatch") or []
    )

    scheduler._run()

    assert calls == ["dispatch"]


def test_scheduler_run_survives_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = PublishScheduler(interval=0.01)
    calls: list[str] = []

    class Stop:
        def __init__(self) -> None:
            self.count = 0

        def wait(self, _interval: float) -> bool:
            self.count += 1
            return self.count > 1

    scheduler._stop = Stop()  # type: ignore[assignment]

    def fail() -> None:
        calls.append("fail")
        raise RuntimeError("offline")

    monkeypatch.setattr(publishing, "dispatch_due", fail)

    scheduler._run()

    assert calls == ["fail"]


def test_module_scheduler_starts_once_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeScheduler:
        instances = 0

        def __init__(self) -> None:
            FakeScheduler.instances += 1
            self.started = 0
            self.stopped = 0

        def start(self) -> FakeScheduler:
            self.started += 1
            return self

        def stop(self) -> None:
            self.stopped += 1

    monkeypatch.setattr(publishing, "PublishScheduler", FakeScheduler)
    monkeypatch.setattr(publishing, "_scheduler", None)

    first = start_scheduler()
    assert start_scheduler() is first
    assert first.started == 2  # type: ignore[attr-defined]

    stop_scheduler()
    assert first.stopped == 1  # type: ignore[attr-defined]
    stop_scheduler()


def test_items_persist_with_an_items_wrapper(tmp_path: Path) -> None:
    add_target()
    add_item(tmp_path, scheduled_at=past())

    payload = json.loads(publishing.queue_path().read_text(encoding="utf-8"))

    assert isinstance(payload["items"], list)
    assert payload["items"][0]["title"] == "Title"
