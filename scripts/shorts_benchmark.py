# ruff: noqa: E501
#!/usr/bin/env python
"""Deterministic Scene Intelligence and Dynamic Shorts benchmark.

The harness checks scene-boundary F1, crop accuracy, plan composition, caption
sanitising, safe zones, and end padding. It never claims physical RTX speed:
``render_60s_sec`` stays pending until a worker measurement is supplied.

    uv run python scripts/shorts_benchmark.py --quick
    uv run python scripts/shorts_benchmark.py --full --json-out docs/qa-evidence/shorts-benchmark.json
    uv run python scripts/shorts_benchmark.py --video corpus.mp4 --cut-every 5
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from videoflow.application.scene_intel.pipeline import analyze_scene_project  # noqa: E402
from videoflow.application.short_composition.captions import (  # noqa: E402
    CaptionWord,
    assign_layouts,
    group_words,
    sanitize_blocks,
)
from videoflow.application.short_composition.geometry import (  # noqa: E402
    FaceBox,
    crop_for_text_face,
    subtitle_y_map,
)
from videoflow.application.short_composition.plan import resolve_draft  # noqa: E402
from videoflow.application.short_composition.rhythm import (  # noqa: E402
    end_settings,
    layout_sfx_cues,
)
from videoflow.application.short_composition.validate import validate_plan  # noqa: E402
from videoflow.domain.scenes import SceneEntry, ScenesManifest  # noqa: E402
from videoflow.domain.short_composition import (  # noqa: E402
    BrollSource,
    ShortCompositionDraft,
    ShortSegment,
    ShortSegmentDraft,
)

THRESHOLDS = {
    "scene_f1": 0.93,
    "detection_sec_per_hour": 45.0,
    "face_x_error_pct": 0.03,
    "caption_overlaps": 0,
    "truncated_words": 0,
    "safe_zone_bottom_px": 380,
    "safe_zone_right_px": 140,
    "fade_out_ms": 80,
    "gpu_render_60s_sec": 20.0,
}


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise SystemExit("FFmpeg is required for the corpus benchmark")
    return binary


def _run(argv: list[str]) -> None:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip().splitlines()
        raise RuntimeError(
            "ffmpeg failed: " + (tail[-1][:400] if tail else str(completed.returncode))
        )


def make_corpus(tmp_path: Path, *, seconds: int, cut_every: int = 5) -> Path:
    """Create one continuous clip with known color cuts every ``cut_every`` s."""

    corpus = tmp_path / "corpus.mp4"
    period = max(2, int(cut_every) * 2)
    half = max(1, int(cut_every))
    red = f"lt(mod(t,{period}),{half})"
    blue = f"gte(mod(t,{period}),{half})"
    _run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=640x360:r=30:d={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={seconds}",
            "-vf",
            (
                f"drawbox=x=0:y=0:w=iw:h=ih:color=red:t=fill:enable='{red}',"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='{blue}'"
            ),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            str(seconds),
            str(corpus),
        ]
    )
    return corpus


def _scene(scene_id: str, start: float, end: float, layout: str, x: float = 0.5) -> SceneEntry:
    return SceneEntry(
        scene_id=scene_id,
        start_sample=round(start * 48_000),
        end_sample=round(end * 48_000),
        start_sec=start,
        end_sec=end,
        layout_type=layout,  # type: ignore[arg-type]
        face_count=1,
        face_bbox_norm={"cx": x, "cy": 0.4, "w": 0.2, "h": 0.3},
        face_area_ratio=0.06,
        edge_density=0.2 if layout.startswith("SCREEN") else 0.02,
        sharpness_laplacian=140.0,
        editing_hints=["PROTECT_FROM_BROLL"] if layout.startswith("SCREEN") else ["SAFE_FOR_BROLL"],
    )


def check_geometry() -> dict[str, Any]:
    errors: list[float] = []
    for cam_w, cam_h in ((1920, 1080), (3840, 1080)):
        for cx in (0.45, 0.5, 0.55):
            face = FaceBox(cx=cx, cy=0.4, w=0.2, h=0.3)
            crop = crop_for_text_face(cam_w=cam_w, cam_h=cam_h, face=face)
            face_px = face.cx * cam_w
            error = abs(face_px - (crop.x + crop.width / 2)) / max(1, crop.width)
            errors.append(error)
    worst = max(errors)
    return {
        "ok": worst <= THRESHOLDS["face_x_error_pct"],
        "face_x_error_pct": round(worst, 5),
        "samples": len(errors),
    }


def check_face_tracking() -> dict[str, Any]:
    errors: list[float] = []
    for index in range(60):
        cx = 0.35 if index % 2 == 0 else 0.65
        face = FaceBox(cx=cx, cy=0.4, w=0.2, h=0.3)
        crop = crop_for_text_face(cam_w=1920, cam_h=1080, face=face)
        face_px = cx * 1920
        errors.append(abs(face_px - (crop.x + crop.width / 2)) / max(1, crop.width))
    worst = max(errors)
    return {
        "ok": worst <= THRESHOLDS["face_x_error_pct"],
        "samples": len(errors),
        "face_x_error_pct": round(worst, 5),
        "sequence": "left-right-60s",
    }


def check_plan_sequence() -> dict[str, Any]:
    manifest = ScenesManifest(
        video_id="bench",
        resolution={"w": 1920, "h": 1080},
        fps_num=30,
        fps_den=1,
        scenes=[
            _scene("SC_0001", 0.0, 15.0, "TALKING_HEAD"),
            _scene("SC_0002", 15.0, 30.0, "TALKING_HEAD"),
            _scene("SC_0003", 30.0, 45.0, "SCREEN_SHARE_PIP"),
        ],
    )
    draft = ShortCompositionDraft(
        short_id="BENCH",
        start=0.0,
        end=45.0,
        segments=[
            ShortSegmentDraft(seg_id="S1", rel_start=0.0, rel_end=15.0, layout="FULL_FACE"),
            ShortSegmentDraft(
                seg_id="S2",
                rel_start=15.0,
                rel_end=30.0,
                layout="SPLIT_BROLL",
                broll_source=BrollSource(path="/synthetic/broll.mp4"),
            ),
            ShortSegmentDraft(
                seg_id="S3",
                rel_start=30.0,
                rel_end=45.0,
                layout="SPLIT_SCREEN_SAFE",
            ),
        ],
    )
    result = resolve_draft(draft, manifest, broll_exists=lambda path: True)
    validation = validate_plan(
        result.plan, manifest, broll_exists=lambda path: True
    )
    layouts = [segment.layout for segment in result.plan.segments]
    expected = ["FULL_FACE", "SPLIT_BROLL", "SPLIT_SCREEN_SAFE"]
    return {
        "ok": layouts == expected and validation["ok"],
        "layouts": layouts,
        "expected": expected,
        "warnings": len(result.warnings) + len(validation["warnings"]),
        "errors": validation["errors"],
    }


def _caption_words(seconds: int) -> list[CaptionWord]:
    words = []
    cursor = 0.1
    index = 0
    while cursor < seconds - 0.2:
        words.append(CaptionWord(cursor, min(seconds, cursor + 0.26), f"w{index}"))
        cursor += 0.32
        index += 1
    return words


def check_captions() -> dict[str, Any]:
    from videoflow.domain.short_composition import ShortCompositionPlan

    plan = ShortCompositionPlan(
        short_id="BENCH",
        start=0.0,
        end=60.0,
        segments=[
            ShortSegment(seg_id="S1", rel_start=0.0, rel_end=20.0, layout="FULL_FACE"),
            ShortSegment(seg_id="S2", rel_start=20.0, rel_end=40.0, layout="SPLIT_SCREEN_SAFE"),
            ShortSegment(seg_id="S3", rel_start=40.0, rel_end=60.0, layout="FULL_FACE"),
        ],
    )
    words = _caption_words(60)
    blocks, group_warnings = group_words(words, layout_boundaries=[20.0, 40.0])
    blocks, layout_warnings = assign_layouts(blocks, plan, subtitle_y=subtitle_y_map())
    blocks, sanitize_warnings = sanitize_blocks(blocks)
    overlaps = sum(
        1
        for left, right in zip(blocks, blocks[1:], strict=False)
        if right.start < left.end
    )
    truncated = sum(len(block.text.split()) for block in blocks)
    overwide = sum(1 for block in blocks if max((len(line) for line in block.lines), default=0) > 18)
    overlarge = sum(1 for block in blocks if len(block.lines) > 2)
    ending = end_settings(plan)
    sfx = layout_sfx_cues(plan)
    unsafe = sum(1 for block in blocks if block.layout == "SPLIT_SCREEN_SAFE" and block.subtitle_y > 1540)
    last_end = round(blocks[-1].end, 3) if blocks else 0.0
    max_height = max(
        (len(block.lines) * 64 * 1.18 for block in blocks), default=0.0
    )
    return {
        "ok": (
            overlaps == THRESHOLDS["caption_overlaps"]
            and truncated >= len(words) - 2
            and overwide == 0
            and overlarge == 0
            and ending["fade_out_ms"] == THRESHOLDS["fade_out_ms"]
            and ending["padding_ms"] >= 349
            and unsafe == 0
            and last_end >= 58.0
            and max_height / 1920 <= 0.12
        ),
        "blocks": len(blocks),
        "words": len(words),
        "overlaps": overlaps,
        "truncated_words": max(0, len(words) - truncated),
        "overwide_lines": overwide,
        "overlarge_blocks": overlarge,
        "fade_out_ms": ending["fade_out_ms"],
        "padding_ms": ending["padding_ms"],
        "sfx_cues": len(sfx),
        "warnings": len(group_warnings) + len(layout_warnings) + len(sanitize_warnings),
        "last_block_end": last_end,
        "caption_height_pct": round(max_height / 1920, 4),
        "safe_zone_bottom_px": THRESHOLDS["safe_zone_bottom_px"],
        "safe_zone_right_px": THRESHOLDS["safe_zone_right_px"],
    }


def _f1(truth: list[float], detected: list[float], tolerance: float = 0.25) -> tuple[float, int, int]:
    matched: set[int] = set()
    hits = 0
    for value in truth:
        for index, found in enumerate(detected):
            if index in matched:
                continue
            if abs(found - value) <= tolerance:
                matched.add(index)
                hits += 1
                break
    precision = hits / len(detected) if detected else 0.0
    recall = hits / len(truth) if truth else 0.0
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return score, hits, len(detected)


def check_scene_corpus(
    video: Path,
    *,
    cut_every: int,
    seconds: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="vf-scenes-bench-") as directory:
        result = analyze_scene_project(
            video,
            Path(directory) / "scenes",
            threshold=2.0,
            min_scene_len_sec=1.5,
            force=True,
        )
    elapsed = time.perf_counter() - started
    truth = [value for value in range(cut_every, seconds, cut_every)]
    detected = [
        scene.start_sec
        for scene in result.manifest.scenes
        if scene.start_sec > 0.01
    ]
    score, hits, found = _f1(truth, detected)
    timings = result.timings or {}
    detection_sec = float(timings.get("detection", elapsed))
    detection_per_hour = detection_sec / max(0.001, seconds) * 3600
    full_per_hour = elapsed / max(0.001, seconds) * 3600
    return {
        "ok": (
            score >= THRESHOLDS["scene_f1"]
            and detection_per_hour <= THRESHOLDS["detection_sec_per_hour"]
        ),
        "engine": result.engine,
        "seconds": seconds,
        "scenes": len(result.manifest.scenes),
        "truth_cuts": len(truth),
        "detected_cuts": found,
        "matched": hits,
        "f1": round(score, 4),
        "analysis_sec": round(elapsed, 3),
        "detection_sec": round(detection_sec, 3),
        "detection_sec_per_hour": round(detection_per_hour, 3),
        "full_pipeline_sec_per_hour": round(full_per_hour, 3),
        "timings": {key: round(value, 4) for key, value in timings.items()},
        "cache_hit": result.cache_hit,
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Scene intelligence and Dynamic Shorts benchmark",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "| Check | Result | Metric |",
        "| --- | --- | --- |",
    ]
    for name, item in payload["checks"].items():
        status = "PASS" if item.get("ok") else "FAIL"
        metric = item.get("f1", item.get("face_x_error_pct", item.get("blocks", "")))
        lines.append(f"| {name} | {status} | `{metric}` |")
    lines.extend(
        [
            "",
            "## Thresholds",
            "",
            "```json",
            json.dumps(THRESHOLDS, indent=2),
            "```",
            "",
            "## Pending physical certification",
            "",
            "`render_60s_sec` remains pending until a Windows RTX 3060 worker",
            "measurement is recorded. The harness never claims that speedup.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="30 s synthetic corpus")
    parser.add_argument("--full", action="store_true", help="600 s synthetic corpus")
    parser.add_argument("--video", type=Path, default=None)
    parser.add_argument("--cut-every", type=int, default=5)
    parser.add_argument("--seconds", type=int, default=0)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=ROOT / "docs" / "qa-evidence" / "shorts-benchmark.json",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=ROOT / "docs" / "qa-evidence" / "shorts-benchmark.md",
    )
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args(argv)

    seconds = args.seconds or (600 if args.full else 30)
    checks: dict[str, Any] = {
        "geometry": check_geometry(),
        "face_tracking_60s": check_face_tracking(),
        "plan_sequence": check_plan_sequence(),
        "captions": check_captions(),
    }
    corpus_dir: tempfile.TemporaryDirectory[str] | None = None
    video = args.video
    if video is None:
        corpus_dir = tempfile.TemporaryDirectory(prefix="vf-shorts-bench-")
        video = make_corpus(Path(corpus_dir.name), seconds=seconds, cut_every=args.cut_every)
    try:
        checks["scene_corpus"] = check_scene_corpus(
            video,
            cut_every=args.cut_every,
            seconds=seconds,
        )
    finally:
        if corpus_dir is not None and not args.keep_temp:
            corpus_dir.cleanup()
    ok = all(bool(item.get("ok")) for item in checks.values())
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ok": ok,
        "thresholds": THRESHOLDS,
        "checks": checks,
        "render_60s_sec": None,
        "render_status": "pending_physical_worker",
        "physical_acceptance_pending": True,
        "full_pipeline_target_met": (
            checks["scene_corpus"].get("full_pipeline_sec_per_hour", 999)
            <= THRESHOLDS["detection_sec_per_hour"]
        ),
        "notes": [
            "The 45 s/h target is applied to the scene-detection pass (proxy + PySceneDetect).",
            "Full analysis including face metrics and keyframes is reported separately; keyframes are batched and visual sampling is parallel.",
            "Synthetic corpus; replace with a physical 10-minute annotated corpus before claiming production F1.",
            "Renderer speed requires a Windows RTX 3060 worker; local CI does not certify it.",
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_markdown(args.md_out, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
