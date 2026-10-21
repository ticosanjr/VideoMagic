"""Optional local model catalog and downloader."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import httpx

from videoflow.application.capabilities import ensure_external_allowed
from videoflow.domain.errors import FilesystemError, StateNotReadyError
from videoflow.runtime import portable_home

_FASTER_WHISPER_SMALL = (
    "https://huggingface.co/Systran/faster-whisper-small/resolve/main"
)
_WHISPER_TINY = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin"
)

CATALOG: dict[str, dict[str, Any]] = {
    "faster-whisper-small": {
        "label": "Faster-Whisper small",
        "size_mb": 484,
        "kind": "faster-whisper",
        "target": "faster-whisper/small",
        "files": [
            (f"{_FASTER_WHISPER_SMALL}/config.json", "config.json", None),
            (f"{_FASTER_WHISPER_SMALL}/tokenizer.json", "tokenizer.json", None),
            (f"{_FASTER_WHISPER_SMALL}/vocabulary.txt", "vocabulary.txt", None),
            (
                f"{_FASTER_WHISPER_SMALL}/model.bin",
                "model.bin",
                "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
            ),
        ],
    },
    "whisper-tiny": {
        "label": "whisper.cpp tiny",
        "size_mb": 75,
        "kind": "whisper",
        "target": "whisper/ggml-tiny.bin",
        "files": [
            (
                _WHISPER_TINY,
                "ggml-tiny.bin",
                "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
            )
        ],
    },
}


def models_dir() -> Path:
    directory = portable_home() / "models"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _target(model_id: str) -> Path:
    try:
        entry = CATALOG[model_id]
    except KeyError as exc:
        raise StateNotReadyError(f"Unknown model: {model_id}") from exc
    return models_dir() / str(entry["target"])


def _installed(model_id: str) -> bool:
    target = _target(model_id)
    if CATALOG[model_id]["kind"] == "faster-whisper":
        return (target / "model.bin").is_file() and (target / "config.json").is_file()
    return target.is_file()


def list_models() -> list[dict[str, object]]:
    return [
        {
            "id": model_id,
            "label": entry["label"],
            "size_mb": entry["size_mb"],
            "kind": entry["kind"],
            "installed": _installed(model_id),
            "path": str(_target(model_id)),
        }
        for model_id, entry in CATALOG.items()
    ]


def install_model(model_id: str, *, allow_network: bool = True) -> dict[str, object]:
    if _installed(model_id):
        return {"id": model_id, "installed": True, "path": str(_target(model_id))}
    entry = CATALOG.get(model_id)
    if entry is None:
        raise StateNotReadyError(f"Unknown model: {model_id}")
    target = _target(model_id)
    is_directory = entry["kind"] == "faster-whisper"
    target.parent.mkdir(parents=True, exist_ok=True)
    if is_directory:
        target.mkdir(exist_ok=True)
    for url, name, expected in entry["files"]:
        ensure_external_allowed(
            url,
            capability="model_download",
            allow_external_services=allow_network,
        )
        destination = target / name if is_directory else target
        temp = destination.with_suffix(destination.suffix + ".part")
        digest = hashlib.sha256()
        with httpx.stream(
            "GET", url, follow_redirects=True, timeout=600.0
        ) as response:
            if response.status_code >= 400:
                raise FilesystemError(
                    f"Model download returned HTTP {response.status_code}: {url}"
                )
            with temp.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
                    digest.update(chunk)
        if expected and digest.hexdigest() != expected:
            temp.unlink(missing_ok=True)
            raise FilesystemError(f"Checksum mismatch for {url}")
        temp.replace(destination)
    return {"id": model_id, "installed": True, "path": str(target)}


def remove_model(model_id: str) -> None:
    target = _target(model_id)
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()
    else:
        raise StateNotReadyError(f"Model is not installed: {model_id}")
