"""Generic webhook publishing and a small local schedule queue."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from videoflow.application.capabilities import ensure_external_allowed
from videoflow.domain.errors import FilesystemError, StateNotReadyError
from videoflow.runtime import portable_home

TARGETS_FILE = "publish_targets.json"
QUEUE_FILE = "publish_queue.json"


class PublishTarget(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    webhook_url: str = Field(min_length=1)
    secret_name: str = "VIDEOWFLOW_PUBLISH_TOKEN"
    enabled: bool = True


class PublishQueueItem(BaseModel):
    id: str
    target: str
    asset_path: str
    title: str
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    platform: str = "youtube"
    scheduled_at: str
    status: str = "pending"
    attempts: int = 0
    last_error: str = ""
    job_id: str | None = None
    short_index: int | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))


def targets_path() -> Path:
    return portable_home() / TARGETS_FILE


def queue_path() -> Path:
    return portable_home() / QUEUE_FILE


def list_targets() -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in _read_targets()]


def save_target(target: PublishTarget) -> dict[str, object]:
    targets = _read_targets()
    clean = [item for item in targets if item.name.casefold() != target.name.casefold()]
    clean.append(target)
    _write_targets(clean)
    return target.model_dump(mode="json")


def delete_target(name: str) -> None:
    targets = [item for item in _read_targets() if item.name.casefold() != name.casefold()]
    _write_targets(targets)


def list_queue() -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in _read_queue()]


def enqueue_publish(
    *,
    target_name: str,
    asset_path: Path,
    title: str,
    description: str = "",
    hashtags: list[str] | None = None,
    platform: str = "youtube",
    scheduled_at: str | None = None,
    job_id: str | None = None,
    short_index: int | None = None,
) -> dict[str, object]:
    targets = {item.name.casefold(): item for item in _read_targets()}
    target = targets.get(target_name.casefold())
    if target is None or not target.enabled:
        raise StateNotReadyError(f"Publish target is unavailable: {target_name}")
    asset = Path(asset_path).expanduser().resolve()
    if not asset.is_file():
        raise StateNotReadyError(f"Publish asset does not exist: {asset}")
    scheduled = scheduled_at or datetime.now(UTC).isoformat(timespec="seconds")
    item = PublishQueueItem(
        id=f"{int(time.time() * 1000)}-{len(_read_queue()) + 1}",
        target=target.name,
        asset_path=str(asset),
        title=title,
        description=description,
        hashtags=list(hashtags or []),
        platform=platform,
        scheduled_at=scheduled,
        job_id=job_id,
        short_index=short_index,
    )
    queue = _read_queue()
    queue.append(item)
    _write_queue(queue)
    return item.model_dump(mode="json")


def cancel_publish(item_id: str) -> dict[str, object]:
    queue = _read_queue()
    for item in queue:
        if item.id == item_id:
            item.status = "cancelled"
            _write_queue(queue)
            return item.model_dump(mode="json")
    raise StateNotReadyError(f"Publish item not found: {item_id}")


def dispatch_due(
    *,
    now: datetime | None = None,
    allow_external_services: bool = False,
    allowed_hosts: tuple[str, ...] = (),
    client: httpx.Client | None = None,
) -> list[dict[str, object]]:
    targets = {item.name.casefold(): item for item in _read_targets()}
    current = now or datetime.now(UTC)
    queue = _read_queue()
    sent: list[dict[str, object]] = []
    for item in queue:
        if item.status != "pending":
            continue
        try:
            due = datetime.fromisoformat(item.scheduled_at)
        except ValueError:
            due = current
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        if due > current:
            continue
        target = targets.get(item.target.casefold())
        if target is None or not target.enabled:
            item.status = "failed"
            item.last_error = "target missing or disabled"
            continue
        try:
            ensure_external_allowed(
                target.webhook_url,
                capability="publish_webhook",
                allow_external_services=allow_external_services,
                allowed_hosts=allowed_hosts,
            )
            headers = {}
            token = os.environ.get(target.secret_name)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            payload = item.model_dump(mode="json")
            request_client = client or httpx.Client(timeout=30.0)
            close = client is None
            try:
                response = request_client.post(
                    target.webhook_url,
                    headers=headers,
                    json=payload,
                )
            finally:
                if close:
                    request_client.close()
            if response.status_code >= 400:
                raise FilesystemError(
                    f"Webhook returned HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as exc:
            item.attempts += 1
            item.last_error = str(exc)
            item.status = "failed" if item.attempts >= 3 else "pending"
        else:
            item.status = "sent"
            item.last_error = ""
        sent.append(item.model_dump(mode="json"))
    _write_queue(queue)
    return sent


class PublishScheduler:
    def __init__(self, interval: float = 30.0) -> None:
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> PublishScheduler:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._thread = threading.Thread(
                target=self._run, name="videoflow-publisher", daemon=True
            )
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                dispatch_due()
            except Exception:
                continue


_scheduler: PublishScheduler | None = None


def start_scheduler() -> PublishScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = PublishScheduler()
    return _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None


def _read_targets() -> list[PublishTarget]:
    return _read_list(targets_path(), PublishTarget)


def _read_queue() -> list[PublishQueueItem]:
    return _read_list(queue_path(), PublishQueueItem)


def _read_list(path: Path, model: type[PublishTarget] | type[PublishQueueItem]) -> list[Any]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items", [])
        return [model.model_validate(item) for item in items]
    except (OSError, ValueError):
        return []


def _write_targets(items: list[PublishTarget]) -> None:
    _write_items(targets_path(), items)


def _write_queue(items: list[PublishQueueItem]) -> None:
    _write_items(queue_path(), items)


def _write_items(path: Path, items: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"items": [item.model_dump(mode="json") for item in items]}, indent=2)
        + "\n",
        encoding="utf-8",
    )
