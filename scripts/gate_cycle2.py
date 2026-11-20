#!/usr/bin/env python3
"""Cycle 2 gate: edited-timeline Shorts, 30 fps, loudness, and safe-zone captions."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from videoflow.adapters.ffmpeg import FFmpegAdapter  # noqa: E402
from videoflow.application.decupage.snap import build_plan  # noqa: E402
from videoflow.application.projects import init_project, save_project_state  # noqa: E402
from videoflow.application.shorts_batch import run_shorts_batch  # noqa: E402
from videoflow.core.media_contract import TARGET_LUFS, TOLERANCE_LUFS  # noqa: E402
from videoflow.domain.decupage import Asu, AsuWord  # noqa: E402
from videoflow.domain.state import (  # noqa: E402
    AudioSegment,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)

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


def make_source(path: Path, seconds: int = 96) -> None:
    run(
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=1920x1080:rate={FPS}:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate={RATE}:duration={seconds}",
        "-af",
        "pan=stereo|c0=c0|c1=0.9*c0",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        str(RATE),
        "-ac",
        "2",
        "-b:a",
        "192k",
        "-shortest",
        str(path),
    )


def transcript(seconds: int) -> list[Sentence]:
    result: list[Sentence] = []
    for index in range(0, seconds, 5):
        words = []
        for word_index in range(5):
            start = (index + word_index) * RATE
            words.append(
                WordTiming(
                    word=f"palavra{index}_{word_index}",
                    start_sample=start,
                    end_sample=start + int(0.8 * RATE),
                    probability=0.95,
                )
            )
        result.append(
            Sentence(
                id=len(result),
                start_sample=index * RATE,
                end_sample=(index + 5) * RATE,
                text=f"Frase completa numero {index} com cinco palavras.",
                words=words,
            )
        )
    return result


def ass_audit(path: Path, duration: float, fps: int = 30) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    dialogues = [
        line for line in text.splitlines() if line.startswith("Dialogue:")
    ]
    outside = re.sub(r"\{[^}]*\}", "", "\n".join(dialogues))
    timestamps = []
    line_lengths = []
    for line in dialogues:
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        start = _ass_seconds(parts[1])
        end = _ass_seconds(parts[2])
        timestamps.append((start, end))
        visible = re.sub(r"\{[^}]*\}", "", parts[9])
        line_lengths.append(max(len(item) for item in visible.split("\\N")))
    last_end = max((end for _, end in timestamps), default=0.0)
    style_row = next(
        (line for line in text.splitlines() if line.startswith("Style:")), ""
    )
    style_parts = style_row.split(",")
    margin_v = int(style_parts[-2]) if len(style_parts) >= 2 else 0
    return {
        "dialogue_count": len(dialogues),
        "margin_v": margin_v,
        "outside_text": outside,
        "literal_color_tag": "\\c&H" in outside,
        "last_end": round(last_end, 3),
        "clamped": all(0 <= start <= end <= duration - 0.05 for start, end in timestamps),
        "max_line_chars": max(line_lengths, default=0),
        "pos": sorted(set(re.findall(r"\\pos\((\d+),(\d+)\)", text))),
        "wrap_style": "WrapStyle: 2" in text,
        "margin_lr": re.search(r"MarginL, MarginR, MarginV", text) is not None,
    }


def _ass_seconds(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def main() -> int:
    work = Path("/tmp/opencode/vf-cycle2-gate")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    source = work / "source.mp4"
    make_source(source)
    intro = work / "intro.png"
    run("-f", "lavfi", "-i", "color=c=0x0ea5e9:s=1080x1920", "-frames:v", "1", str(intro))

    record, _ = init_project(name="Cycle 2 gate", output=work / "project")
    media = FFmpegAdapter().probe(source)
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        transcript=transcript(96),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=media.duration_frames,
                timeline_in_frame=0,
                timeline_out_frame=media.duration_frames,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=media.duration_frames * RATE // FPS,
                timeline_in_sample=0,
                timeline_out_sample=media.duration_frames * RATE // FPS,
            )
        ],
    )
    state.pipeline.speech_intervals = [(0, media.duration_frames * RATE // FPS)]
    save_project_state(record, state, bump_revision=False)

    started = time.perf_counter()
    result = run_shorts_batch(
        record.project_id,
        [
            {
                "start_sec": 0,
                "end_sec": 30,
                "time_basis": "timeline",
                "title": "Vertical 30",
                "aspect_ratio": "9:16",
                "layout": "FULL_FACE",
                "min_sec": 27,
                "max_sec": 33,
            },
            {
                "start_sec": 30,
                "end_sec": 60,
                "time_basis": "timeline",
                "title": "Feed 30",
                "aspect_ratio": "4:5",
                "layout": "SPLIT_BROLL",
                "min_sec": 27,
                "max_sec": 33,
            },
            {
                "start_sec": 60,
                "end_sec": 90,
                "time_basis": "timeline",
                "title": "Intro 30",
                "aspect_ratio": "9:16",
                "layout": "SPLIT_SCREEN_SAFE",
                "intro_path": str(intro),
                "intro_duration_sec": 2.0,
                "min_sec": 28,
                "max_sec": 35,
            },
        ],
        adapter=FFmpegAdapter(),
    )

    asu_word = AsuWord(
        idx=0,
        w="teste",
        start_sample=5 * RATE,
        end_sample=7 * RATE,
        start_sec=5.0,
        end_sec=7.0,
        p=0.95,
    )
    asu = Asu(
        asu_id="A1",
        start_sample=5 * RATE,
        end_sample=7 * RATE,
        start_sec=5.0,
        end_sec=7.0,
        text="teste",
        words=[asu_word],
    )
    profile = {
        "sample_rate": RATE,
        "hop_samples": 480,
        "db": [float(index % 20 - 30) for index in range(96 * 100)],
    }
    pad_plan = build_plan(
        media,
        [asu],
        [],
        profile=profile,
        noise_events=[],
        review_flags=[],
        pre_roll_ms=110,
        post_roll_ms=190,
    )
    pad_ok = bool(pad_plan.active_spans) and all(
        span.start_sample <= asu.start_sample - int(0.110 * RATE) + 1
        and span.end_sample >= asu.end_sample + int(0.190 * RATE) - 1
        and span.valley_rms_dbfs is not None
        for span in pad_plan.active_spans
    )
    clips = []
    checks: dict[str, bool] = {"pad_floor_110_190": pad_ok}
    for clip in result["clips"]:
        path = Path(clip["path"])
        probe = FFmpegAdapter().probe(path)
        duration = probe.duration_frames / (probe.fps_num / probe.fps_den)
        expected = float(clip["expected_duration_sec"])
        loudness = FFmpegAdapter().measure_loudness(path)
        ass_path = Path(clip["subtitles"]) if clip.get("subtitles") else None
        ass = ass_audit(ass_path, duration) if ass_path and ass_path.is_file() else {}
        clip_data = {
            **clip,
            "duration_sec": round(duration, 3),
            "fps": round(probe.fps_num / probe.fps_den, 3),
            "audio_sample_rate": probe.audio_sample_rate,
            "integrated_lufs": loudness.get("integrated_lufs"),
            "audio_checks": ass,
        }
        clips.append(clip_data)
        checks[f"{clip['title']}_duration"] = abs(duration - expected) <= max(
            2 / FPS, 0.05
        )
        expected_frames = round(expected * FPS)
        frame_tolerance = max(2, len(clip.get("pieces") or []))
        checks[f"{clip['title']}_frames"] = (
            abs(probe.duration_frames - expected_frames) <= frame_tolerance
        )
        checks[f"{clip['title']}_fps"] = abs(probe.fps_num / probe.fps_den - FPS) < 0.01
        checks[f"{clip['title']}_audio"] = int(probe.audio_sample_rate) == RATE
        checks[f"{clip['title']}_loudness"] = abs(
            float(loudness.get("integrated_lufs") or -99) - TARGET_LUFS
        ) <= TOLERANCE_LUFS
        pos = ass.get("pos") or []
        allowed_y = {"1340", "960", "840"}
        if clip["aspect_ratio"] == "9:16":
            zone_ok = bool(pos) and str(pos[0][1]) in allowed_y
        else:
            zone_ok = int(ass.get("margin_v") or 0) == 189
        checks[f"{clip['title']}_safe_zone"] = bool(
            ass.get("clamped")
            and not ass.get("literal_color_tag")
            and ass.get("wrap_style")
            and int(ass.get("max_line_chars") or 0) <= 18
            and int(ass.get("last_end") or 0) <= duration - 0.05
            and zone_ok
        )

    payload = {
        "ok": all(checks.values()),
        "elapsed_sec": round(time.perf_counter() - started, 3),
        "checks": checks,
        "clips": clips,
    }
    out = ROOT / "docs" / "qa-evidence" / "cycle2-gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
