#!/usr/bin/env python3
"""Cycle 4 micro gate: 90 s real-footage run with FX, media, and delivery QA.

Runs the full-profile path on one 90 s excerpt:

* core regressions from Gates 1-3 (media contract, culling/timeline, Shorts,
  scenes/PiP/keyframes, FCPXML quarantine);
* advanced FX (depth, parallax, motion, capture) with real alpha;
* keyless media, B-roll motion, music, license audit/approval, style preview;
* seven deliverables audited in fast QA mode.

GPU-only thresholds are reported separately so a CPU host is never mistaken
for an RTX 3060 pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from videoflow.application.asset_providers.ledger import (  # noqa: E402
    license_blockers,
    write_ledger,
)
from videoflow.application.asset_providers.models import AssetCandidate  # noqa: E402

from videoflow.adapters.ffmpeg import FFmpegAdapter  # noqa: E402
from videoflow.application.compositor import (  # noqa: E402
    depth_composite,
    parallax,
    style_preview,
)
from videoflow.application.master_export import render_master  # noqa: E402
from videoflow.application.projects import (  # noqa: E402
    init_project,
    load_project_state,
    save_project_state,
)
from videoflow.application.qa_final import audit_final  # noqa: E402
from videoflow.application.release_kit import build_release_kit  # noqa: E402
from videoflow.application.scene_intel.pipeline import analyze_scene_project  # noqa: E402
from videoflow.application.shorts_batch import run_shorts_batch  # noqa: E402
from videoflow.application.timeline_builder import build_timeline  # noqa: E402
from videoflow.core.media_contract import validate_alpha, validate_media  # noqa: E402
from videoflow.domain.config import JlCutsConfig, ZoomsConfig  # noqa: E402
from videoflow.domain.state import (  # noqa: E402
    AudioSegment,
    InactiveSegment,
    OverlayClip,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)
from videoflow.exporters.fcpxml import export_fcpxml  # noqa: E402

DEFAULT_SOURCE = Path("/home/rafael/Documents/EdicaoVideo/15_49_05-2026_11_17.mp4")
RATE = 48_000
FPS = 30


def run(*args: str) -> None:
    completed = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr[-1500:])


def probe_stream(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,pix_fmt:stream_tags=alpha_mode",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout or "{}")
    return (payload.get("streams") or [{}])[0]


def has_alpha(path: Path) -> bool:
    return validate_alpha(path).ok


def transcript(
    seconds: int, spans: list[tuple[int, int]] | None = None
) -> list[Sentence]:
    topics = [
        "Nvidia no Brasil mudou o mercado de inteligência artificial",
        "A placa RTX 3060 entrega doze gigabytes de memória",
        "O encoder NVENC acelera a exportação de vídeo",
        "Editores precisam validar legenda e safe zone",
        "O fluxo completo cabe em noventa segundos",
    ]
    result: list[Sentence] = []
    ranges = spans or [(0, seconds * RATE)]
    for index, (begin, finish) in enumerate(ranges):
        if finish <= begin:
            continue
        text = topics[index % len(topics)]
        tokens = text.split()
        step = max(1, (finish - begin) // max(1, len(tokens)))
        words = []
        for word_index, word in enumerate(tokens):
            word_start = begin + word_index * step
            words.append(
                WordTiming(
                    word=word,
                    start_sample=word_start,
                    end_sample=word_start + max(1, int(step * 0.8)),
                    probability=0.95,
                )
            )
        result.append(
            Sentence(
                id=len(result),
                start_sample=begin,
                end_sample=finish,
                text=text,
                words=words,
            )
        )
    return result


def extract_clip(source: Path, target: Path, seconds: int, start: int = 900) -> None:
    run(
        "-ss",
        str(start),
        "-t",
        str(seconds),
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-ar",
        str(RATE),
        "-ac",
        "2",
        "-b:a",
        "192k",
        str(target),
    )


def speech_spans(source: Path, media: Any) -> list[tuple[int, int]]:
    """Detect speech and return kept source spans, like editorial_clean."""

    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(source),
            "-af",
            "silencedetect=noise=-30dB:d=0.30",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    total = media.duration_frames * RATE // FPS
    silences: list[tuple[float, float]] = []
    start: float | None = None
    for line in completed.stderr.splitlines():
        match = re.search(r"silence_start: ([0-9.]+)", line)
        if match:
            start = float(match.group(1))
            continue
        match = re.search(r"silence_end: ([0-9.]+)", line)
        if match and start is not None:
            silences.append((start, float(match.group(1))))
            start = None
    if start is not None:
        silences.append((start, total / RATE))
    spans: list[tuple[int, int]] = []
    cursor = 0.0
    pad = 0.08
    for begin, end in silences:
        speech_end = max(cursor, begin)
        if speech_end - cursor > 0.35:
            spans.append(
                (
                    max(0, round((cursor - pad) * RATE)),
                    min(total, round((speech_end + pad) * RATE)),
                )
            )
        cursor = max(cursor, end)
    if total / RATE - cursor > 0.35:
        spans.append(
            (
                max(0, round((cursor - pad) * RATE)),
                min(total, round((total / RATE + pad) * RATE)),
            )
        )
    return spans or [(0, total)]


def build_state(source: Path, seconds: int) -> tuple[Any, ProjectState]:
    record, _ = init_project(
        project_id=f"micro-gate-{int(time.time())}",
        name="Cycle 4 micro gate",
        output=source.parent / f"project-{int(time.time())}",
    )
    media = FFmpegAdapter().probe(source)
    spans = speech_spans(source, media)
    built = build_timeline(
        media,
        spans,
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(
            mode="alternate_cuts",
            min_scale=1.0,
            max_scale=1.0,
            punch_in_scale=1.0,
        ),
    )
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        transcript=transcript(seconds, spans),
        video_segments=list(built.video_segments),
        audio_segments=list(built.audio_segments),
    )
    state.pipeline.speech_intervals = list(spans)
    save_project_state(record, state, bump_revision=False)
    return record, state


def check_core(
    source: Path,
    record: Any,
    state: ProjectState,
    work: Path,
) -> dict[str, Any]:
    source_contract = validate_media(source, "source")
    scenes = analyze_scene_project(source, work / "scenes", force=True)
    manifest = scenes.manifest
    screen_layouts = {"SCREEN_SHARE_FULL", "SCREEN_SHARE_PIP", "DUAL_CANVAS_OBS"}
    keyframes = sum(
        1
        for scene in manifest.scenes
        if scene.keyframe_path and Path(scene.keyframe_path).is_file()
    )
    protected_ok = all(
        (scene.layout_type in screen_layouts)
        == ("PROTECT_FROM_BROLL" in scene.editing_hints)
        for scene in manifest.scenes
    )
    talking_clear = all(
        "PROTECT_FROM_BROLL" not in scene.editing_hints
        for scene in manifest.scenes
        if scene.layout_type == "TALKING_HEAD"
    )
    frames = state.media_info.duration_frames if state.media_info else 0
    quarantine_state = state.model_copy(
        update={
            "inactive_segments": [
                InactiveSegment(
                    clip_id="q1",
                    reason="retake",
                    video=VideoSegment(
                        clip_id="q1",
                        source_id="primary",
                        source_in_frame=30,
                        source_out_frame=min(frames, 120),
                        timeline_in_frame=0,
                        timeline_out_frame=max(2, min(frames, 120) - 30),
                    ),
                    audio=AudioSegment(
                        clip_id="q1",
                        source_id="primary",
                        source_in_sample=30 * RATE // FPS,
                        source_out_sample=min(frames, 120) * RATE // FPS,
                        timeline_in_sample=0,
                        timeline_out_sample=max(2, min(frames, 120) - 30)
                        * RATE
                        // FPS,
                    ),
                )
            ]
        }
    )
    fcpxml = export_fcpxml(
        quarantine_state, work / "quarantine.fcpxml", dialect="1.10"
    )
    xml = fcpxml.read_text(encoding="utf-8")
    return {
        "source_contract": source_contract.ok,
        "scenes": len(manifest.scenes),
        "keyframes": keyframes,
        "all_keyframes": keyframes == len(manifest.scenes),
        "faces": sum(1 for scene in manifest.scenes if scene.face_count > 0),
        "pip": sum(
            1 for scene in manifest.scenes if scene.layout_type == "SCREEN_SHARE_PIP"
        ),
        "protected_rule": protected_ok,
        "talking_head_not_protected": talking_clear,
        "quarantine": (
            'lane="1"' in xml
            and 'enabled="0"' in xml
            and "Quarantine" in xml
            and "<marker" in xml
        ),
        "scene_elapsed_sec": round(scenes.timings.get("total", 0.0), 3),
    }


def check_fx(record: Any, state: ProjectState, work: Path) -> dict[str, Any]:
    from videoflow.domains.vision.tools import capture_web_or_screen, render_motion_graphic

    still = work / "still.png"
    run("-i", str(state.media_info.source_path), "-frames:v", "1", str(still))

    depth_started = time.perf_counter()
    depth = depth_composite(record.project_id, "Nvidia no Brasil", 1.0, 4.0)
    depth_elapsed = time.perf_counter() - depth_started
    depth_alpha = has_alpha(Path(depth["matte"])) and has_alpha(Path(depth["graphic"]))

    parallax_started = time.perf_counter()
    parallax_result = parallax(record.project_id, str(still), 10.0, 16.0)
    parallax_elapsed = time.perf_counter() - parallax_started

    scene = work / "motion"
    scene.mkdir(parents=True, exist_ok=True)
    (scene / "index.html").write_text(
        "<html><body style='margin:0;background:#000'>"
        "<div id='card' style='width:240px;height:120px;background:#ffcc4d;"
        "animation:slide 2s linear forwards'></div>"
        "<style>@keyframes slide{to{transform:translateX(600px)}}</style>"
        "</body></html>",
        encoding="utf-8",
    )
    motion_started = time.perf_counter()
    motion = render_motion_graphic(
        record.project_id,
        engine="hyperframes",
        template_or_code=str(scene),
        duration_sec=1.0,
        width=1080,
        height=1920,
        alpha=True,
    )
    motion_elapsed = time.perf_counter() - motion_started
    motion_path = Path(motion["output"])
    motion_alpha = has_alpha(motion_path)
    (scene / "index.html").write_text(
        "<html><body style='margin:0;background:#000'>"
        "<h1 style='color:#fff'>edited in place</h1></body></html>",
        encoding="utf-8",
    )
    motion_after = render_motion_graphic(
        record.project_id,
        engine="hyperframes",
        template_or_code=str(scene),
        duration_sec=1.0,
        width=1080,
        height=1920,
        alpha=True,
    )
    cache_invalidated = (
        motion_after.get("cached") is False
        and motion_after.get("output") != motion.get("output")
    )

    page = work / "capture.html"
    page.write_text(
        "<html><body style='margin:0;background:#0b1020;color:#fff'>"
        + "".join(
            f"<section style='height:900px;font:64px sans-serif'>Section {index}</section>"
            for index in range(5)
        )
        + "</body></html>",
        encoding="utf-8",
    )
    capture_started = time.perf_counter()
    capture = capture_web_or_screen(
        record.project_id,
        page.as_uri(),
        mode="video_clip",
        duration_sec=2.0,
        fps=8,
        viewport_width=1081,
        viewport_height=1921,
        scroll_animation="smooth",
        output_name="scroll",
    )
    capture_elapsed = time.perf_counter() - capture_started
    capture_path = Path(capture["output"])
    stream = probe_stream(capture_path)

    return {
        "depth": {
            "path": depth["matte"],
            "graphic": depth["graphic"],
            "elapsed_sec": round(depth_elapsed, 3),
            "alpha": depth_alpha,
            "cpu_target_25s": depth_elapsed < 25.0,
            "gpu_target_5s": depth_elapsed < 5.0,
        },
        "parallax": {
            "path": parallax_result["graphic"],
            "elapsed_sec": round(parallax_elapsed, 3),
            "alpha": has_alpha(Path(parallax_result["subject"])),
            "cpu_target_20s": parallax_elapsed < 20.0,
            "gpu_target_10s": parallax_elapsed < 10.0,
        },
        "motion": {
            "path": motion["output"],
            "elapsed_sec": round(motion_elapsed, 3),
            "alpha": motion_alpha,
            "cache_invalidated": cache_invalidated,
        },
        "capture": {
            "path": capture["output"],
            "elapsed_sec": round(capture_elapsed, 3),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "even_dimensions": int(stream.get("width") or 0) % 2 == 0
            and int(stream.get("height") or 0) % 2 == 0,
        },
    }


def check_media(record: Any, state: ProjectState, work: Path) -> dict[str, Any]:
    from videoflow.domains.audio.studio import generate_music_or_sfx
    from videoflow.domains.media.fetch_tools import fetch_stock_images
    from videoflow.domains.vision.tools import image_to_broll_motion

    result: dict[str, Any] = {}
    try:
        fetched = fetch_stock_images(
            record.project_id, "rio de janeiro", count=1, provider="wikimedia"
        )
        asset = (fetched.get("assets") or [{}])[0]
        result["stock"] = {
            "ok": bool(asset.get("path")),
            "path": asset.get("path"),
            "license": (asset.get("license") or {}).get("license"),
            "attribution": (asset.get("license") or {}).get("attribution", "")[:80],
        }
        broll = image_to_broll_motion(
            record.project_id,
            str(asset["path"]),
            duration_sec=1.0,
            motion="zoom_in",
            aspect_ratio="16:9",
        )
        stream = probe_stream(Path(broll["output"]))
        result["broll"] = {
            "ok": (stream.get("width"), stream.get("height")) == (1920, 1080),
            "path": broll["output"],
            "width": stream.get("width"),
            "height": stream.get("height"),
        }
        ledger = write_ledger(
            Path(record.output),
            [
                AssetCandidate(
                    asset_id="gate-image",
                    provider="wikimedia",
                    query="rio de janeiro",
                    downloaded_path=str(asset["path"]),
                    title=Path(str(asset["path"])).name,
                    license="CC BY-NC",
                    license_status="cc_review",
                    page_url="https://commons.wikimedia.org/",
                    download_url="",
                )
            ],
        )
        del ledger
        state.overlays.append(
            OverlayClip(
                overlay_id="license-probe",
                path=str(asset["path"]),
                start_frame=0,
                duration_frames=30,
                anchor="top_right",
                margin_x=32,
                margin_y=32,
                width_ratio=0.2,
                z=45,
            )
        )
        save_project_state(record, state, bump_revision=False)
        blockers = license_blockers(
            Path(record.output), state=state, scope="timeline"
        )
        from videoflow.application.assets_service import review_assets

        review_assets(
            Path(record.output),
            action="approve",
            project_id=record.project_id,
            asset_ids=["gate-image"],
            license="CC BY",
            attribution="Wikimedia Commons",
        )
        after = license_blockers(Path(record.output), state=state, scope="timeline")
        result["license"] = {
            "blocked_before": len(blockers),
            "blocked_after_approval": len(after),
            "approval_unblocks": bool(blockers) and not after,
        }
        # Leaving the probe overlay in the state would pollute longform QA.
        state.overlays = [
            overlay
            for overlay in state.overlays
            if overlay.overlay_id != "license-probe"
        ]
        save_project_state(record, state, bump_revision=False)
    except Exception as exc:  # noqa: BLE001 - network is environment dependent
        result["stock_error"] = f"{type(exc).__name__}: {exc}"

    music = generate_music_or_sfx(
        record.project_id, "documentary tension", duration_sec=2.0, type="music"
    )
    result["music"] = {"ok": Path(music["output"]).is_file(), "path": music["output"]}
    return result


def render_deliverables(
    record: Any,
    state: ProjectState,
    work: Path,
) -> list[dict[str, Any]]:
    exports = Path(record.output) / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    deliverables: list[dict[str, Any]] = []
    for audio_source in ("mix", "timeline"):
        target = exports / f"youtube_{audio_source}.mp4"
        started = time.perf_counter()
        render_master(
            state,
            target,
            output=Path(record.output),
            audio_source=audio_source,
            fps=FPS,
            cfr=True,
            preset="ultrafast",
            crf=23,
            scale_height=720,
        )
        deliverables.append(
            {
                "path": str(target),
                "kind": f"longform_{audio_source}",
                "elapsed_sec": round(time.perf_counter() - started, 3),
            }
        )

    record_state = load_project_state(record)
    timeline_frames = max(
        (segment.timeline_out_frame for segment in record_state.video_segments),
        default=0,
    )
    timeline_sec = timeline_frames / FPS if timeline_frames else 60.0
    step = timeline_sec / 5
    min_sec = max(2.0, round(step * 0.85, 3))
    max_sec = round(step * 2.0, 3)
    intro = work / "intro.png"
    run(
        "-f",
        "lavfi",
        "-i",
        "color=c=0x0ea5e9:s=1080x1920",
        "-frames:v",
        "1",
        str(intro),
    )
    shutil.rmtree(Path(record.output) / "shorts" / "batch", ignore_errors=True)
    clip_specs = [
        {
            "start_sec": 0,
            "end_sec": round(step, 3),
            "title": "Vertical",
            "aspect_ratio": "9:16",
            "layout": "FULL_FACE",
            "thought_boundary": False,
            "crossfade_ms": 0,
            "start_pad_ms": 90,
            "end_pad_ms": 120,
            "min_sec": min_sec,
            "max_sec": max_sec,
        },
        {
            "start_sec": round(step, 3),
            "end_sec": round(step * 2, 3),
            "title": "Feed 4:5",
            "aspect_ratio": "4:5",
            "layout": "SPLIT_BROLL",
            "thought_boundary": False,
            "crossfade_ms": 0,
            "start_pad_ms": 90,
            "end_pad_ms": 120,
            "min_sec": min_sec,
            "max_sec": max_sec,
        },
        {
            "start_sec": round(step * 3, 3),
            "end_sec": round(step * 4, 3),
            "title": "Depth 3D",
            "aspect_ratio": "9:16",
            "layout": "DEPTH_3D",
            "thought_boundary": False,
            "crossfade_ms": 0,
            "start_pad_ms": 90,
            "end_pad_ms": 120,
            "min_sec": min_sec,
            "max_sec": max_sec,
        },
        {
            "start_sec": round(step * 4, 3),
            "end_sec": round(step * 5, 3),
            "title": "Short 75",
            "aspect_ratio": "9:16",
            "layout": "FULL_FACE",
            "thought_boundary": False,
            "crossfade_ms": 0,
            "start_pad_ms": 90,
            "end_pad_ms": 120,
            "min_sec": min_sec,
            "max_sec": max_sec,
        },
    ]
    adapter = FFmpegAdapter()
    for spec in clip_specs:
        run_shorts_batch(record.project_id, [spec], adapter=adapter)
    from videoflow.application.time_map import timeline_range_to_source_ranges

    intro_short = Path(record.output) / "shorts" / "batch" / "01-intro.mp4"
    intro_short.parent.mkdir(parents=True, exist_ok=True)
    pieces: list[tuple[int, int]] = []
    intro_state = load_project_state(record)
    for _source_id, start_sec, end_sec in timeline_range_to_source_ranges(
        intro_state, round(step * 2, 3), round(step * 3, 3)
    ):
        pieces.append(
            (round(start_sec * RATE), round(end_sec * RATE))
        )
    merged: list[tuple[int, int]] = []
    for piece_start, piece_end in pieces:
        if merged and piece_start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], piece_end))
        else:
            merged.append((piece_start, piece_end))
    adapter.render_short(
        Path(intro_state.media_info.source_path),
        merged,
        intro_short,
        sample_rate=RATE,
        width=1080,
        height=1920,
        intro_path=intro,
        intro_duration_sec=2.0,
        layout_mode="fullscreen_punchin",
        crossfade_ms=0,
        fps=30,
    )
    for video in sorted((Path(record.output) / "shorts" / "batch").glob("*.mp4")):
        deliverables.append({"path": str(video), "kind": "short"})
    return deliverables


def _audit_one(item: dict[str, Any]) -> dict[str, Any]:
    video = Path(item["path"])
    caption = video.with_suffix(".ass")
    try:
        report = audit_final(
            video,
            output=video.parent,
            state=ProjectState(media_info=FFmpegAdapter().probe(video)),
            mode="fast",
            strict=True,
            caption_path=caption if caption.is_file() else None,
            intro_duration_sec=2.0 if "intro" in video.stem else 0.0,
        )
        item["status"] = report.get("status")
        item["loudness"] = report.get("loudness")
        item["media_contract"] = {
            "ok": (report.get("media_contract") or {}).get("ok"),
            "skipped": (report.get("media_contract") or {}).get("skipped"),
        }
        item["issues"] = report.get("issues", [])
    except Exception as exc:  # noqa: BLE001 - report every failure
        item["status"] = "error"
        item["error"] = f"{type(exc).__name__}: {exc}"
    return item


def audit_deliverables(deliverables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(_audit_one, deliverables))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--start", type=int, default=900)
    parser.add_argument("--profile", default="full")
    args = parser.parse_args()

    work = Path("/tmp/opencode/vf-micro-gate")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    source = work / f"micro-{args.seconds}.mp4"
    extract_clip(Path(args.source).expanduser(), source, args.seconds, args.start)

    record, state = build_state(source, args.seconds)
    started = time.perf_counter()

    core = check_core(source, record, state, work)
    fx = check_fx(record, state, work)
    media = check_media(record, state, work)
    style_started = time.perf_counter()
    style = style_preview(record.project_id, "sr-depth-3d-viral", duration_sec=5.0)
    style_elapsed = time.perf_counter() - style_started
    release = build_release_kit(record.project_id)

    deliverables = render_deliverables(record, load_project_state(record), work)
    deliverables = audit_deliverables(deliverables)

    titles = [str(title) for title in release.get("titles", [])]
    transcript_words = {
        word.casefold()
        for sentence in load_project_state(record).transcript
        for word in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", sentence.text)
    }
    title_source_ok = all(
        35 <= len(title) <= 70
        and "cycle 4 micro gate" not in title.casefold()
        and bool(transcript_words & set(re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", title.casefold())))
        for title in titles
    )
    elapsed = time.perf_counter() - started

    checks = {
        **{f"core_{key}": bool(value) for key, value in core.items() if isinstance(value, bool)},
        "fx_depth_alpha": fx["depth"]["alpha"],
        "fx_depth_cpu_target": fx["depth"]["cpu_target_25s"],
        "fx_parallax_cpu_target": fx["parallax"]["cpu_target_20s"],
        "fx_motion_alpha": fx["motion"]["alpha"],
        "fx_motion_cache_invalidated": fx["motion"]["cache_invalidated"],
        "fx_capture_even": fx["capture"]["even_dimensions"],
        "media_stock_ok": bool(media.get("stock", {}).get("ok")),
        "media_broll_16_9": bool(media.get("broll", {}).get("ok")),
        "media_music_ok": bool(media.get("music", {}).get("ok")),
        "media_license_approval": bool(
            media.get("license", {}).get("approval_unblocks")
        ),
        "style_preview_cpu_target": style_elapsed < 25.0,
        "release_titles_from_transcript": title_source_ok,
        "deliverables_7_passed": len(deliverables) == 7
        and all(item.get("status") in {"passed", "succeeded"} for item in deliverables),
        "micro_gate_cpu_3min": elapsed < 180.0,
    }
    payload = {
        "ok": all(checks.values()),
        "profile": args.profile,
        "hardware": {
            "host": os.uname().machine,
            "gpu_worker_expected": "RTX 3060",
            "gpu_targets_are_reported_separately": True,
        },
        "seconds": args.seconds,
        "elapsed_sec": round(elapsed, 3),
        "checks": checks,
        "core": core,
        "fx": fx,
        "media": media,
        "style": {
            "path": style["path"],
            "elapsed_sec": round(style_elapsed, 3),
            "cpu_target_25s": style_elapsed < 25.0,
            "draft": style.get("draft"),
        },
        "release_kit": {
            "titles": titles,
            "title_lengths": [len(title) for title in titles],
            "from_transcript": title_source_ok,
            "chapters": len(release.get("chapters", [])),
        },
        "deliverables": deliverables,
        "deliverable_count": len(deliverables),
    }
    target = ROOT / "docs" / "qa-evidence" / "cycle4-micro-gate.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
