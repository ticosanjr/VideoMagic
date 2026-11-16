#!/usr/bin/env python3
"""Exercise the remote GPU worker: health, ASR, upscale, and local fallback.

This smoke needs the Windows GPU host online. It uploads one media artifact,
runs ``asr`` and ``upscale``, downloads both results, and verifies that the
router falls back to local when the worker is unreachable.

Usage:
    uv run python scripts/gpu_worker_smoke.py \
      --url http://192.168.1.20:8766 --token "$VF_GPU_WORKER_TOKEN"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from vf_compute import ComputeRouter, GPUWorkerClient


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise SystemExit("ffmpeg is required to generate the smoke media")
    return binary


def _sample_media(directory: Path) -> Path:
    target = directory / "smoke.wav"
    if target.is_file():
        return target
    completed = subprocess.run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "2",
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        raise SystemExit("could not generate the smoke audio: " + completed.stderr[-1000:])
    return target


def _run_job(
    client: GPUWorkerClient,
    capability: str,
    *,
    artifact_id: str,
    params: dict[str, object],
    directory: Path,
) -> dict[str, object]:
    job_id = client.submit(capability, params=params, inputs=[artifact_id])
    status = client.wait(job_id, timeout=1800.0)
    downloaded: list[str] = []
    if status.ok:
        for name in status.artifacts:
            target = directory / f"{capability}-{Path(name).name}"
            client.download(job_id, name, target)
            downloaded.append(str(target))
    return {
        "capability": capability,
        "job_id": job_id,
        "state": status.state,
        "ok": status.ok,
        "error": status.error or "",
        "artifacts": status.artifacts,
        "downloaded": downloaded,
    }


def run_smoke(
    *,
    url: str,
    token: str,
    directory: Path,
    check_fallback: bool,
) -> dict[str, object]:
    media = _sample_media(directory)
    report: dict[str, object] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "url": url,
        "media": str(media),
        "health": {},
        "jobs": [],
        "fallback": {},
    }
    with GPUWorkerClient(url, token) as client:
        health = client.health(timeout=10.0)
        report["health"] = health.model_dump()
        if not health.available:
            report["ok"] = False
            report["error"] = health.message or "worker is not available"
            return report
        missing = [name for name in ("asr", "upscale") if name not in health.capabilities]
        if missing:
            report["ok"] = False
            report["error"] = "worker is missing capabilities: " + ", ".join(missing)
            return report
        artifact_id = client.upload_artifact(media)
        jobs = [
            _run_job(
                client,
                "asr",
                artifact_id=artifact_id,
                params={"language": "pt", "output_name": "transcript.json"},
                directory=directory,
            ),
            _run_job(
                client,
                "upscale",
                artifact_id=artifact_id,
                params={"scale": 2, "is_video": False, "output_name": "upscaled.png"},
                directory=directory,
            ),
        ]
    report["jobs"] = jobs

    if check_fallback:
        router = ComputeRouter(
            mode="remote_preferred",
            worker_url="http://127.0.0.1:1",
            health_ttl=0.0,
            health_timeout=0.2,
            circuit_sec=1.0,
        )
        decision = router.decide("asr")
        report["fallback"] = decision.model_dump()

    ok = all(bool(job["ok"]) and bool(job["downloaded"]) for job in jobs)
    if check_fallback:
        ok = ok and report["fallback"].get("mode") == "local"
    report["ok"] = ok
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("VF_GPU_WORKER_URL", ""))
    parser.add_argument("--token", default=os.environ.get("VF_GPU_WORKER_TOKEN", ""))
    parser.add_argument("--output", default="")
    parser.add_argument("--json-out", default="")
    parser.add_argument(
        "--check-fallback",
        action="store_true",
        help="Verify the router chooses local when the worker is unreachable.",
    )
    args = parser.parse_args(argv)
    if not args.url:
        raise SystemExit("pass --url or set VF_GPU_WORKER_URL")
    directory = (
        Path(args.output).expanduser()
        if args.output
        else Path(tempfile.mkdtemp(prefix="videoflow-gpu-smoke-"))
    )
    directory.mkdir(parents=True, exist_ok=True)
    report = run_smoke(
        url=args.url.rstrip("/"),
        token=args.token,
        directory=directory,
        check_fallback=args.check_fallback,
    )
    text = json.dumps(report, indent=2) + "\n"
    if args.json_out:
        target = Path(args.json_out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
