"""Resumable HTTP upload sessions for large artifacts."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from gpu_worker.artifacts import ArtifactRecord, ArtifactStore, ArtifactTooLarge, _digest_file
from gpu_worker.security import safe_filename

_INDEX_NAME = "sessions.json"


@dataclass(frozen=True, slots=True)
class UploadSession:
    id: str
    filename: str
    size: int
    sha256: str
    path: Path
    received: int
    chunk_size: int
    created_at: float

    def as_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "size": self.size,
            "sha256": self.sha256,
            "received": self.received,
            "chunk_size": self.chunk_size,
            "created_at": self.created_at,
        }


class UploadStore:
    """Track partial uploads and finalize them into the artifact store.

    The index is persisted so a worker restart can resume an upload instead of
    forcing the controller to send the whole file again.
    """

    def __init__(self, root: Path, artifacts: ArtifactStore, *, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts = artifacts
        self.max_bytes = int(max_bytes)
        self._index_path = self.root / _INDEX_NAME
        self._lock = threading.RLock()
        self._sessions: dict[str, UploadSession] = {}
        self._load()

    def _load(self) -> None:
        payload: dict[str, object] = {}
        try:
            value = json.loads(self._index_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                payload = value
        except (OSError, ValueError):
            payload = {}
        raw = payload.get("sessions")
        if not isinstance(raw, dict):
            raw = {}
        for upload_id, item in raw.items():
            if not isinstance(item, dict):
                continue
            path = self.root / f"{upload_id}.part"
            if not path.is_file():
                continue
            try:
                size = int(item.get("size") or 0)
                received = path.stat().st_size
                if size <= 0 or received > size:
                    path.unlink(missing_ok=True)
                    continue
                self._sessions[str(upload_id)] = UploadSession(
                    id=str(upload_id),
                    filename=safe_filename(str(item.get("filename") or "upload.bin")),
                    size=size,
                    sha256=str(item.get("sha256") or "").strip().lower(),
                    path=path,
                    received=received,
                    chunk_size=max(1, int(item.get("chunk_size") or 8 * 1024 * 1024)),
                    created_at=float(item.get("created_at") or time.time()),
                )
            except (OSError, TypeError, ValueError):
                continue
        self._save()

    def _save(self) -> None:
        payload = {
            "schema_version": 1,
            "sessions": {
                upload_id: session.as_dict()
                for upload_id, session in self._sessions.items()
            },
        }
        temporary = self._index_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self._index_path)

    def create(
        self,
        *,
        filename: str,
        size: int,
        sha256: str = "",
        chunk_size: int = 8 * 1024 * 1024,
    ) -> UploadSession:
        if size < 0:
            raise ValueError("size must be non-negative")
        if size > self.max_bytes:
            raise ArtifactTooLarge(
                f"upload exceeds the {self.max_bytes} byte artifact limit"
            )
        digest = str(sha256 or "").strip().lower()
        with self._lock:
            if digest:
                for session in self._sessions.values():
                    if (
                        session.sha256 == digest
                        and session.size == size
                        and session.received < session.size
                    ):
                        return session
            upload_id = uuid.uuid4().hex
            path = self.root / f"{upload_id}.part"
            path.touch()
            session = UploadSession(
                id=upload_id,
                filename=safe_filename(filename),
                size=int(size),
                sha256=digest,
                path=path,
                received=0,
                chunk_size=max(1, int(chunk_size)),
                created_at=time.time(),
            )
            self._sessions[upload_id] = session
            self._save()
            return session

    def get(self, upload_id: str) -> UploadSession | None:
        with self._lock:
            return self._sessions.get(str(upload_id))

    def append(self, upload_id: str, offset: int, data: bytes) -> UploadSession:
        if not data:
            raise ValueError("upload chunk is empty")
        with self._lock:
            session = self._sessions.get(str(upload_id))
            if session is None:
                raise KeyError("upload session not found")
            if int(offset) != session.received:
                raise ValueError(
                    f"upload offset mismatch: expected {session.received}, got {offset}"
                )
            if session.received + len(data) > session.size:
                raise ValueError("upload chunk exceeds the declared size")
            with session.path.open("ab") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            received = session.path.stat().st_size
            updated = UploadSession(
                id=session.id,
                filename=session.filename,
                size=session.size,
                sha256=session.sha256,
                path=session.path,
                received=received,
                chunk_size=session.chunk_size,
                created_at=session.created_at,
            )
            self._sessions[session.id] = updated
            self._save()
            return updated

    def complete(self, upload_id: str) -> ArtifactRecord:
        with self._lock:
            session = self._sessions.get(str(upload_id))
            if session is None:
                raise KeyError("upload session not found")
            received = session.path.stat().st_size
            if received != session.size:
                raise ValueError(
                    f"upload is incomplete: received {received} of {session.size} bytes"
                )
            digest, measured = _digest_file(session.path)
            if session.sha256 and digest != session.sha256:
                session.path.unlink(missing_ok=True)
                self._sessions.pop(session.id, None)
                self._save()
                raise ValueError("upload SHA-256 does not match the declared digest")
            record = self.artifacts.save_path(
                session.path,
                session.filename,
                sha256=digest,
                size=measured,
            )
            self._sessions.pop(session.id, None)
            self._save()
            return record

    def cleanup_stale(self, max_age_sec: float = 24 * 3600) -> int:
        cutoff = time.time() - max(0.0, float(max_age_sec))
        removed = 0
        with self._lock:
            for upload_id, session in list(self._sessions.items()):
                if session.created_at >= cutoff:
                    continue
                session.path.unlink(missing_ok=True)
                self._sessions.pop(upload_id, None)
                removed += 1
            if removed:
                self._save()
        return removed


__all__ = ["UploadSession", "UploadStore"]
