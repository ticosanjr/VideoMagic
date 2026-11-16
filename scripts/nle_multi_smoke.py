#!/usr/bin/env python3
"""Build a 30-second project and export it to MP4, Resolve, Premiere, and Kdenlive.

The smoke is intentionally self-contained: it generates A-roll, B-roll, an
alpha motion graphic, captions, music, SFX, ducking, and markers with FFmpeg,
then runs the same delivery bundle the MCP exposes.

Usage:
    uv run python scripts/nle_multi_smoke.py --json-out /tmp/nle-smoke.json
    uv run python scripts/nle_multi_smoke.py --melt
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from videoflow.application.delivery_bundle import (
    DeliveryBundleRequest,
    build_delivery_bundle,
)
from videoflow.application.timeline_meta import add_marker
from videoflow.domain.state import (
    AudioSegment,
    OverlayClip,
    ProjectState,
    VideoSegment,
)


def _run(argv: list[str]) -> None:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise SystemExit("command failed: " + " ".join(argv) + "\n" + completed.stderr[-2000:])


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise SystemExit("ffmpeg is required for the NLE smoke")
    return binary


def _generate_media(directory: Path, duration: float) -> dict[str, Path]:
    ffmpeg = _ffmpeg()
    aroll = directory / "a-roll.mp4"
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1920x1080:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(aroll),
        ]
    )
    broll = directory / "b-roll.mp4"
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=1280x720:rate=30",
            "-t",
            "2.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(broll),
        ]
    )
    graphic = directory / "motion-alpha.webm"
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red@0.5:s=640x360:r=30:d=2.5",
            "-c:v",
            "libvpx-vp9",
            "-pix_fmt",
            "yuva420p",
            "-b:v",
            "0",
            "-crf",
            "30",
            str(graphic),
        ]
    )
    music = directory / "music.wav"
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:sample_rate=48000",
            "-t",
            f"{duration:.3f}",
            str(music),
        ]
    )
    master = directory / "master.wav"
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(aroll),
            "-i",
            str(music),
            "-filter_complex",
            "[1:a]volume=-18dB[bed];"
            "[0:a][bed]amix=inputs=2:duration=first:dropout_transition=0,"
            "loudnorm=I=-16.5:TP=-1.0:LRA=11[a]",
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
            str(master),
        ]
    )
    return {
        "aroll": aroll,
        "broll": broll,
        "graphic": graphic,
        "music": music,
        "master": master,
    }


def _write_sidecars(
    output: Path,
    state: ProjectState,
    media: dict[str, Path],
    *,
    duration: float,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "project_state.json").write_text(
        state.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    audio = output / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    shutil.copy2(media["master"], audio / "master.wav")
    (audio / "beatmap.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sfx_events": [
                    {
                        "path": str(media["broll"]),
                        "start_frame": 15,
                        "duration_frames": 15,
                        "gain_db": -6.0,
                    }
                ],
                "music_tracks": [
                    {
                        "path": str(media["music"]),
                        "start_frame": 0,
                        "end_frame": int(duration * 30),
                        "gain_db": -18.0,
                        "duck_under_speech": True,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (audio / "ducking.json").write_text(
        json.dumps(
            {
                "ducking": [
                    {"start_sec": 2.0, "end_sec": 6.0, "level_db": -12.0},
                    {"start_sec": 10.0, "end_sec": 14.0, "level_db": -10.0},
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "titles.ass").write_text(
        "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Olá, este é o smoke multi-NLE\n"
        "Dialogue: 0,0:00:12.00,0:00:15.00,Default,,0,0,0,,Legenda karaokê de teste\n",
        encoding="utf-8",
    )
    add_marker(output, marker_id="intro", time_sec=0.0, label="Intro")
    add_marker(output, marker_id="review", time_sec=8.0, label="Review")


def run_smoke(*, output: Path, duration: float, melt: bool) -> dict[str, object]:
    media_dir = output / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    media = _generate_media(media_dir, duration)
    probe = __import__("videoflow.adapters.ffmpeg", fromlist=["FFmpegAdapter"]).FFmpegAdapter()
    info = probe.probe(media["aroll"])
    total_frames = info.duration_frames
    samples = round(duration * info.audio_sample_rate)
    state = ProjectState(
        media_info=info,
        video_segments=[
            VideoSegment(
                clip_id="a-roll-1",
                source_in_frame=0,
                source_out_frame=total_frames,
                timeline_in_frame=0,
                timeline_out_frame=total_frames,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="a-roll-1",
                source_in_sample=0,
                source_out_sample=samples,
                timeline_in_sample=0,
                timeline_out_sample=samples,
            )
        ],
        overlays=[
            OverlayClip(
                overlay_id="broll-1",
                path=str(media["broll"]),
                start_frame=90,
                duration_frames=75,
                width_ratio=1.0,
                kind="video",
            ),
            OverlayClip(
                overlay_id="graphic-1",
                path=str(media["graphic"]),
                start_frame=300,
                duration_frames=75,
                width_ratio=0.4,
                position_x=0.8,
                position_y=0.2,
                kind="video",
            ),
        ],
    )
    _write_sidecars(output, state, media, duration=duration)
    bundle = build_delivery_bundle(
        state,
        output,
        request=DeliveryBundleRequest(
            targets=("mp4_youtube", "resolve", "premiere", "kdenlive"),
        ),
        cache_dir=output / "render" / "segments",
    )
    files = {name: str(entry["path"]) for name, entry in bundle["files"].items()}
    melt_output = ""
    if melt:
        binary = shutil.which("melt")
        if binary is None:
            raise SystemExit("--melt requested but melt is not installed")
        melt_path = output / "exports" / "timeline-melt.mp4"
        _run([binary, "-consumer", f"avformat:{melt_path}", files["kdenlive"]])
        melt_output = str(melt_path)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ok": bool(bundle.get("ok")),
        "output": str(output),
        "timeline_frames": bundle["timeline_frames"],
        "files": files,
        "melt_output": melt_output,
        "validation": bundle["validation"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--melt", action="store_true")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args(argv)
    output = (
        Path(args.output).expanduser()
        if args.output
        else Path(tempfile.mkdtemp(prefix="videoflow-nle-smoke-"))
    )
    report = run_smoke(output=output, duration=max(6.0, args.duration), melt=args.melt)
    text = json.dumps(report, indent=2) + "\n"
    if args.json_out:
        target = Path(args.json_out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
