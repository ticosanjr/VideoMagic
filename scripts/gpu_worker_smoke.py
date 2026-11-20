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
import sys
import tempfile
import threading
import time
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


def run_local_worker(
    *,
    token: str,
    directory: Path,
    port: int,
) -> dict[str, object]:
    """Run the real worker HTTP app in-process with deterministic handlers."""

    import uvicorn

    root = Path(__file__).resolve().parents[1]
    package_src = root / "packages" / "gpu-worker" / "src"
    if str(package_src) not in sys.path:
        sys.path.insert(0, str(package_src))
    from gpu_worker.app import create_app
    from gpu_worker.settings import Settings

    app = create_app(
        Settings(
            token=token,
            work_dir=directory / "worker",
            max_upload_mb=64,
            max_queue=4,
        )
    )

    def asr(params, inputs, work_dir):
        target = work_dir / str(params.get("output_name") or "transcript.json")
        target.write_text(
            json.dumps(
                {
                    "version": 1,
                    "language": str(params.get("language") or "pt"),
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "text": "smoke local",
                            "words": [
                                {"word": "smoke", "start": 0.0, "end": 0.5},
                                {"word": "local", "start": 0.5, "end": 1.0},
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return [target]

    def upscale(params, inputs, work_dir):
        target = work_dir / str(params.get("output_name") or "upscaled.png")
        target.write_bytes(b"PNG")
        return [target]

    app.state.registry.register_handler("asr", asr)
    app.state.registry.register_handler("upscale", upscale)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    try:
        with GPUWorkerClient(url, token) as client:
            for _ in range(100):
                try:
                    if client.health(timeout=0.5).available:
                        break
                except Exception:  # noqa: BLE001 - server is still starting
                    time.sleep(0.05)
            else:
                raise SystemExit("local GPU worker did not start")
        report = run_smoke(
            url=url,
            token=token,
            directory=directory,
            check_fallback=True,
            check_jobs=True,
        )
        report["mode"] = "local"
        return report
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)
        app.state.close()


def discover_url(*, timeout: float = 3.0) -> str:
    """Find a LAN worker through UDP, then the active TCP subnet scan."""

    from vf_compute.discovery import discover_workers, scan_workers

    peers = discover_workers(timeout_sec=min(max(timeout, 0.5), 5.0))
    if not peers:
        peers = scan_workers(port=8766)
    for peer in peers:
        url = str(peer.get("url") or "")
        if url:
            return url
    return ""


def run_smoke(
    *,
    url: str,
    token: str,
    directory: Path,
    check_fallback: bool,
    check_jobs: bool = True,
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
        try:
            report["overview"] = client.overview(timeout=5.0)
        except Exception as exc:  # noqa: BLE001 - dashboard is advisory
            report["overview"] = {"ok": False, "error": str(exc)}
        if not check_jobs:
            report["ok"] = bool(report["overview"].get("ok", False))
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
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run the worker HTTP app locally with deterministic handlers.",
    )
    parser.add_argument("--local-port", type=int, default=8799)
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Find the worker through UDP/TCP discovery instead of --url.",
    )
    parser.add_argument(
        "--skip-jobs",
        action="store_true",
        help="Only check health/overview/dashboard, without media jobs.",
    )
    parser.add_argument("--output", default="")
    parser.add_argument("--json-out", default="")
    parser.add_argument(
        "--check-fallback",
        action="store_true",
        help="Verify the router chooses local when the worker is unreachable.",
    )
    args = parser.parse_args(argv)
    if not args.local and args.discover:
        args.url = discover_url()
        if not args.url:
            raise SystemExit("no worker discovered on the LAN")
    if not args.local and not args.url:
        raise SystemExit("pass --url, set VF_GPU_WORKER_URL, --discover, or use --local")
    directory = (
        Path(args.output).expanduser()
        if args.output
        else Path(tempfile.mkdtemp(prefix="videoflow-gpu-smoke-"))
    )
    directory.mkdir(parents=True, exist_ok=True)
    if args.local:
        report = run_local_worker(
            token=args.token or "local-smoke",
            directory=directory,
            port=args.local_port,
        )
    else:
        report = run_smoke(
            url=args.url.rstrip("/"),
            token=args.token,
            directory=directory,
            check_fallback=args.check_fallback,
            check_jobs=not args.skip_jobs,
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
