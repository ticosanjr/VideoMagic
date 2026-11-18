"""Post-render audit of the actual deliverable MP4."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.media_integrity import validate_integrity
from videoflow.application.overlay_geometry import caption_box, collisions
from videoflow.application.qa_caption import audit_ass
from videoflow.application.qa_media import (
    detect_audio_silence,
    detect_black,
    detect_freeze,
    render_waveform,
)
from videoflow.application.qa_word_fidelity import verify_word_fidelity
from videoflow.exporters.common import timeline_duration_frames, timeline_duration_samples
from videoflow.runtime import find_binary


def _overlaps(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] <= right[0] or right[2] <= left[0] or left[3] <= right[1] or right[3] <= left[1]
    )


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
            "fps=1/2,scale=320:-2,tile=3x2:padding=4:margin=4",
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


def _last_sentence_end(state: Any) -> float | None:
    from videoflow.application.time_map import last_speech_timeline_sec

    return last_speech_timeline_sec(state)


def _caption_path(output: Path) -> Path | None:
    for relative in ("captions/captions.ass", "subtitles.ass"):
        path = output / relative
        if path.is_file():
            return path
    return None


def audit_final(
    video: Path,
    *,
    output: Path,
    state: Any,
    platforms: list[str] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    video = Path(video).expanduser()
    if not video.is_file():
        raise FileNotFoundError(f"Final video does not exist: {video}")
    media = state.media_info
    expected = 0.0
    expected_frames = 0
    expected_samples = 0
    fps = 0.0
    if media is not None and media.fps_num:
        fps = media.fps_num / media.fps_den
        expected_frames = timeline_duration_frames(state)
        expected_samples = timeline_duration_samples(state)
        expected = expected_frames / fps if fps else 0.0
    integrity = (
        validate_integrity(
            video,
            expected,
            expected_frames=expected_frames,
            expected_samples=expected_samples,
            fps=fps,
            last_sentence_end_sec=_last_sentence_end(state),
        )
        if expected > 0
        else None
    )
    issues: list[dict[str, Any]] = []
    issues.extend(detect_black(video))
    issues.extend(detect_freeze(video))
    silence = detect_audio_silence(video)
    for item in silence:
        item.setdefault("kind", "audio_silence")
        duration = float(item.get("duration_sec") or 0.0)
        start = float(item.get("start_sec") or 0.0)
        end = float(item.get("end_sec") or 0.0)
        if start <= 0.05 and duration > 0.3:
            item["severity"] = "critical"
            item["message"] = "Initial edge silence longer than 300 ms."
        elif expected > 0 and expected - end <= 0.05 and duration > 0.4:
            item["severity"] = "critical"
            item["message"] = "Final edge silence longer than 400 ms."
        elif duration > 0.7:
            item["severity"] = "critical"
            item["message"] = "Internal dead air longer than 700 ms."
        issues.append(item)
    loudness: dict[str, Any] = {}
    try:
        from videoflow.adapters.ffmpeg import FFmpegAdapter

        loudness = FFmpegAdapter().measure_loudness(video)
        integrated = float(loudness.get("integrated_lufs") or -99.0)
        peak = float(
            loudness.get("true_peak_dbfs", loudness.get("true_peak_db", 99.0)) or 99.0
        )
        loudness["passed"] = abs(integrated + 16.0) <= 1.0 and peak <= -1.0
        if strict and not loudness["passed"]:
            issues.append(
                {
                    "kind": "loudness",
                    "severity": "critical",
                    "message": (
                        f"loudness {integrated:.1f} LUFS / true peak {peak:.1f} dBTP "
                        "is outside -16 ± 1 LUFS and <= -1.0 dBTP"
                    ),
                }
            )
    except Exception as exc:  # noqa: BLE001 - optional measurement
        loudness = {"error": str(exc), "passed": True}
    width = media.width if media is not None else 0
    height = media.height if media is not None else 0
    vertical = bool(width and height and height > width)
    selected = platforms or (
        ["shorts", "reels", "tiktok"]
        if vertical
        else ["youtube_16_9"]
    )
    try:
        from videoflow.steps.qa_safezone import SAFE_ZONES

        safe_zones = SAFE_ZONES
    except Exception:  # noqa: BLE001 - safe-zone QA is optional
        safe_zones = {}
    if width and height:
        style = state.modules_config.shorts.caption_style
        caption = caption_box(style, width, height)
        caption_present = _caption_path(Path(output)) is not None
        for item in collisions(
            state,
            width,
            height,
            caption=caption if caption_present else None,
        ):
            issues.append(
                {
                    **item,
                    "severity": "critical",
                    "message": f"{item['kind']} with {item['overlap_px']} px overlap",
                }
            )
        for platform in selected:
            for zone in safe_zones.get(platform, ()):
                zone_box = (zone.x, zone.y, zone.x + zone.width, zone.y + zone.height)
                for overlay in state.overlays:
                    from videoflow.application.overlay_geometry import overlay_box

                    box = overlay_box(overlay, width, height)
                    if _overlaps(box.normalised(width, height), zone_box):
                        issues.append(
                            {
                                "kind": "safe_zone",
                                "severity": "warning",
                                "platform": platform,
                                "overlay_id": overlay.overlay_id,
                                "message": f"overlay enters {platform} {zone.reason}",
                            }
                        )
                if caption_present and _overlaps(
                    caption.normalised(width, height), zone_box
                ):
                    issues.append(
                        {
                            "kind": "safe_zone",
                            "severity": "critical",
                            "platform": platform,
                            "element": "captions",
                            "message": f"captions enter {platform} {zone.reason}",
                        }
                    )
    caption_path = _caption_path(Path(output))
    caption_qa: dict[str, Any] = {"ok": True, "skipped": True}
    if caption_path is not None:
        style = state.modules_config.shorts.caption_style
        caption_qa = audit_ass(
            caption_path,
            effect=style.effect,
            max_chars=round(style.max_width * (width or 1080) / max(1.0, style.font_size * 0.55)),
        )
        caption_qa.setdefault("skipped", False)
        for item in caption_qa.get("issues", []):
            issues.append(
                {
                    **item,
                    "severity": (
                        "critical"
                        if item.get("kind") in {"caption_effect", "caption_escape"}
                        else "warning"
                    ),
                }
            )
    kept = [
        sentence
        for sentence in state.transcript
        if sentence.id not in set(state.pipeline.discard_sentence_ids)
    ]
    fidelity = verify_word_fidelity(
        video,
        kept,
        work=Path(output) / "exports" / "qa",
        language=state.language or "pt",
    )
    if fidelity.get("status") == "checked" and not fidelity.get("passed"):
        issues.append(
            {
                "kind": "word_fidelity",
                "severity": "critical",
                "message": f"word error rate {float(fidelity.get('wer') or 0) * 100:.2f}% >= 3%",
            }
        )
    qa_dir = Path(output).expanduser() / "exports" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    contact = _contact_sheet(video, qa_dir / "final_contact.jpg")
    waveform = render_waveform(video, qa_dir / "final_waveform.png")
    critical = [item for item in issues if item.get("severity") == "critical"]
    ok = not critical and (integrity.ok if integrity is not None else True)
    report = {
        "ok": ok,
        "status": "succeeded" if ok else "needs_review",
        "video": str(video),
        "expected_sec": round(expected, 3),
        "expected_frames": expected_frames,
        "expected_samples": expected_samples,
        "duration": integrity.to_dict() if integrity is not None else {"ok": True},
        "issues": issues,
        "loudness": loudness,
        "caption_qa": caption_qa,
        "word_fidelity": fidelity,
        "contact_sheet": str(contact) if contact is not None else "",
        "waveform": str(waveform) if waveform is not None else "",
        "text_cut_check": "deterministic_caption_box",
    }
    report_path = qa_dir / "final_qa.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report"] = str(report_path)
    return report


__all__ = ["audit_final"]
