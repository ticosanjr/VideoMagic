#!/usr/bin/env python3
"""Cycle 1 gate: media contract, 2:1 audio fix, and remote NVENC when available."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from videoflow.adapters.ffmpeg import FFmpegAdapter  # noqa: E402
from videoflow.application.audio_finalize import finalize_audio  # noqa: E402
from videoflow.application.compute import router_from_settings  # noqa: E402
from videoflow.application.master_export import render_master  # noqa: E402
from videoflow.application.media_integrity import validate_integrity  # noqa: E402
from videoflow.application.timeline_builder import build_timeline  # noqa: E402
from videoflow.core.media_contract import (  # noqa: E402
    channel_rms,
    needs_mono_repair,
    validate_media,
)
from videoflow.domain.config import JlCutsConfig, ZoomsConfig  # noqa: E402


def run(*args: str) -> None:
    completed = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr[-1200:])


def make_source(path: Path) -> None:
    run(
        "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=12",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=12",
        "-af", "pan=stereo|c0=c0|c1=0*c0",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
        "-b:a", "192k", "-shortest", str(path),
    )


def main() -> int:
    work = Path("/tmp/opencode/vf-cycle1-gate")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    source = work / "source.mp4"
    make_source(source)

    adapter = FFmpegAdapter()
    media = adapter.probe(source)
    left, right = channel_rms(source)
    repaired = needs_mono_repair(left, right)
    result: dict[str, object] = {
        "source": str(source),
        "duration_sec": round(media.duration_frames / (media.fps_num / media.fps_den), 3),
        "left_dbfs": round(left, 3),
        "right_dbfs": round(right, 3),
        "mono_repair_channel": repaired,
        "checks": {},
    }

    started = time.perf_counter()
    audio = finalize_audio(
        source,
        work / "project",
        duration_sec=12.0,
        target_name="final.wav",
        target_lufs=-15.5,
        true_peak_db=-1.5,
    )
    result["audio"] = audio.to_dict()
    audio_report = validate_media(audio.path, "audio_master")
    result["checks"]["audio_contract"] = audio_report.ok
    result["checks"]["audio_mono_repaired"] = audio.mono_repaired

    built = build_timeline(
        media,
        [(0, 6 * 48_000), (6 * 48_000, 12 * 48_000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="alternate_cuts"),
    )
    from videoflow.domain.state import ProjectState

    project = ProjectState(
        media_info=media,
        video_segments=list(built.video_segments),
        audio_segments=list(built.audio_segments),
    )
    gate: dict[str, object] = {}
    for audio_source in ("mix", "timeline"):
        target = work / "project" / "exports" / f"youtube_{audio_source}.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        render_master(
            project,
            target,
            output=work / "project",
            audio_source=audio_source,
            fps=30,
            cfr=True,
            preset="ultrafast",
            crf=23,
        )
        elapsed = time.perf_counter() - t0
        contract = validate_media(target, "deliverable")
        integrity = validate_integrity(
            target,
            12.0,
            expected_frames=360,
            fps=30.0,
            tolerance_frames=2,
        )
        gate[audio_source] = {
            "path": str(target),
            "elapsed_sec": round(elapsed, 3),
            "contract_ok": contract.ok,
            "contract": contract.to_dict(),
            "integrity_ok": integrity.ok,
            "integrity": integrity.to_dict(),
        }
    result["checks"]["mix_contract"] = bool(gate["mix"]["contract_ok"])
    result["checks"]["timeline_contract"] = bool(gate["timeline"]["contract_ok"])
    result["checks"]["mix_drift"] = bool(gate["mix"]["integrity_ok"])
    result["checks"]["timeline_drift"] = bool(gate["timeline"]["integrity_ok"])
    result["exports"] = gate

    try:
        router = router_from_settings()
        health = router.health(force=True)
        result["worker"] = {
            "available": health.available,
            "worker_id": health.worker_id,
            "gpu_name": health.gpu_name,
            "nvenc": health.nvenc,
            "encoder": health.encoder,
            "nvenc_error": health.nvenc_error,
        }
        result["checks"]["worker_online"] = bool(health.available)
        result["checks"]["nvenc"] = bool(health.nvenc)
        if health.available and health.nvenc:
            mix_path = work / "project" / "exports" / "youtube_mix.mp4"
            t0 = time.perf_counter()
            remote = router.submit(
                "render_nvenc",
                {
                    "inputs": [str(mix_path)],
                    "params": {
                        "output_name": "youtube_nvenc.mp4",
                        "preset": "p4",
                        "tune": "hq",
                        "cq": 19,
                    },
                    "timeout_sec": 1800.0,
                },
                timeout=1800.0,
            )
            remote_path = Path(str(remote.get("path") or ""))
            remote_contract = validate_media(remote_path, "deliverable")
            remote_integrity = validate_integrity(
                remote_path,
                12.0,
                expected_frames=360,
                fps=30.0,
                tolerance_frames=2,
            )
            result["remote_nvenc"] = {
                "path": str(remote_path),
                "elapsed_sec": round(time.perf_counter() - t0, 3),
                "contract_ok": remote_contract.ok,
                "integrity_ok": remote_integrity.ok,
            }
            result["checks"]["remote_nvenc_render"] = bool(
                remote_contract.ok and remote_integrity.ok
            )
    except Exception as exc:  # noqa: BLE001
        result["worker"] = {"available": False, "error": str(exc)}
        result["checks"]["worker_online"] = False
        result["checks"]["nvenc"] = False

    result["elapsed_sec"] = round(time.perf_counter() - started, 3)
    result["ok"] = all(bool(value) for value in result["checks"].values())
    out = ROOT / "docs" / "qa-evidence" / "cycle1-gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
