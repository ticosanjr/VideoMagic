"""YAMNet ONNX adapter for non-speech acoustic events.

The model is optional. When a model and a class map are present, the adapter
scores 0.96 s windows on a 0.24 s hop at 16 kHz and returns sample-aligned
events at the project rate. When they are not present the caller falls back to
the existing heuristic/AST path instead of failing the job.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.domain.errors import IngestError
from videoflow.runtime import find_yamnet_model

SAMPLE_RATE = 16_000
WINDOW_SAMPLES = 15_600  # 0.96 s
HOP_SAMPLES = 3_840  # 0.24 s

REMOVE_LABELS = {
    "cough",
    "throat clearing",
    "sneeze",
    "snort",
    "gasp",
    "knock",
    "tap",
    "thump",
}
INFORMATIONAL_LABELS = {"sigh", "breathing", "laughter"}


@dataclass(frozen=True, slots=True)
class YamnetEvent:
    label: str
    start_sample: int
    end_sample: int
    score: float
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "score": round(self.score, 4),
            "action": self.action,
            "source": "yamnet",
        }


def _default_model() -> Path:
    found = find_yamnet_model()
    return found if found is not None else Path("yamnet.onnx")


def default_labels_path(model: Path | None = None) -> Path | None:
    override = os.environ.get("VIDEOWFLOW_YAMNET_LABELS", "").strip()
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    target = model or _default_model()
    candidates = (
        target.with_suffix(".labels.json"),
        target.with_name("yamnet_labels.json"),
        target.with_name("class_map.csv"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_labels(path: Path | None) -> dict[int, str]:
    """Load a JSON list/dict or an AudioSet-style ``index,mid,label`` CSV."""

    if path is None or not path.is_file():
        raise IngestError(
            "YAMNet class labels were not found. Provide a labels JSON/CSV "
            "with VIDEOWFLOW_YAMNET_LABELS."
        )
    try:
        if path.suffix.lower() == ".csv":
            labels: dict[int, str] = {}
            with path.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.reader(handle):
                    if len(row) < 3 or not row[0].strip().isdigit():
                        continue
                    labels[int(row[0])] = row[2].strip()
            return labels
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, csv.Error) as exc:
        raise IngestError(f"Cannot read YAMNet labels {path}: {exc}") from exc
    if isinstance(payload, list):
        return {index: str(value) for index, value in enumerate(payload)}
    if isinstance(payload, dict):
        result: dict[int, str] = {}
        for key, value in payload.items():
            try:
                result[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        if result:
            return result
    raise IngestError(f"Unsupported YAMNet labels format: {path}")


class YamnetAdapter:
    def __init__(
        self,
        model: str | Path | None = None,
        *,
        labels: str | Path | None = None,
        threads: int | None = None,
    ) -> None:
        self.model = Path(model) if model is not None else _default_model()
        self.labels_path = Path(labels) if labels is not None else default_labels_path(self.model)
        self.threads = threads or max(1, min(4, os.cpu_count() or 1))
        self._session: Any | None = None
        self._labels: dict[int, str] | None = None

    @staticmethod
    def available() -> bool:
        return find_yamnet_model() is not None and _onnx_available()

    def status(self) -> dict[str, Any]:
        labels = self.labels_path is not None and self.labels_path.is_file()
        model = self.model.is_file() and _onnx_available()
        return {
            "available": model,
            "model": str(self.model),
            "labels": str(self.labels_path) if labels else "",
            "reason": "" if model and labels else (
                "model_missing" if not model else "labels_missing"
            ),
        }

    def detect(
        self,
        pcm: np.ndarray,
        *,
        sample_rate: int,
        word_spans: list[tuple[int, int, float]] | None = None,
        threshold: float = 0.45,
        low_threshold: float = 0.30,
        asr_confidence: float = 0.35,
        min_event_ms: int = 150,
        merge_gap_ms: int = 120,
    ) -> list[YamnetEvent]:
        if sample_rate <= 0:
            raise IngestError("YAMNet sample rate must be positive")
        if not 0 <= low_threshold <= threshold <= 1:
            raise IngestError("YAMNet thresholds must satisfy 0 <= low <= high <= 1")
        if min_event_ms < 0 or merge_gap_ms < 0:
            raise IngestError("YAMNet durations must not be negative")
        signal = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if signal.size == 0:
            return []
        if sample_rate != SAMPLE_RATE:
            signal = _resample(signal, sample_rate, SAMPLE_RATE)
        labels = self._load_labels()
        session = self._load_session()
        input_meta = session.get_inputs()[0]
        input_name = input_meta.name
        input_shape = tuple(getattr(input_meta, "shape", ()) or ())

        windows: list[tuple[int, int, str, float]] = []
        critical = {
            index: name.casefold()
            for index, name in labels.items()
            if name.casefold() in REMOVE_LABELS | INFORMATIONAL_LABELS
        }
        if not critical:
            raise IngestError("YAMNet label map has no supported acoustic classes")
        for start in range(0, signal.size, HOP_SAMPLES):
            chunk = signal[start : start + WINDOW_SAMPLES]
            if chunk.size == 0:
                continue
            if chunk.size < WINDOW_SAMPLES:
                chunk = np.pad(chunk, (0, WINDOW_SAMPLES - chunk.size))
            batch = chunk.reshape(1, -1)
            if len(input_shape) == 3:
                batch = batch.reshape(1, -1, 1)
            try:
                output = session.run(None, {input_name: batch})[0]
            except Exception as exc:  # pragma: no cover - runtime/model failure
                raise IngestError(f"YAMNet inference failed: {exc}") from exc
            scores = np.asarray(output, dtype=np.float64).reshape(-1)
            if scores.size <= max(critical):
                raise IngestError(
                    f"YAMNet returned {scores.size} scores; labels expect at least "
                    f"{max(critical) + 1}."
                )
            index, score = max(
                ((index, float(scores[index])) for index in critical),
                key=lambda item: item[1],
            )
            if score < low_threshold:
                continue
            windows.append((start, min(start + WINDOW_SAMPLES, signal.size), labels[index], score))

        events: list[YamnetEvent] = []
        for start, end, label, score in windows:
            label_key = label.casefold()
            if label_key not in REMOVE_LABELS | INFORMATIONAL_LABELS:
                continue
            confidence = _word_confidence(word_spans or [], start, end, SAMPLE_RATE)
            strong = score >= threshold
            weak_with_asr_gap = (
                score >= low_threshold and (confidence is None or confidence <= asr_confidence)
            )
            if not (strong or weak_with_asr_gap):
                continue
            action = "remove" if label_key in REMOVE_LABELS else "informational"
            events.append(
                YamnetEvent(
                    label=label,
                    start_sample=start,
                    end_sample=end,
                    score=score,
                    action=action,
                )
            )

        merged = _merge_events(
            events,
            sample_rate=SAMPLE_RATE,
            merge_gap_ms=merge_gap_ms,
        )
        minimum = max(1, round(SAMPLE_RATE * min_event_ms / 1000))
        merged = [event for event in merged if event.end_sample - event.start_sample >= minimum]
        scale = sample_rate / SAMPLE_RATE
        return [
            YamnetEvent(
                label=event.label,
                start_sample=round(event.start_sample * scale),
                end_sample=round(event.end_sample * scale),
                score=event.score,
                action=event.action,
            )
            for event in merged
        ]

    def _load_labels(self) -> dict[int, str]:
        if self._labels is None:
            self._labels = load_labels(self.labels_path)
        return self._labels

    def _load_session(self) -> Any:
        if self._session is not None:
            return self._session
        if not self.model.is_file():
            raise IngestError(
                f"YAMNet model was not found: {self.model}. Set VIDEOWFLOW_YAMNET_MODEL."
            )
        try:
            import onnxruntime as ort
        except (ImportError, OSError) as exc:
            raise IngestError("YAMNet requires onnxruntime.") from exc
        options = ort.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.log_severity_level = 3
        try:
            self._session = ort.InferenceSession(
                str(self.model),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:  # pragma: no cover - runtime/model failure
            raise IngestError(f"Cannot load YAMNet model {self.model}: {exc}") from exc
        return self._session


def _onnx_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


def _resample(signal: np.ndarray, source: int, target: int) -> np.ndarray:
    if source == target or signal.size == 0:
        return signal
    length = max(1, round(signal.size * target / source))
    positions = np.linspace(0, signal.size - 1, length)
    return np.interp(positions, np.arange(signal.size), signal).astype(np.float32)


def _word_confidence(
    spans: list[tuple[int, int, float]],
    start: int,
    end: int,
    sample_rate: int,
) -> float | None:
    scale = sample_rate / SAMPLE_RATE
    first = start * scale
    last = end * scale
    values = [
        probability
        for word_start, word_end, probability in spans
        if word_start < last and word_end > first
    ]
    if not values:
        return None
    return float(sum(values) / len(values))


def _merge_events(
    events: list[YamnetEvent],
    *,
    sample_rate: int,
    merge_gap_ms: int,
) -> list[YamnetEvent]:
    if not events:
        return []
    gap = max(1, round(sample_rate * merge_gap_ms / 1000))
    merged: list[YamnetEvent] = []
    for event in sorted(events, key=lambda item: (item.start_sample, item.end_sample)):
        if (
            merged
            and merged[-1].label.casefold() == event.label.casefold()
            and event.start_sample - merged[-1].end_sample <= gap
        ):
            previous = merged[-1]
            merged[-1] = YamnetEvent(
                label=previous.label,
                start_sample=previous.start_sample,
                end_sample=max(previous.end_sample, event.end_sample),
                score=max(previous.score, event.score),
                action=previous.action,
            )
        else:
            merged.append(event)
    return merged
