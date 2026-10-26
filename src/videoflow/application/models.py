"""Optional local model catalog and downloader."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable
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

def _faster_entry(size: str, repo: str, size_mb: int) -> dict[str, Any]:
    base = f"https://huggingface.co/{repo}/resolve/main"
    return {
        "label": f"Faster-Whisper {size}",
        "capability": "asr",
        "used_by": ["transcribe"],
        "license": "MIT",
        "source": repo,
        "size_mb": size_mb,
        "kind": "faster-whisper",
        "target": f"faster-whisper/{size}",
        "files": [
            (f"{base}/config.json", "config.json", None),
            (f"{base}/tokenizer.json", "tokenizer.json", None),
            (f"{base}/vocabulary.txt", "vocabulary.txt", None),
            (f"{base}/model.bin", "model.bin", None),
        ],
    }


def _whisper_entry(size: str, size_mb: int) -> dict[str, Any]:
    return {
        "label": f"whisper.cpp {size}",
        "capability": "asr",
        "used_by": ["transcribe"],
        "license": "MIT",
        "source": "ggerganov/whisper.cpp",
        "size_mb": size_mb,
        "kind": "whisper",
        "target": f"whisper/ggml-{size}.bin",
        "files": [
            (
                f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{size}.bin",
                f"ggml-{size}.bin",
                None,
            )
        ],
    }


CATALOG: dict[str, dict[str, Any]] = {
    "faster-whisper-small": {
        "label": "Faster-Whisper small",
        "capability": "asr",
        "used_by": ["transcribe"],
        "license": "MIT",
        "source": "Systran/faster-whisper-small",
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
    "pyannote-diarization-3.1": {
        "label": "pyannote speaker diarization 3.1",
        "capability": "diarization",
        "used_by": ["audio.diarize"],
        "license": "model card",
        "source": "pyannote/speaker-diarization-3.1",
        "size_mb": 320,
        "kind": "pyannote",
        "target": "pyannote/speaker-diarization-3.1",
        "repo": "pyannote/speaker-diarization-3.1",
    },
    "faster-whisper-tiny": _faster_entry("tiny", "Systran/faster-whisper-tiny", 75),
    "faster-whisper-base": _faster_entry("base", "Systran/faster-whisper-base", 145),
    "faster-whisper-medium": _faster_entry("medium", "Systran/faster-whisper-medium", 1530),
    "faster-whisper-large-v3": _faster_entry(
        "large-v3", "Systran/faster-whisper-large-v3", 3090
    ),
    "whisper-base": _whisper_entry("base", 142),
    "whisper-small": _whisper_entry("small", 466),
    "whisper-medium": _whisper_entry("medium", 1500),
    "whisper-tiny": {
        "label": "whisper.cpp tiny",
        "capability": "asr",
        "used_by": ["transcribe"],
        "license": "MIT",
        "source": "ggerganov/whisper.cpp",
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


LOCAL_FILE = "models-local.json"


def _local_models() -> dict[str, dict[str, Any]]:
    path = portable_home() / LOCAL_FILE
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        str(key): dict(value)
        for key, value in payload.items()
        if isinstance(value, dict)
    }


def _entry(model_id: str) -> dict[str, Any]:
    if model_id in CATALOG:
        return CATALOG[model_id]
    local = _local_models().get(model_id)
    if local is None:
        raise StateNotReadyError(f"Unknown model: {model_id}")
    return local


def register_local_model(
    *,
    model_id: str,
    label: str,
    capability: str,
    path: str,
    kind: str = "local",
    license: str = "",
) -> dict[str, object]:
    target = Path(path).expanduser()
    if not target.exists():
        raise StateNotReadyError(f"Local model path does not exist: {target}")
    if not model_id.strip():
        raise StateNotReadyError("Model id is empty.")
    payload = _local_models()
    payload[model_id] = {
        "label": label or model_id,
        "capability": capability or "other",
        "used_by": ["local"],
        "license": license,
        "source": "local",
        "size_mb": round(target.stat().st_size / 1_000_000) if target.is_file() else 0,
        "kind": kind,
        "path": str(target),
    }
    path_file = portable_home() / LOCAL_FILE
    path_file.parent.mkdir(parents=True, exist_ok=True)
    path_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload[model_id]


def remove_local_model(model_id: str) -> None:
    payload = _local_models()
    if payload.pop(model_id, None) is None:
        raise StateNotReadyError(f"Unknown local model: {model_id}")
    path_file = portable_home() / LOCAL_FILE
    path_file.parent.mkdir(parents=True, exist_ok=True)
    path_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def verify_model(model_id: str) -> dict[str, object]:
    entry = _entry(model_id)
    if entry.get("kind") == "local":
        path = Path(str(entry.get("path") or "")).expanduser()
        return {"id": model_id, "ok": path.exists(), "path": str(path)}
    if entry.get("kind") == "pyannote":
        target = _target(model_id)
        return {"id": model_id, "ok": _installed(model_id), "path": str(target)}
    files = entry.get("files", [])
    missing: list[str] = []
    checks: list[dict[str, object]] = []
    target = _target(model_id)
    for _, name, expected in files:
        path = target / name if entry.get("kind") == "faster-whisper" else target
        exists = path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if exists else ""
        checks.append(
            {
                "file": path.name,
                "exists": exists,
                "checksum_ok": None if not expected else digest == expected,
            }
        )
        if not exists or (expected and digest != expected):
            missing.append(path.name)
    return {
        "id": model_id,
        "ok": not missing,
        "path": str(target),
        "files": checks,
        "invalid": missing,
    }


def models_dir() -> Path:
    try:
        from videoflow.application.settings import load_settings

        configured = load_settings().paths.models_dir
    except Exception:
        configured = ""
    directory = Path(configured).expanduser() if configured else portable_home() / "models"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _target(model_id: str) -> Path:
    entry = _entry(model_id)
    if entry.get("kind") == "local":
        return Path(str(entry.get("path") or "")).expanduser()
    return models_dir() / str(entry["target"])


def _installed(model_id: str) -> bool:
    target = _target(model_id)
    kind = _entry(model_id)["kind"]
    if kind == "local":
        return target.exists()
    if kind == "faster-whisper":
        return (target / "model.bin").is_file() and (target / "config.json").is_file()
    if kind == "pyannote":
        return target.is_dir() and (target / "config.yaml").is_file()
    return target.is_file()


def installed_path(model_id: str) -> Path | None:
    try:
        return _target(model_id) if _installed(model_id) else None
    except StateNotReadyError:
        return None


def list_models() -> list[dict[str, object]]:
    return [
        {
            "id": model_id,
            "label": entry["label"],
            "size_mb": entry["size_mb"],
            "kind": entry["kind"],
            "capability": entry.get("capability", "other"),
            "used_by": list(entry.get("used_by", [])),
            "license": entry.get("license", ""),
            "source": entry.get("source", ""),
            "installed": _installed(model_id),
            "path": str(_target(model_id)),
            "custom": model_id not in CATALOG,
        }
        for model_id, entry in {**CATALOG, **_local_models()}.items()
    ]


def install_model(
    model_id: str,
    *,
    allow_network: bool = True,
    progress: Callable[[int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress(max(0, min(100, int(percent))), message)
        if should_cancel is not None and should_cancel():
            from videoflow.domain.errors import JobCancelledError

            raise JobCancelledError("Model download cancelled")

    if _installed(model_id):
        report(100, "Already installed")
        return {"id": model_id, "installed": True, "path": str(_target(model_id))}
    entry = CATALOG.get(model_id) or _local_models().get(model_id)
    if entry is None:
        raise StateNotReadyError(f"Unknown model: {model_id}")
    if entry.get("kind") == "local":
        raise StateNotReadyError(
            f"Local model is missing at {_target(model_id)}: {model_id}"
        )
    target = _target(model_id)
    if entry["kind"] == "pyannote":
        if not allow_network:
            raise FilesystemError("pyannote model download requires network access.")
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise FilesystemError(
                "pyannote download needs huggingface_hub. Install the diarization extra."
            ) from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        report(5, "Downloading model snapshot")
        snapshot_download(
            repo_id=str(entry["repo"]),
            local_dir=target,
            token=os.environ.get("HF_TOKEN") or None,
        )
        report(100, "Installed")
        return {"id": model_id, "installed": True, "path": str(target)}
    is_directory = entry["kind"] == "faster-whisper"
    target.parent.mkdir(parents=True, exist_ok=True)
    if is_directory:
        target.mkdir(exist_ok=True)
    files = list(entry["files"])
    for file_index, (url, name, expected) in enumerate(files):
        report(int(file_index / max(1, len(files)) * 100), f"Downloading {name}")
        ensure_external_allowed(
            url,
            capability="model_download",
            allow_external_services=allow_network,
        )
        destination = target / name if is_directory else target
        temp = destination.with_suffix(destination.suffix + ".part")
        existing = temp.stat().st_size if temp.is_file() else 0
        digest = hashlib.sha256()
        if existing:
            with temp.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        with httpx.stream(
            "GET", url, follow_redirects=True, timeout=600.0, headers=headers
        ) as response:
            resumed = existing > 0 and response.status_code == 206
            if response.status_code >= 400 and not (
                resumed or (existing and response.status_code == 416)
            ):
                raise FilesystemError(
                    f"Model download returned HTTP {response.status_code}: {url}"
                )
            if existing and not resumed:
                existing = 0
                digest = hashlib.sha256()
            total_bytes = int(response.headers.get("content-length") or 0) + existing
            written = existing
            mode = "ab" if resumed else "wb"
            with temp.open(mode) as handle:
                for chunk in response.iter_bytes():
                    if should_cancel is not None and should_cancel():
                        from videoflow.domain.errors import JobCancelledError

                        raise JobCancelledError("Model download cancelled")
                    handle.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    if total_bytes > 0:
                        fraction = written / total_bytes
                        report(
                            int(
                                (file_index + fraction)
                                / max(1, len(files))
                                * 100
                            ),
                            f"Downloading {name}",
                        )
        if expected and digest.hexdigest() != expected:
            temp.unlink(missing_ok=True)
            raise FilesystemError(f"Checksum mismatch for {url}")
        temp.replace(destination)
    report(100, "Installed")
    return {"id": model_id, "installed": True, "path": str(target)}


def remove_model(model_id: str) -> None:
    entry = _entry(model_id)
    if entry.get("kind") == "local":
        remove_local_model(model_id)
        return
    target = _target(model_id)
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()
        target.with_suffix(target.suffix + ".part").unlink(missing_ok=True)
    else:
        raise StateNotReadyError(f"Model is not installed: {model_id}")
