#!/usr/bin/env python
"""Measure a real Windows/NVIDIA GPU worker for the 3.6.0 acceptance gate.

The script never fabricates a speedup. Missing media or an unreachable worker
produces ``blocked``; a measured threshold miss produces ``failed``.

Usage:
    uv run python scripts/gpu_acceptance.py \
      --worker-url http://192.168.1.45:8766 \
      --token "$VF_GPU_WORKER_TOKEN" \
      --asr-audio samples/25min.wav \
      --nvenc-video samples/11min.mp4 \
      --matte-input samples/matte-3s.mp4 \
      --json-out docs/qa-evidence/3.6.0-gpu.json \
      --markdown-out docs/performance-3.5.md
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vf_shared.compute import GPUWorkerClient
from vf_shared.compute.discovery import discover_workers, scan_workers


def _videoflow_version() -> str:
    try:
        from videoflow import __version__
    except Exception:  # noqa: BLE001 - acceptance must report, not crash
        return "unknown"
    return __version__


def _duration_sec(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return 0.0
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return max(0.0, float(completed.stdout.strip() or 0.0))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def _measure(
    client: GPUWorkerClient,
    capability: str,
    *,
    media: Path,
    params: dict[str, Any],
    timeout_sec: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    artifact = client.upload_artifact(media)
    job_id = client.submit(capability, params=params, inputs=[artifact])
    status = client.wait(job_id, timeout=timeout_sec)
    elapsed = time.perf_counter() - started
    return {
        "ok": bool(status.ok),
        "job_id": job_id,
        "state": status.state,
        "elapsed_sec": round(elapsed, 3),
        "artifacts": list(status.artifacts),
        "error": status.error or status.message,
    }


def _asr_check(client: GPUWorkerClient, media: Path | None) -> dict[str, Any]:
    if media is None or not media.is_file():
        return {"ok": False, "skipped": "pass --asr-audio with a real audio file"}
    duration = _duration_sec(media)
    result = _measure(
        client,
        "asr",
        media=media,
        params={
            "model": "large-v3-turbo",
            "language": "pt",
            "compute_type": "float16",
            "word_timestamps": True,
        },
        timeout_sec=900,
    )
    result["media_sec"] = round(duration, 2)
    result["speedup"] = round(duration / max(0.001, result["elapsed_sec"]), 2)
    result["threshold_sec"] = 45 if duration >= 1500 else None
    result["passed"] = bool(
        result["ok"]
        and (duration < 1500 or result["elapsed_sec"] <= result["threshold_sec"])
    )
    return result


def _nvenc_check(client: GPUWorkerClient, media: Path | None) -> dict[str, Any]:
    if media is None or not media.is_file():
        return {"ok": False, "skipped": "pass --nvenc-video with a real video file"}
    duration = _duration_sec(media)
    result = _measure(
        client,
        "render_nvenc",
        media=media,
        params={"fps": 30, "cq": 20, "preset": "p4", "duration": duration or None},
        timeout_sec=1800,
    )
    result["media_sec"] = round(duration, 2)
    result["speedup"] = round(duration / max(0.001, result["elapsed_sec"]), 2)
    result["threshold_sec"] = 240 if duration >= 600 else None
    result["passed"] = bool(
        result["ok"]
        and (duration < 600 or result["elapsed_sec"] <= result["threshold_sec"])
    )
    return result


def _matte_check(client: GPUWorkerClient, media: Path | None) -> dict[str, Any]:
    if media is None or not media.is_file():
        return {"ok": False, "skipped": "pass --matte-input with a short clip or image"}
    duration = _duration_sec(media)
    result = _measure(
        client,
        "segment_matte",
        media=media,
        params={"fps": 30},
        timeout_sec=300,
    )
    result["media_sec"] = round(duration, 2)
    result["speedup"] = round(duration / max(0.001, result["elapsed_sec"]), 2)
    result["threshold_sec"] = 5.0
    result["passed"] = bool(result["ok"] and result["elapsed_sec"] <= 5.0)
    return result


def _markdown(payload: dict[str, Any]) -> str:
    worker = payload.get("worker", {})
    lines = [
        f"# GPU acceptance — {payload['version']}",
        "",
        f"Generated: {payload['generated_at']}",
        f"Status: **{payload['status']}**",
        "",
        "## Worker",
        "",
        f"- GPU: `{worker.get('gpu_name', '')}`",
        f"- Host: `{worker.get('hostname', '')}`",
        f"- Worker: `{worker.get('worker_id', '')}`",
        f"- VRAM: {worker.get('vram_total_mb', 0)} MB",
        f"- Capabilities: {', '.join(worker.get('capabilities', []))}",
        "",
        "## Measurements",
        "",
        "| Check | State | Media | Elapsed | Speedup | Threshold |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for name, check in payload.get("checks", {}).items():
        state = "passed" if check.get("passed") else check.get("skipped", "failed")
        lines.append(
            f"| {name} | {state} | {check.get('media_sec', '')} s | "
            f"{check.get('elapsed_sec', '')} s | {check.get('speedup', '')}× | "
            f"{check.get('threshold_sec', '')} |"
        )
    lines.append("")
    lines.append(
        "A passing file requires a real Windows worker with NVIDIA NVENC and "
        "CUDA. Simulated tests do not replace this evidence."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-url", default=os.environ.get("VF_GPU_WORKER_URL", ""))
    parser.add_argument("--token", default=os.environ.get("VF_GPU_WORKER_TOKEN", ""))
    parser.add_argument("--asr-audio", type=Path, default=None)
    parser.add_argument("--nvenc-video", type=Path, default=None)
    parser.add_argument("--matte-input", type=Path, default=None)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument(
        "--require-nvenc",
        action="store_true",
        help="Fail when the worker does not expose a working h264_nvenc encoder.",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--markdown-out", type=Path, default=None)
    args = parser.parse_args()

    payload: dict[str, Any] = {
        "schema_version": 1,
        "version": _videoflow_version(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "worker_url": args.worker_url,
        "worker": {},
        "checks": {},
        "discovery": [],
        "status": "blocked",
    }
    if not args.worker_url and args.discover:
        peers = discover_workers(timeout_sec=2.0)
        if not peers:
            peers = scan_workers(port=8766)
        payload["discovery"] = peers
        args.worker_url = str((peers[0] if peers else {}).get("url") or "")
    payload["worker_url"] = args.worker_url
    if not args.worker_url:
        payload["message"] = "No --worker-url was provided and discovery found no worker."
    else:
        try:
            client = GPUWorkerClient(args.worker_url, args.token, timeout=15.0)
            health = client.health(timeout=5.0)
            payload["worker"] = health.model_dump(mode="json")
            if not health.available:
                payload["message"] = health.message or "Worker is not available."
            elif args.require_nvenc and not bool(getattr(health, "nvenc", False)):
                payload["status"] = "failed"
                payload["message"] = (
                    "NVENC is required but unavailable: "
                    + (getattr(health, "encoder", "") or "unknown")
                )
            else:
                payload["checks"]["asr"] = _asr_check(client, args.asr_audio)
                payload["checks"]["nvenc"] = _nvenc_check(client, args.nvenc_video)
                payload["checks"]["matte"] = _matte_check(client, args.matte_input)
                if args.discover:
                    peers = discover_workers(timeout_sec=2.0)
                    payload["discovery"] = peers
                checks = payload["checks"].values()
                if any(check.get("ok") and not check.get("passed") for check in checks):
                    payload["status"] = "failed"
                elif all(check.get("passed") for check in checks) and len(payload["checks"]) == 3:
                    payload["status"] = "passed"
                else:
                    payload["status"] = "blocked"
                    payload["message"] = "One or more real media measurements are missing."
        except Exception as exc:  # noqa: BLE001 - acceptance must report, not crash
            payload["message"] = str(exc)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.markdown_out is not None:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "passed" else 2 if payload["status"] == "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
