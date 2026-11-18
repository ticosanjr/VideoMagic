"""Post-render audit of the actual deliverable MP4."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.media_integrity import validate_duration
from videoflow.application.qa_media import detect_black, detect_freeze
from videoflow.runtime import find_binary


def _caption_box(platform: str) -> tuple[float, float, float, float]:
    if platform == "youtube":
        return (0.05, 0.72, 0.90, 0.16)
    return (0.05, 0.68, 0.90, 0.18)


def _overlaps(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] <= right[0] or right[2] <= left[0] or left[3] <= right[1] or right[3] <= left[1]
    )


def _overlay_boxes(state: Any, width: int, height: int) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001 - overlay height falls back to square
        Image = None  # type: ignore[assignment]
    for overlay in state.overlays:
        ratio = max(0.0, min(1.0, overlay.width_ratio))
        height_ratio = ratio
        if Image is not None:
            try:
                with Image.open(overlay.path) as image:
                    image_width, image_height = image.size
                if image_width > 0:
                    height_ratio = ratio * (image_height / image_width) * (width / height)
            except OSError:
                pass
        x = max(0.0, min(1.0, overlay.position_x - ratio / 2))
        y = max(0.0, min(1.0, overlay.position_y - height_ratio / 2))
        boxes.append(
            {
                "id": overlay.overlay_id,
                "box": (x, y, min(1.0, x + ratio), min(1.0, y + height_ratio)),
                "start_frame": overlay.start_frame,
                "duration_frames": overlay.duration_frames,
            }
        )
    return boxes


def _contact_sheet(video: Path, target: Path) -> Path | None:
    binary = find_binary("ffmpeg")
    if binary is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            "fps=1/2,scale=320:-2,tile=4x4:padding=4:margin=4",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    return target if completed.returncode == 0 and target.is_file() else None


def audit_final(
    video: Path,
    *,
    output: Path,
    state: Any,
    platforms: list[str] | None = None,
) -> dict[str, Any]:
    video = Path(video).expanduser()
    if not video.is_file():
        raise FileNotFoundError(f"Final video does not exist: {video}")
    media = state.media_info
    expected = 0.0
    if media is not None and media.fps_num:
        frames = max((clip.timeline_out_frame for clip in state.video_segments), default=0)
        expected = frames / (media.fps_num / media.fps_den)
    duration = validate_duration(video, expected) if expected > 0 else None
    issues: list[dict[str, Any]] = []
    issues.extend(detect_black(video))
    issues.extend(detect_freeze(video))
    loudness: dict[str, Any] = {}
    try:
        from videoflow.adapters.ffmpeg import FFmpegAdapter

        loudness = FFmpegAdapter().measure_loudness(video)
    except Exception as exc:  # noqa: BLE001 - advisory
        loudness = {"error": str(exc)}
    width = media.width if media is not None else 0
    height = media.height if media is not None else 0
    selected = platforms or ["shorts", "reels", "tiktok", "youtube"]
    try:
        from videoflow.steps.qa_safezone import SAFE_ZONES

        safe_zones = SAFE_ZONES
    except Exception:  # noqa: BLE001 - safe-zone QA is optional
        safe_zones = {}
    for item in _overlay_boxes(state, width, height) if width and height else []:
        for platform in selected:
            for zone in safe_zones.get(platform, ()):
                zone_box = (zone.x, zone.y, zone.x + zone.width, zone.y + zone.height)
                if _overlaps(item["box"], zone_box):
                    issues.append(
                        {
                            "kind": "safe_zone",
                            "severity": "warning",
                            "platform": platform,
                            "overlay_id": item["id"],
                            "message": f"overlay enters {platform} {zone.reason}",
                        }
                    )
    for platform in selected:
        box = _caption_box(platform)
        if box[2] > 0.99 or box[3] > 0.99:
            issues.append(
                {
                    "kind": "text_cut",
                    "severity": "warning",
                    "platform": platform,
                    "message": "caption box reaches the frame edge",
                }
            )
        for zone in safe_zones.get(platform, ()):
            zone_box = (zone.x, zone.y, zone.x + zone.width, zone.y + zone.height)
            if _overlaps(box, zone_box):
                issues.append(
                    {
                        "kind": "safe_zone",
                        "severity": "warning",
                        "platform": platform,
                        "element": "captions",
                        "message": f"captions enter {platform} {zone.reason}",
                    }
                )
    qa_dir = Path(output).expanduser() / "exports" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    contact = _contact_sheet(video, qa_dir / "final_contact.jpg")
    report = {
        "ok": not any(item.get("severity") == "critical" for item in issues)
        and (duration.ok if duration is not None else True),
        "video": str(video),
        "expected_sec": round(expected, 3),
        "duration": duration.to_dict() if duration is not None else {"ok": True},
        "issues": issues,
        "loudness": loudness,
        "contact_sheet": str(contact) if contact is not None else "",
        "text_cut_check": "deterministic_caption_box",
        "text_cut_limitations": "OCR is optional; verify unusual fonts visually.",
    }
    report_path = qa_dir / "final_qa.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report"] = str(report_path)
    return report


__all__ = ["audit_final"]
