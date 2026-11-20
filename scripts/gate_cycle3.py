#!/usr/bin/env python3
"""Cycle 3 gate: scene speed/PiP, FCPXML quarantine, and QA deliverables."""

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
from videoflow.application.projects import init_project, save_project_state  # noqa: E402
from videoflow.application.qa_final import audit_final  # noqa: E402
from videoflow.application.scene_intel.pipeline import analyze_scene_project  # noqa: E402
from videoflow.application.shorts_batch import run_shorts_batch  # noqa: E402
from videoflow.domain.state import (  # noqa: E402
    AudioSegment,
    InactiveSegment,
    ProjectState,
    VideoSegment,
)
from videoflow.exporters.fcpxml import export_fcpxml  # noqa: E402

SOURCE = Path("/home/rafael/Documents/EdicaoVideo/15_49_05-2026_11_17.mp4")
RATE = 48_000


def run(*args: str) -> None:
    completed = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr[-1200:])


def main() -> int:
    work = Path("/tmp/opencode/vf-cycle3-gate")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    clip = work / "gate3-784.mp4"
    run("-ss", "0", "-t", "784", "-i", str(SOURCE), "-c", "copy", str(clip))

    started = time.perf_counter()
    scenes = analyze_scene_project(clip, work / "scenes", force=True)
    elapsed = time.perf_counter() - started
    manifest = scenes.manifest
    screen_layouts = {"SCREEN_SHARE_FULL", "SCREEN_SHARE_PIP", "DUAL_CANVAS_OBS"}
    protected_ok = all(
        (scene.layout_type in screen_layouts)
        == ("PROTECT_FROM_BROLL" in scene.editing_hints)
        for scene in manifest.scenes
    )
    talking_not_protected = all(
        "PROTECT_FROM_BROLL" not in scene.editing_hints
        for scene in manifest.scenes
        if scene.layout_type == "TALKING_HEAD"
    )
    keyframes = sum(
        1
        for scene in manifest.scenes
        if scene.keyframe_path and Path(scene.keyframe_path).is_file()
    )
    faces = sum(1 for scene in manifest.scenes if scene.face_count > 0)
    pip = sum(1 for scene in manifest.scenes if scene.layout_type == "SCREEN_SHARE_PIP")
    rate_sec_per_hour = elapsed * 3600 / 784

    media = FFmpegAdapter().probe(clip)
    active_frames = min(media.duration_frames, 90)
    last_frame = min(media.duration_frames, active_frames + 90)
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=active_frames,
                timeline_in_frame=0,
                timeline_out_frame=active_frames,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=active_frames * RATE // 30,
                timeline_in_sample=0,
                timeline_out_sample=active_frames * RATE // 30,
            )
        ],
        inactive_segments=[
            InactiveSegment(
                clip_id="q1",
                reason="retake",
                video=VideoSegment(
                    clip_id="q1",
                    source_id="primary",
                    source_in_frame=active_frames,
                    source_out_frame=last_frame,
                    timeline_in_frame=0,
                    timeline_out_frame=last_frame - active_frames,
                ),
                audio=AudioSegment(
                    clip_id="q1",
                    source_id="primary",
                    source_in_sample=active_frames * RATE // 30,
                    source_out_sample=last_frame * RATE // 30,
                    timeline_in_sample=0,
                    timeline_out_sample=(last_frame - active_frames) * RATE // 30,
                ),
            )
        ],
    )
    fcpxml = export_fcpxml(state, work / "quarantine.fcpxml", dialect="1.10")
    xml = fcpxml.read_text(encoding="utf-8")

    deliverables: list[dict[str, object]] = []
    extra_sources = Path("/tmp/opencode/vf-cycle2-gate/source.mp4")
    if extra_sources.is_file():
        extra_record, _ = init_project(name="Cycle 3 extra Shorts", output=work / "extra")
        extra_media = FFmpegAdapter().probe(extra_sources)
        extra_state = ProjectState(
            media_info=extra_media,
            sources={"primary": extra_media},
            primary_source_id="primary",
            video_segments=[
                VideoSegment(
                    clip_id="v1",
                    source_id="primary",
                    source_in_frame=0,
                    source_out_frame=extra_media.duration_frames,
                    timeline_in_frame=0,
                    timeline_out_frame=extra_media.duration_frames,
                )
            ],
            audio_segments=[
                AudioSegment(
                    clip_id="v1",
                    source_id="primary",
                    source_in_sample=0,
                    source_out_sample=extra_media.duration_frames * RATE // 30,
                    timeline_in_sample=0,
                    timeline_out_sample=extra_media.duration_frames * RATE // 30,
                )
            ],
        )
        extra_state.pipeline.speech_intervals = [
            (0, extra_media.duration_frames * RATE // 30)
        ]
        save_project_state(extra_record, extra_state, bump_revision=False)
        run_shorts_batch(
            extra_record.project_id,
            [
                {"start_sec": 0, "end_sec": 30, "title": "Extra A"},
                {"start_sec": 30, "end_sec": 60, "title": "Extra B"},
            ],
            adapter=FFmpegAdapter(),
        )
    candidates = [
        *sorted(Path("/tmp/opencode/vf-cycle2-gate/project/shorts/batch").glob("*.mp4")),
        *sorted((work / "extra" / "shorts" / "batch").glob("*.mp4")),
        *sorted(Path("/tmp/opencode/vf-cycle1-gate/project/exports").glob("youtube_*.mp4")),
    ]
    for video in candidates:
        try:
            caption = video.with_suffix(".ass")
            report = audit_final(
                video,
                output=video.parent,
                state=ProjectState(media_info=FFmpegAdapter().probe(video)),
                mode="fast",
                strict=True,
                caption_path=caption if caption.is_file() else None,
                intro_duration_sec=2.0 if "intro" in video.stem else 0.0,
            )
            deliverables.append(
                {
                    "path": str(video),
                    "status": report.get("status"),
                    "loudness": report.get("loudness"),
                    "media_contract": report.get("media_contract"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - gate reports every failure
            deliverables.append({"path": str(video), "status": "error", "error": str(exc)})

    checks = {
        "scene_speed_45s_per_hour": rate_sec_per_hour <= 45.0,
        "scene_speed_10s_for_784": elapsed <= 10.0,
        "faces_detected": faces > 0,
        "pip_detected": pip > 0,
        "protected_rule": protected_ok,
        "talking_head_not_protected": talking_not_protected,
        "all_keyframes": keyframes == len(manifest.scenes),
        "quarantine_track": (
            'lane="1"' in xml
            and 'enabled="0"' in xml
            and "Quarantine" in xml
            and "<marker" in xml
        ),
        "deliverables_7_passed": len(deliverables) >= 7
        and all(
            item.get("status") in {"passed", "succeeded"} for item in deliverables
        ),
    }
    payload = {
        "ok": all(checks.values()),
        "checks": checks,
        "scene": {
            "elapsed_sec": round(elapsed, 3),
            "sec_per_hour": round(rate_sec_per_hour, 2),
            "scenes": len(manifest.scenes),
            "faces": faces,
            "pip": pip,
            "screen_layouts": sum(
                1 for scene in manifest.scenes if scene.layout_type in screen_layouts
            ),
            "keyframes": keyframes,
            "timings": scenes.timings,
        },
        "quarantine": {
            "path": str(fcpxml),
            "lane": 'lane="1"' in xml,
            "enabled_off": 'enabled="0"' in xml,
            "markers": xml.count("<marker"),
        },
        "deliverables": deliverables,
    }
    out = ROOT / "docs" / "qa-evidence" / "cycle3-gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
