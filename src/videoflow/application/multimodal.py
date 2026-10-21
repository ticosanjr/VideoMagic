"""Optional audio-emotion and visual-motion analysis for a rendered Short."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from videoflow.application.tracking import frames_from_pieces
from videoflow.domain.errors import IngestError, ShortEditError, StateNotReadyError
from videoflow.runtime import find_binary


def audio_features(samples: np.ndarray, sample_rate: int) -> dict[str, object]:
    if len(samples) == 0 or sample_rate <= 0:
        return {"label": "unknown", "rms": 0.0, "zcr": 0.0, "variation": 0.0}
    values = samples.astype(np.float64)
    window = max(1, sample_rate // 10)
    count = len(values) // window
    if count == 0:
        return {"label": "unknown", "rms": 0.0, "zcr": 0.0, "variation": 0.0}
    rows = values[: count * window].reshape(count, window)
    rms_values = np.sqrt((rows * rows).mean(axis=1))
    rms = float(rms_values.mean() / 32768.0)
    zcr = float(np.abs(np.diff(np.signbit(rows).astype(np.int8), axis=1)).mean())
    variation = float(rms_values.std() / max(1.0, rms_values.mean()))
    if variation >= 0.45:
        label = "expressive"
    elif rms <= 0.03 and zcr <= 0.08:
        label = "calm"
    elif rms >= 0.12:
        label = "energetic"
    else:
        label = "neutral"
    return {
        "label": label,
        "rms": round(rms, 4),
        "zcr": round(zcr, 4),
        "variation": round(variation, 4),
    }


def motion_region(frames: np.ndarray) -> dict[str, float] | None:
    if frames.ndim != 3 or frames.shape[0] < 2:
        return None
    difference = np.abs(np.diff(frames.astype(np.int16), axis=0))
    mask = difference > 18
    rows, columns = np.where(mask.any(axis=0))
    if len(rows) == 0 or len(columns) == 0:
        return None
    height, width = frames.shape[1], frames.shape[2]
    return {
        "x": round(float(columns.mean()) / width, 4),
        "y": round(float(rows.mean()) / height, 4),
        "coverage": round(float(mask.mean()), 4),
    }


def analyze_short(path: Path) -> dict[str, object]:
    source = Path(path).expanduser()
    if not source.is_file():
        raise IngestError(f"Short does not exist: {source}")
    frames = frames_from_pieces(source, [(0, _duration_samples(source, 8000))], 8000)
    audio = _audio_samples(source)
    visual: dict[str, object] = {
        "motion": motion_region(frames),
        "face_count": None,
        "face_focus_x": None,
        "provider": "motion",
    }
    try:
        import cv2  # type: ignore[import-not-found]

        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(str(cascade_path))
        faces: list[float] = []
        for frame in frames[:: max(1, len(frames) // 20)]:
            for x, _y, width, _height in detector.detectMultiScale(
                frame, scaleFactor=1.1, minNeighbors=4
            ):
                faces.append((x + width / 2) / frame.shape[1])
        visual.update(
            {
                "face_count": len(faces),
                "face_focus_x": (
                    round(max(0.05, min(0.95, sum(faces) / len(faces))), 4)
                    if faces
                    else None
                ),
                "provider": "opencv_face",
            }
        )
    except ImportError:
        pass
    return {
        "audio": audio_features(audio, 16000),
        "visual": visual,
        "caveats": [
            "Audio labels are signal heuristics, not a trained emotion classifier.",
            "Visual motion is frame-difference based; object classes are not recognized.",
        ],
    }


def analyze_short_entry(
    *, output: Path, index: int, result: dict[str, object]
) -> dict[str, object]:
    shorts = result.get("shorts")
    if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
        raise ShortEditError(f"Short index {index} is out of range.")
    entry = shorts[index]
    if not isinstance(entry, dict) or not entry.get("path"):
        raise ShortEditError("Short asset is missing.")
    analysis = analyze_short(Path(str(entry["path"])))
    entry["analysis"] = analysis
    output = output.expanduser().resolve()
    path = output / "shorts.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateNotReadyError(f"Cannot read Shorts report: {exc}") from exc
    clips = report.get("clips")
    if isinstance(clips, list) and 0 <= index < len(clips):
        clips[index] = entry
    path.write_text(
        json.dumps({"ok": True, "clips": clips if isinstance(clips, list) else shorts}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return analysis


def _duration_samples(source: Path, sample_rate: int) -> int:
    binary = find_binary("ffprobe")
    if binary is None:
        raise IngestError("FFprobe is not available for analysis.")
    result = subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(source),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        return max(1, round(float(result.stdout.strip()) * sample_rate))
    except ValueError as exc:
        raise IngestError("Cannot determine Short duration.") from exc


def _audio_samples(source: Path) -> np.ndarray:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise IngestError("FFmpeg is not available for analysis.")
    result = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "s16le",
            "-",
        ],
        check=False,
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0 or not result.stdout:
        raise IngestError("Cannot decode Short audio.")
    return np.frombuffer(result.stdout, dtype=np.int16)
