"""Immutable per-artifact QA reports and regression comparison."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return slug[:60] or "artifact"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _status(report: dict[str, Any]) -> str:
    value = str(report.get("status") or "").strip().lower()
    if value in {"passed", "succeeded", "ok"}:
        return "passed"
    if value in {"failed", "error"}:
        return "failed"
    return "passed" if bool(report.get("ok")) else "needs_review"


def _metrics(report: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key in ("duration", "loudness", "caption_qa", "word_fidelity", "fps", "mode"):
        if key in report:
            metrics[key] = report[key]
    for key in ("integrated_lufs", "true_peak_dbfs", "wer", "overlap_px"):
        if key in report:
            metrics[key] = report[key]
    return metrics


class QaStore:
    """Write one report per artifact/run and keep a latest pointer."""

    def __init__(self, output: str | Path) -> None:
        self.output = Path(output).expanduser()
        self.root = self.output / "exports" / "qa"

    def directory(self, artifact_path: str | Path) -> Path:
        return self.root / _slug(Path(artifact_path).stem)

    def write(
        self,
        artifact_path: str | Path,
        report: dict[str, Any],
        *,
        run_id: str = "",
    ) -> dict[str, Any]:
        artifact = Path(artifact_path).expanduser()
        identifier = run_id.strip() or datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        directory = self.directory(artifact)
        directory.mkdir(parents=True, exist_ok=True)
        payload = dict(report)
        payload.update(
            {
                "schema_version": 1,
                "run_id": identifier,
                "artifact_path": str(artifact),
                "artifact_sha256": _sha256(artifact) if artifact.is_file() else "",
                "status": _status(payload),
                "metrics": _metrics(payload),
                "issues": list(payload.get("issues") or []),
                "degraded": bool(payload.get("degraded")),
            }
        )
        report_path = directory / f"{identifier}.json"
        report_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        latest_path = directory / "latest.json"
        latest_path.write_text(
            json.dumps(
                {
                    "run_id": identifier,
                    "report_path": str(report_path),
                    "artifact_path": str(artifact),
                    "status": payload["status"],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "run_id": identifier,
            "artifact_slug": directory.name,
            "report_path": str(report_path),
            "latest_path": str(latest_path),
            "artifact_sha256": payload["artifact_sha256"],
            "status": payload["status"],
        }

    def read(self, artifact_path: str | Path, run_id: str) -> dict[str, Any] | None:
        directory = self.directory(artifact_path)
        path = directory / f"{run_id}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    def latest(self, artifact_path: str | Path) -> dict[str, Any] | None:
        directory = self.directory(artifact_path)
        pointer = directory / "latest.json"
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        report_path = Path(str(payload.get("report_path") or ""))
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return payload
        return report if isinstance(report, dict) else payload

    def compare(self, report_a: str | Path, report_b: str | Path) -> dict[str, Any]:
        first = _load_report(report_a)
        second = _load_report(report_b)
        if first is None or second is None:
            return {
                "ok": False,
                "error_code": "qa_report_not_found",
                "message": "one or both QA reports could not be read",
            }
        left = _comparable(first)
        right = _comparable(second)
        deltas: dict[str, float] = {}
        regressions: list[str] = []
        improvements: list[str] = []
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                continue
            delta = float(right[key]) - float(left[key])
            deltas[key] = round(delta, 6)
            if key in {"wer", "overlap_px", "render_sec", "duration_frame_delta"}:
                if delta > 0:
                    regressions.append(key)
                elif delta < 0:
                    improvements.append(key)
            elif key in {"integrated_lufs"}:
                if abs(float(right[key]) + 16.0) > abs(float(left[key]) + 16.0):
                    regressions.append(key)
                elif abs(float(right[key]) + 16.0) < abs(float(left[key]) + 16.0):
                    improvements.append(key)
        return {
            "ok": True,
            "report_a": str(report_a),
            "report_b": str(report_b),
            "deltas": deltas,
            "regressions": regressions,
            "improvements": improvements,
            "status_a": first.get("status"),
            "status_b": second.get("status"),
        }


def _load_report(value: str | Path) -> dict[str, Any] | None:
    path = Path(value).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _comparable(report: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    loudness = report.get("loudness")
    if isinstance(loudness, dict):
        integrated = _number(loudness.get("integrated_lufs"))
        if integrated is not None:
            values["integrated_lufs"] = integrated
    fidelity = report.get("word_fidelity")
    if isinstance(fidelity, dict):
        wer = _number(fidelity.get("wer"))
        if wer is not None:
            values["wer"] = wer
    duration = report.get("duration")
    if isinstance(duration, dict):
        delta = _number(duration.get("frame_delta"))
        if delta is not None:
            values["duration_frame_delta"] = abs(delta)
    issues = report.get("issues")
    if isinstance(issues, list):
        overlap = 0.0
        for item in issues:
            if not isinstance(item, dict):
                continue
            value = _number(item.get("overlap_px"))
            if value is not None:
                overlap += value
        values["overlap_px"] = overlap
    metrics = report.get("metrics")
    if isinstance(metrics, dict):
        render = _number(metrics.get("render_sec"))
        if render is not None:
            values["render_sec"] = render
    return values


__all__ = ["QaStore"]
