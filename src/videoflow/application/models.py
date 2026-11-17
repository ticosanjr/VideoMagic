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
from videoflow.runtime import external_home, model_search_dirs, portable_home

_FASTER_WHISPER_SMALL = "https://huggingface.co/Systran/faster-whisper-small/resolve/main"
_WHISPER_TINY = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin"


def _faster_entry(
    size: str,
    repo: str,
    size_mb: int,
    *,
    vocabulary: str = "vocabulary.txt",
    preprocessor: bool = False,
) -> dict[str, Any]:
    base = f"https://huggingface.co/{repo}/resolve/main"
    files = [
        (f"{base}/config.json", "config.json", None),
        (f"{base}/tokenizer.json", "tokenizer.json", None),
        (f"{base}/{vocabulary}", vocabulary, None),
        (f"{base}/model.bin", "model.bin", None),
    ]
    if preprocessor:
        files.insert(
            2,
            (f"{base}/preprocessor_config.json", "preprocessor_config.json", None),
        )
    return {
        "label": f"Faster-Whisper {size}",
        "capability": "asr",
        "used_by": ["transcribe"],
        "license": "MIT",
        "source": repo,
        "size_mb": size_mb,
        "kind": "faster-whisper",
        "target": f"faster-whisper/{size}",
        "files": files,
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
    "faster-whisper-large-v3-turbo": _faster_entry(
        "large-v3-turbo",
        "dropbox-dash/faster-whisper-large-v3-turbo",
        1618,
        vocabulary="vocabulary.json",
        preprocessor=True,
    ),
    "faster-whisper-large-v3": _faster_entry(
        "large-v3",
        "Systran/faster-whisper-large-v3",
        3090,
        vocabulary="vocabulary.json",
        preprocessor=True,
    ),
    "whisper-base": _whisper_entry("base", 142),
    "whisper-small": _whisper_entry("small", 466),
    "whisper-medium": _whisper_entry("medium", 1500),
    "whisper-large-v3-turbo-q5_0": _whisper_entry("large-v3-turbo-q5_0", 574),
    "whisper-large-v3-turbo": _whisper_entry("large-v3-turbo", 1625),
    "silero-vad": {
        "label": "Silero VAD ONNX",
        "capability": "vad",
        "used_by": ["audio.vad"],
        "license": "MIT",
        "source": "snakers4/silero-vad",
        "size_mb": 2,
        "kind": "silero",
        "target": "silero/silero_vad.onnx",
        "files": [
            (
                "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
                "silero_vad.onnx",
                None,
            )
        ],
    },
    "mediapipe-face-detector": {
        "label": "MediaPipe face detector (Tasks)",
        "capability": "vision",
        "used_by": ["shorts.reframe"],
        "license": "Apache-2.0",
        "source": "google-ai-edge/mediapipe",
        "size_mb": 1,
        "kind": "mediapipe",
        "target": "mediapipe/blaze_face_short_range.tflite",
        "files": [
            (
                "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
                "blaze_face_short_range.tflite",
                None,
            )
        ],
    },
    "mediapipe-face-landmarker": {
        "label": "MediaPipe face landmarker",
        "capability": "vision",
        "used_by": ["shorts.reframe", "vision.gaze", "qa.visual_10fps"],
        "license": "Apache-2.0",
        "source": "google-ai-edge/mediapipe",
        "size_mb": 4,
        "kind": "mediapipe",
        "target": "mediapipe/face_landmarker.task",
        "files": [
            (
                "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
                "face_landmarker.task",
                None,
            )
        ],
    },
    "mediapipe-selfie-segmenter": {
        "label": "MediaPipe selfie segmenter",
        "capability": "vision",
        "used_by": ["layout.cutout", "vision.segment"],
        "license": "Apache-2.0",
        "source": "google-ai-edge/mediapipe",
        "size_mb": 1,
        "kind": "mediapipe",
        "target": "mediapipe/selfie_segmenter.tflite",
        "files": [
            (
                "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/1/selfie_segmenter.tflite",
                "selfie_segmenter.tflite",
                None,
            )
        ],
    },
    "tesseract-eng": {
        "label": "Tesseract English data",
        "capability": "ocr",
        "used_by": ["vision.ocr", "qa.visual_10fps"],
        "license": "Apache-2.0",
        "source": "tesseract-ocr/tessdata_fast",
        "size_mb": 5,
        "kind": "tesseract",
        "target": "tesseract/eng.traineddata",
        "files": [
            (
                "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata",
                "eng.traineddata",
                None,
            )
        ],
    },
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
    path = external_home() / LOCAL_FILE
    if not path.is_file():
        legacy = portable_home() / LOCAL_FILE
        if legacy.is_file():
            path = legacy
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)}


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
    path_file = external_home() / LOCAL_FILE
    path_file.parent.mkdir(parents=True, exist_ok=True)
    path_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload[model_id]


def remove_local_model(model_id: str) -> None:
    payload = _local_models()
    if payload.pop(model_id, None) is None:
        raise StateNotReadyError(f"Unknown local model: {model_id}")
    path_file = external_home() / LOCAL_FILE
    path_file.parent.mkdir(parents=True, exist_ok=True)
    path_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def verify_model(model_id: str) -> dict[str, object]:
    entry = _entry(model_id)
    if entry.get("kind") == "local":
        path = Path(str(entry.get("path") or "")).expanduser()
        return {"id": model_id, "ok": path.exists(), "path": str(path)}
    found = installed_path(model_id)
    target = found or _target(model_id)
    search_paths = [str(root) for root in model_roots()]
    if entry.get("kind") == "pyannote":
        return {
            "id": model_id,
            "ok": found is not None,
            "path": str(target),
            "search_paths": search_paths,
        }
    files = entry.get("files", [])
    missing: list[str] = []
    checks: list[dict[str, object]] = []
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
        "search_paths": search_paths,
        "files": checks,
        "invalid": missing,
    }


def models_dir() -> Path:
    """Preferred directory for new downloads.

    Frozen builds keep ``portable_home()`` inside the release folder. Download
    to the persistent external home by default so replacing a release does not
    require downloading the same model again. An explicit setting or
    ``VIDEOWFLOW_MODELS_DIR`` still wins, and a non-writable external location
    falls back to the portable directory.
    """

    try:
        from videoflow.application.settings import load_settings

        configured = load_settings().paths.models_dir
    except Exception:
        configured = ""
    if configured:
        directory = Path(configured).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    raw = os.environ.get("VIDEOWFLOW_MODELS_DIR", "")
    if raw:
        directory = Path(raw).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    external_override = os.environ.get("VIDEOWFLOW_EXTERNAL_HOME", "")
    external_root = (
        Path(external_override).expanduser() if external_override else Path.home() / ".videoflow"
    )
    external = external_root / "models"
    try:
        external.mkdir(parents=True, exist_ok=True)
        return external
    except OSError:
        directory = portable_home() / "models"
        directory.mkdir(parents=True, exist_ok=True)
        return directory


def model_roots() -> list[Path]:
    """All roots checked for an installed model, preferred install path first."""

    roots: list[Path] = [models_dir(), *model_search_dirs(), portable_home() / "models"]
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def _target(model_id: str) -> Path:
    entry = _entry(model_id)
    if entry.get("kind") == "local":
        return Path(str(entry.get("path") or "")).expanduser()
    return models_dir() / str(entry["target"])


def _candidates(model_id: str) -> list[Path]:
    entry = _entry(model_id)
    if entry.get("kind") == "local":
        return [Path(str(entry.get("path") or "")).expanduser()]
    return [root / str(entry["target"]) for root in model_roots()]


def _is_model_path(path: Path, kind: str) -> bool:
    if kind == "local":
        return path.exists()
    if kind == "faster-whisper":
        return (path / "model.bin").is_file() and (path / "config.json").is_file()
    if kind == "pyannote":
        return path.is_dir() and (path / "config.yaml").is_file()
    return path.is_file()


def _installed(model_id: str) -> bool:
    kind = _entry(model_id)["kind"]
    return any(_is_model_path(path, kind) for path in _candidates(model_id))


def installed_path(model_id: str) -> Path | None:
    try:
        kind = _entry(model_id)["kind"]
    except StateNotReadyError:
        return None
    for path in _candidates(model_id):
        if _is_model_path(path, kind):
            return path
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
            "path": str(installed_path(model_id) or _target(model_id)),
            "search_paths": [str(root) for root in model_roots()],
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
        return {
            "id": model_id,
            "installed": True,
            "path": str(installed_path(model_id) or _target(model_id)),
        }
    entry = CATALOG.get(model_id) or _local_models().get(model_id)
    if entry is None:
        raise StateNotReadyError(f"Unknown model: {model_id}")
    if entry.get("kind") == "local":
        raise StateNotReadyError(f"Local model is missing at {_target(model_id)}: {model_id}")
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
                raise FilesystemError(f"Model download returned HTTP {response.status_code}: {url}")
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
                            int((file_index + fraction) / max(1, len(files)) * 100),
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
    kind = entry["kind"]
    removed = False
    for target in _candidates(model_id):
        if kind in {"faster-whisper", "pyannote"} and target.is_dir():
            shutil.rmtree(target)
            removed = True
        elif target.exists():
            target.unlink(missing_ok=True)
            target.with_suffix(target.suffix + ".part").unlink(missing_ok=True)
            removed = True
    if not removed:
        raise StateNotReadyError(f"Model is not installed: {model_id}")


def update_model(
    model_id: str,
    *,
    allow_network: bool = True,
    progress: Callable[[int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Reinstall an installed model so it can be refreshed/updated."""

    if installed_path(model_id) is not None:
        remove_model(model_id)
    return install_model(
        model_id,
        allow_network=allow_network,
        progress=progress,
        should_cancel=should_cancel,
    )
