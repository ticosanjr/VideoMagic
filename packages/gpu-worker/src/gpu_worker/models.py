"""Loaded-model registry with idle unload cleanup."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

UnloadCallback = Callable[[], None]


@dataclass(slots=True)
class LoadedModel:
    name: str
    capability: str | None
    loaded_at: float
    last_used: float
    unload: UnloadCallback | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    vram_mb: int = 0


class ModelRegistry:
    """Track loaded models and run optional unload callbacks after idling."""

    def __init__(self, ttl_seconds: float = 900.0) -> None:
        self.ttl_seconds = max(float(ttl_seconds), 0.0)
        self._models: dict[str, LoadedModel] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def register(
        self,
        name: str,
        *,
        capability: str | None = None,
        unload: UnloadCallback | None = None,
        metadata: dict[str, Any] | None = None,
        vram_mb: int = 0,
    ) -> LoadedModel:
        if not name or not name.strip():
            raise ValueError("model name must not be empty")
        now = time.time()
        model = LoadedModel(
            name=name,
            capability=capability,
            loaded_at=now,
            last_used=now,
            unload=unload,
            metadata=dict(metadata or {}),
            vram_mb=max(int(vram_mb), 0),
        )
        with self._lock:
            previous = self._models.get(name)
            self._models[name] = model
        if previous is not None and previous.unload is not None:
            with contextlib.suppress(Exception):
                previous.unload()
        return model

    def touch(self, name: str) -> bool:
        with self._lock:
            model = self._models.get(name)
            if model is None:
                return False
            model.last_used = time.time()
            return True

    def unload(self, name: str) -> bool:
        with self._lock:
            model = self._models.pop(name, None)
        if model is None:
            return False
        if model.unload is not None:
            with contextlib.suppress(Exception):
                model.unload()
        return True

    def vram_used_mb(self) -> int:
        with self._lock:
            return sum(model.vram_mb for model in self._models.values())

    def unload_lru(self, required_mb: int) -> tuple[list[str], int]:
        """Unload least-recently-used models until ``required_mb`` is freed."""

        required = max(int(required_mb), 0)
        if required <= 0:
            return [], 0
        with self._lock:
            ordered = sorted(self._models.values(), key=lambda item: item.last_used)
        names: list[str] = []
        freed = 0
        for model in ordered:
            if freed >= required:
                break
            if self.unload(model.name):
                names.append(model.name)
                freed += model.vram_mb
        return names, freed

    def sweep(self, *, now: float | None = None) -> list[str]:
        """Unload models idle longer than the TTL; return their names."""

        moment = time.time() if now is None else now
        with self._lock:
            expired = [
                model.name
                for model in self._models.values()
                if moment - model.last_used >= self.ttl_seconds
            ]
        return [name for name in expired if self.unload(name)]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            models = list(self._models.values())
        return [
            {
                "name": model.name,
                "capability": model.capability,
                "loaded_at": model.loaded_at,
                "last_used": model.last_used,
                "metadata": dict(model.metadata),
                "vram_mb": model.vram_mb,
            }
            for model in models
        ]

    def __len__(self) -> int:
        with self._lock:
            return len(self._models)

    def start(self) -> None:
        """Start the background unload thread once."""

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if self.ttl_seconds <= 0:
                return
            self._stop.clear()
            interval = max(min(self.ttl_seconds / 2.0, 30.0), 0.1)
            self._thread = threading.Thread(
                target=self._cleanup_loop,
                args=(interval,),
                name="gpu-worker-model-ttl",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
        self._stop.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _cleanup_loop(self, interval: float) -> None:
        while not self._stop.wait(interval):
            self.sweep()
