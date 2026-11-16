"""Content-addressed artifact storage."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import BinaryIO

from gpu_worker.security import safe_extension, safe_filename
from gpu_worker.store import ArtifactRecord, JobStore

_CHUNK_SIZE = 1024 * 1024


class ArtifactTooLarge(ValueError):
    """Raised when an upload exceeds the configured per-artifact limit."""


class ArtifactStore:
    """Store uploads by SHA-256 digest under a constrained object root."""

    def __init__(self, root: Path, store: JobStore, *, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.root = Path(root).expanduser().resolve()
        self.objects = self.root / "objects"
        self.tmp = self.root / "tmp"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self._store = store
        self.max_bytes = max_bytes

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        """Return a readable artifact, refusing tampered paths outside the object root."""

        record = self._store.get_artifact(artifact_id)
        if record is None:
            return None
        resolved = record.path.expanduser().resolve()
        if resolved != self.objects and self.objects not in resolved.parents:
            return None
        if not resolved.is_file():
            return None
        return ArtifactRecord(
            id=record.id, filename=record.filename, size=record.size, path=resolved
        )

    def save_upload(self, source: BinaryIO, filename: str | None) -> ArtifactRecord:
        """Stream an upload to disk, hashing it and deduplicating by digest."""

        name = safe_filename(filename)
        suffix = safe_extension(filename)
        temp_path = self.tmp / f"{uuid.uuid4().hex}.part"
        digest = hashlib.sha256()
        total = 0
        try:
            with temp_path.open("wb") as target:
                while True:
                    chunk = source.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise ArtifactTooLarge(
                            f"upload exceeds the {self.max_bytes} byte artifact limit"
                        )
                    digest.update(chunk)
                    target.write(chunk)

            artifact_id = digest.hexdigest()
            existing = self.get(artifact_id)
            if existing is not None:
                return existing

            destination = self.objects / artifact_id[:2] / f"{artifact_id}{suffix}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp_path, destination)
            record = ArtifactRecord(id=artifact_id, filename=name, size=total, path=destination)
            stored = self._store.add_artifact(record)
            if stored.path.resolve() != destination.resolve():
                destination.unlink(missing_ok=True)
            return stored
        finally:
            temp_path.unlink(missing_ok=True)
