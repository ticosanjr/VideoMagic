"""Lightweight human curation previews: music, B-roll, SFX, and a one-minute sample."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import ExportError
from videoflow.domains.audio.synth import compose_music, synthesize_foley
from videoflow.runtime import find_binary


def _ffmpeg() -> str:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise ExportError("FFmpeg is required for curation previews")
    return binary


def _voice(project_id: str) -> Path | None:
    record = get_project(project_id)
    for relative in ("audio/master.wav", "audio/final.wav"):
        path = Path(record.output) / relative
        if path.is_file():
            return path
    state = load_project_state(record)
    if state.media_info is not None:
        return Path(state.media_info.source_path).expanduser()
    return None


def build_music_candidates(project_id: str) -> list[dict[str, Any]]:
    record = get_project(project_id)
    directory = Path(record.output) / "curation" / "music"
    directory.mkdir(parents=True, exist_ok=True)
    voice = _voice(project_id)
    candidates: list[dict[str, Any]] = []
    for index, (seed, bpm) in enumerate(((7, 90), (19, 104), (31, 76)), start=1):
        label = f"M{index}"
        folder = directory / label
        composed = compose_music(
            folder,
            duration_sec=15.0,
            bpm=float(bpm),
            seed=seed,
            max_loop_seconds=15.0,
        )
        bed = Path(str((composed.get("files") or {}).get("mix") or ""))
        preview = folder / f"{label}-preview.wav"
        if voice is not None and voice.is_file():
            _mix_preview(voice, bed, preview)
        else:
            preview = bed
        candidates.append(
            {
                "id": label,
                "bpm": bpm,
                "bed": str(bed),
                "preview": str(preview),
                "duration_sec": 15.0,
            }
        )
    return candidates


def _mix_preview(voice: Path, bed: Path, target: Path) -> None:
    command = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(voice),
        "-i",
        str(bed),
        "-filter_complex",
        "[0:a]atrim=0:15,asetpts=PTS-STARTPTS,asplit=2[voice][side];"
        "[1:a]volume=0.22,atrim=0:15,asetpts=PTS-STARTPTS[music];"
        "[music][side]sidechaincompress=threshold=0.03:ratio=8:"
        "attack=20:release=250[ducked];"
        "[voice][ducked]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map",
        "[a]",
        "-c:a",
        "pcm_s24le",
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ExportError("Music preview mix failed: " + completed.stderr[-400:])


def build_broll_contact_sheet(project_id: str) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    source = Path(media.source_path).expanduser()
    if not source.is_file():
        raise ExportError(f"Source does not exist: {source}")
    directory = Path(record.output) / "curation" / "broll"
    directory.mkdir(parents=True, exist_ok=True)
    duration = media.duration_frames / max(0.001, media.fps_num / media.fps_den)
    frames: list[Path] = []
    for index, ratio in enumerate((0.2, 0.5, 0.8), start=1):
        target = directory / f"candidate-{index}.jpg"
        completed = subprocess.run(
            [
                _ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{max(0.1, duration * ratio):.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0 and target.is_file():
            frames.append(target)
    sheet = _contact_sheet(frames, directory / "broll-contact.jpg")
    return {
        "ok": bool(sheet),
        "contact_sheet": str(sheet) if sheet else "",
        "candidates": [
            {"id": chr(64 + index), "path": str(path), "frame": index}
            for index, path in enumerate(frames, start=1)
        ],
    }


def _contact_sheet(frames: list[Path], target: Path) -> Path | None:
    if not frames:
        return None
    from PIL import Image, ImageDraw

    images = []
    for path in frames:
        with Image.open(path) as source:
            images.append(source.convert("RGB").resize((480, 270)))
    sheet = Image.new("RGB", (480 * len(images), 310), "#111111")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(images):
        sheet.paste(image, (index * 480, 0))
        draw.text((index * 480 + 12, 282), f"[1{chr(65 + index)}]", fill="#ffffff")
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, quality=90)
    return target


def build_sfx_demo(project_id: str) -> dict[str, Any]:
    record = get_project(project_id)
    directory = Path(record.output) / "curation" / "sfx"
    directory.mkdir(parents=True, exist_ok=True)
    cues = [
        {"kind": "whoosh", "start_sec": 0.0, "gain": 0.35},
        {"kind": "impact", "start_sec": 3.0, "gain": 0.45},
        {"kind": "click", "start_sec": 6.0, "gain": 0.3},
    ]
    payload = synthesize_foley(directory, cues)
    files = [Path(str(item["path"])) for item in payload.get("cues", []) if item.get("path")]
    preview = directory / "sfx-demo-10s.wav"
    if files:
        inputs: list[str] = []
        chains: list[str] = []
        for index, item in enumerate(files):
            inputs.extend(["-i", str(item)])
            delay = int(cues[index]["start_sec"] * 1000) if index < len(cues) else index * 3000
            chains.append(f"[{index}:a]adelay={delay}|{delay}[s{index}]")
        mix_inputs = "".join(f"[s{index}]" for index in range(len(files)))
        chains.append(
            f"{mix_inputs}amix=inputs={len(files)}:duration=longest,"
            "atrim=0:10,apad=whole_dur=10,asetpts=PTS-STARTPTS[a]"
        )
        completed = subprocess.run(
            [
                _ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                *inputs,
                "-filter_complex",
                ";".join(chains),
                "-map",
                "[a]",
                "-c:a",
                "pcm_s24le",
                str(preview),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            preview = files[0]
    else:
        preview = directory / "sfx-demo-10s.wav"
    return {
        "ok": True,
        **payload,
        "preview": str(preview),
        "duration_sec": 10.0,
    }


def build_minute_sample(project_id: str) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    if state.media_info is None:
        raise ExportError("Project has no media")
    delivered = Path(record.output) / "exports" / "youtube_master.mp4"
    if not delivered.is_file():
        delivered = Path(record.output) / "exports" / "final_youtube.mp4"
    source = delivered if delivered.is_file() else Path(state.media_info.source_path).expanduser()
    target = Path(record.output) / "curation" / "sample-1min.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "0",
            "-t",
            "60",
            "-i",
            str(source),
            "-c",
            "copy",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        raise ExportError("Minute sample failed: " + completed.stderr[-400:])
    return {"ok": True, "path": str(target), "duration_sec": 60.0}


def curation_manifest(project_id: str) -> dict[str, Any]:
    music = build_music_candidates(project_id)
    broll = build_broll_contact_sheet(project_id)
    sfx = build_sfx_demo(project_id)
    sample = build_minute_sample(project_id)
    payload = {"ok": True, "music": music, "broll": broll, "sfx": sfx, "sample": sample}
    record = get_project(project_id)
    target = Path(record.output) / "curation" / "manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["path"] = str(target)
    return payload


__all__ = [
    "build_broll_contact_sheet",
    "build_minute_sample",
    "build_music_candidates",
    "build_sfx_demo",
    "curation_manifest",
]
