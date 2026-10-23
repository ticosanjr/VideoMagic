"""Background model downloads with progress, cancellation, and status."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from videoflow.application.models import install_model, installed_path
from videoflow.runtime import portable_home


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class ModelDownload:
    model_id: str
    status: str = "queued"
    percent: int = 0
    message: str = "Queued"
    error: str = ""
    started_at: str = field(default_factory=_now)
    finished_at: str = ""
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "status": self.status,
            "percent": self.percent,
            "message": self.message,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancel_requested": self.cancel_requested,
            "installed": installed_path(self.model_id) is not None,
        }


class ModelDownloadManager:
    def __init__(self) -> None:
        self._items: dict[str, ModelDownload] = {}
        self._lock = threading.Lock()
        self._load()

    @property
    def path(self) -> Path:
        return portable_home() / "model-downloads.json"

    def _load(self) -> None:
        path = self.path
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for item in payload.get("items", []):
            try:
                entry = ModelDownload(
                    model_id=str(item["model_id"]),
                    status=str(item.get("status", "interrupted")),
                    percent=int(item.get("percent", 0)),
                    message=str(item.get("message", "")),
                    error=str(item.get("error", "")),
                    started_at=str(item.get("started_at", _now())),
                    finished_at=str(item.get("finished_at", "")),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if entry.status in {"queued", "downloading"}:
                entry.status = "interrupted"
                entry.message = "Interrupted by restart"
            self._items[entry.model_id] = entry

    def _save(self) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"items": [item.to_dict() for item in self._items.values()]}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )

    def start(self, model_id: str, *, allow_network: bool = True) -> ModelDownload:
        with self._lock:
            active = self._items.get(model_id)
            if active is not None and active.status in {"queued", "downloading"}:
                return active
            item = ModelDownload(model_id=model_id)
            self._items[model_id] = item
            self._save()
        thread = threading.Thread(
            target=self._work,
            args=(model_id, allow_network),
            name=f"videoflow-model-{model_id}",
            daemon=True,
        )
        thread.start()
        return item

    def _work(self, model_id: str, allow_network: bool) -> None:
        with self._lock:
            item = self._items[model_id]
            item.status = "downloading"
            item.message = "Starting"
            self._save()

        def progress(percent: int, message: str) -> None:
            with self._lock:
                item.percent = percent
                item.message = message

        def cancelled() -> bool:
            with self._lock:
                return item.cancel_requested

        try:
            install_model(
                model_id,
                allow_network=allow_network,
                progress=progress,
                should_cancel=cancelled,
            )
        except Exception as exc:
            with self._lock:
                if item.cancel_requested:
                    item.status = "cancelled"
                    item.message = "Cancelled"
                else:
                    item.status = "failed"
                    item.error = str(exc)
                    item.message = "Download failed"
                item.finished_at = _now()
                self._save()
            return
        with self._lock:
            item.status = "installed"
            item.percent = 100
            item.message = "Installed"
            item.finished_at = _now()
            self._save()

    def cancel(self, model_id: str) -> ModelDownload | None:
        with self._lock:
            item = self._items.get(model_id)
            if item is None:
                return None
            if item.status in {"queued", "downloading"}:
                item.cancel_requested = True
                self._save()
            return item

    def get(self, model_id: str) -> ModelDownload | None:
        with self._lock:
            return self._items.get(model_id)

    def list(self) -> list[dict[str, object]]:
        with self._lock:
            return [item.to_dict() for item in self._items.values()]


downloads = ModelDownloadManager()
