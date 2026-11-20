#!/usr/bin/env python
"""Acceptance checks for VideoFlow 3.3.0.

The script keeps optional backends honest: checks that need ffmpeg, Pillow, or a
GPU are either executed or reported as skipped with a reason. It never marks a
skipped backend as passed.

Usage:
    uv run python scripts/acceptance_3_3.py
    uv run python scripts/acceptance_3_3.py --bench-seconds 60 --json-out /tmp/acceptance.json
    uv run python scripts/acceptance_3_3.py --bench-seconds 660 --segments 11
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RATE = 48_000


def _word(text: str, start_ms: int, end_ms: int, probability: float = 0.9):
    from videoflow.domain.state import WordTiming

    return WordTiming(
        word=text,
        start_sample=round(start_ms * RATE / 1000),
        end_sample=round(end_ms * RATE / 1000),
        probability=probability,
    )


def _sentence(identifier: int, text: str, start_ms: int, end_ms: int, words):
    from videoflow.domain.state import Sentence

    return Sentence(
        id=identifier,
        start_sample=round(start_ms * RATE / 1000),
        end_sample=round(end_ms * RATE / 1000),
        text=text,
        words=words,
    )


def check_editorial() -> dict[str, Any]:
    from videoflow.application.editorial_clean import clean_editorial

    sentences = [
        _sentence(
            0,
            "Hoje eu vou mostrar como instalar o modelo.",
            0,
            1200,
            [
                _word("Hoje", 0, 150),
                _word("eu", 160, 240),
                _word("vou", 250, 360),
                _word("mostrar", 370, 620),
                _word("como", 630, 760),
                _word("instalar", 770, 980),
                _word("o", 990, 1030),
                _word("modelo.", 1040, 1200),
            ],
        ),
        _sentence(
            1,
            "e o o o modelo",
            1300,
            2100,
            [
                _word("e", 1300, 1360),
                _word("o", 1370, 1430),
                _word("o", 1450, 1510),
                _word("o", 1530, 1590),
                _word("modelo", 1600, 2100),
            ],
        ),
        _sentence(
            2,
            "Neste vídeo você vai aprender o passo a passo para instalar.",
            2200,
            3800,
            [
                _word("Neste", 2200, 2350),
                _word("vídeo", 2360, 2520),
                _word("você", 2530, 2660),
                _word("vai", 2670, 2780),
                _word("aprender", 2790, 3000),
                _word("o", 3010, 3050),
                _word("passo", 3060, 3220),
                _word("a", 3230, 3260),
                _word("passo", 3270, 3430),
                _word("para", 3440, 3560),
                _word("instalar.", 3570, 3800),
            ],
        ),
        _sentence(
            3,
            "Hoje eu vou mostrar como instalar o modelo.",
            4000,
            5200,
            [
                _word("Hoje", 4000, 4150),
                _word("eu", 4160, 4240),
                _word("vou", 4250, 4360),
                _word("mostrar", 4370, 4620),
                _word("como", 4630, 4760),
                _word("instalar", 4770, 4980),
                _word("o", 4990, 5030),
                _word("modelo.", 5040, 5200),
            ],
        ),
    ]
    result = clean_editorial(sentences, semantic=False)
    report = result.report
    kept = " ".join(sentence.text for sentence in result.transcript)
    ok = (
        report["clipped_words"] == 0
        and report["stutters_removed"] >= 1
        and 0 in report["discarded_sentence_ids"]
        and bool(result.transcript)
        and result.transcript[-1].text.startswith("Hoje eu vou mostrar")
        and "passo a passo" in kept
        and "e o o o modelo" not in kept
    )
    return {
        "ok": ok,
        "stutters_removed": report["stutters_removed"],
        "words_removed": report["words_removed"],
        "clipped_words": report["clipped_words"],
        "sentence_discards": report["discarded_sentence_ids"],
        "kept": kept,
        "warnings": report.get("warnings", []),
    }


def check_shorts() -> dict[str, Any]:
    from videoflow.application.shorts import short_dimensions
    from videoflow.application.style_catalog import StyleCatalog

    selected = [
        "sr-depth-3d-viral",
        "sr-kinetic-3beat-explainer",
        "sr-screen-demo-saas",
        "sr-founder-rant-raw",
        "sr-x-native-video-card",
    ]
    catalog = StyleCatalog()
    checks: list[dict[str, Any]] = []
    ok = True
    for style_id in selected:
        style = catalog.get(style_id)
        aspect = style.aspect_ratio or "9:16"
        width, height = short_dimensions(aspect)
        even = width % 2 == 0 and height % 2 == 0
        checks.append(
            {
                "style_id": style_id,
                "aspect_ratio": aspect,
                "width": width,
                "height": height,
                "layout_mode": style.layout_mode,
                "even": even,
            }
        )
        ok = ok and even and width > 0 and height > 0
    return {"ok": ok, "styles": checks}


def check_compositors() -> dict[str, Any]:
    from videoflow.mcp_server.registry import TOOL_SPECS

    names = {spec.name for spec in TOOL_SPECS}
    required = {
        "vf_depth_composite",
        "vf_pip",
        "vf_parallax",
        "vf_style_preview",
    }
    return {
        "ok": required <= names and len(TOOL_SPECS) == 35,
        "missing": sorted(required - names),
        "tool_count": len(TOOL_SPECS),
    }


def check_alpha(work: Path) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return {"ok": False, "skipped": "ffmpeg is not on PATH"}
    try:
        from PIL import Image  # noqa: F401
    except Exception:  # noqa: BLE001
        return {"ok": False, "skipped": "Pillow is not installed"}

    from videoflow.application.compositor import picture_in_picture
    from videoflow.application.projects import (
        init_project,
        load_project_state,
        project_uuid,
        save_project_state,
    )
    from videoflow.domain.state import MediaInfo, ProjectState

    asset = work / "acceptance_alpha.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30",
            "-t",
            "0.6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(asset),
        ],
        check=True,
    )
    record, _state = init_project(
        project_id="acceptance-alpha",
        name="Acceptance Alpha",
        output=work / "alpha-project",
    )
    media = MediaInfo(
        source_path=str(asset),
        duration_frames=18,
        fps_num=30,
        fps_den=1,
        width=1080,
        height=1920,
        audio_sample_rate=RATE,
    )
    state = ProjectState(
        project_id=project_uuid(record.project_id),
        media_info=media,
        sources={"src1": media},
        primary_source_id="src1",
    )
    save_project_state(record, state, bump_revision=False)
    result = picture_in_picture(record.project_id, str(asset), 0.0, 0.5, width_ratio=0.4)
    output = Path(result["asset"])
    frame = work / "acceptance-alpha.png"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-c:v",
            "libvpx-vp9",
            "-i",
            str(output),
            "-frames:v",
            "1",
            str(frame),
        ],
        check=True,
    )
    from PIL import Image

    alpha = Image.open(frame).getchannel("A").getextrema()
    saved = load_project_state(record)
    return {
        "ok": output.is_file() and alpha == (0, 255) and saved.overlays[-1].z == 25,
        "asset": str(output),
        "alpha": list(alpha),
        "z": saved.overlays[-1].z,
    }


def _make_bench_source(work: Path, seconds: float) -> tuple[Path, float, float]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is not on PATH")
    source = work / "benchmark.mp4"
    started = time.perf_counter()
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=1920x1080:rate=30:duration={seconds:.3f}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={seconds:.3f}",
            "-t",
            f"{seconds:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(source),
        ],
        check=True,
    )
    return source, seconds, time.perf_counter() - started


def _bench_state(source: Path, seconds: float, segments: int):
    from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment

    frames = max(1, round(seconds * 30))
    media = MediaInfo(
        source_path=str(source),
        duration_frames=frames,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=RATE,
    )
    count = max(1, int(segments))
    video: list[VideoSegment] = []
    audio: list[AudioSegment] = []
    for index in range(count):
        start = round(index * frames / count)
        end = round((index + 1) * frames / count)
        if end <= start:
            continue
        video.append(
            VideoSegment(
                clip_id=f"v{index}",
                source_in_frame=start,
                source_out_frame=end,
                timeline_in_frame=start,
                timeline_out_frame=end,
            )
        )
        audio.append(
            AudioSegment(
                clip_id=f"v{index}",
                source_in_sample=start * 1600,
                source_out_sample=end * 1600,
                timeline_in_sample=start * 1600,
                timeline_out_sample=end * 1600,
            )
        )
    return ProjectState(media_info=media, video_segments=video, audio_segments=audio)

def check_performance(work: Path, seconds: float, segments: int) -> dict[str, Any]:
    from videoflow.exporters.mp4 import export_mp4

    source, duration, build_sec = _make_bench_source(work, seconds)
    state = _bench_state(source, duration, segments)
    target = work / "benchmark-export.mp4"
    started = time.perf_counter()
    export_mp4(
        state,
        target,
        preset="veryfast",
        fps=30,
        cache_dir=work / "cache",
    )
    elapsed = time.perf_counter() - started
    size = target.stat().st_size if target.is_file() else 0
    factor = 660 / max(0.001, duration)
    return {
        "ok": target.is_file() and elapsed > 0,
        "source_sec": round(duration, 2),
        "build_sec": round(build_sec, 2),
        "export_sec": round(elapsed, 2),
        "realtime_factor": round(duration / max(0.001, elapsed), 2),
        "projected_11min_sec": round(elapsed * factor, 1),
        "output_bytes": size,
        "segments": segments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-seconds", type=float, default=0.0)
    parser.add_argument("--segments", type=int, default=11)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--skip-media", action="store_true")
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="vf-acceptance-"))
    os.environ.setdefault("VIDEOWFLOW_HOME", str(work / "home"))
    checks: dict[str, Any] = {
        "editorial": check_editorial(),
        "shorts": check_shorts(),
        "compositors": check_compositors(),
    }
    if args.skip_media:
        checks["alpha"] = {"ok": False, "skipped": "--skip-media"}
    else:
        checks["alpha"] = check_alpha(work)
    if args.bench_seconds > 0:
        checks["performance"] = check_performance(
            work, args.bench_seconds, args.segments
        )
    else:
        checks["performance"] = {
            "ok": False,
            "skipped": "pass --bench-seconds to run the export benchmark",
        }

    hard = ("editorial", "shorts", "compositors")
    ok = all(bool(checks[name].get("ok")) for name in hard)
    payload = {
        "schema_version": 1,
        "version": "3.3.0",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": f"{platform.system().lower()}-{platform.machine().lower()}",
        "python": platform.python_version(),
        "ok": ok,
        "checks": checks,
    }
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    shutil.rmtree(work, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
