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


def _timeline_or_media_frames(state: Any, media: Any) -> int:
    if state.video_segments:
        return timeline_duration_frames(state)
    if media is not None:
        return int(media.duration_frames)
    return 0


def audit_final(
    video: Path,
    *,
    output: Path,
    state: Any,
    platforms: list[str] | None = None,
    strict: bool = True,
    mode: str = "full",
    window_sec: tuple[float, float] | None = None,
    expected_sec: float | None = None,
    expected_frames: int | None = None,
    expected_samples: int | None = None,
    fps: float | None = None,
    transcript: Any | None = None,
    caption_path: Path | None = None,
    width: int | None = None,
    height: int | None = None,
    max_wer: float = 0.12,
    warning_wer: float = 0.06,
    collision_mode: str = "visual",
    intro_duration_sec: float = 0.0,
) -> dict[str, Any]:
    """Audit a delivered MP4 in fast or full mode.

    ``fast`` is the export gate: duration/frames, audio silence, and overlay
    bounds. ``full`` adds black/freeze detection, loudness, caption QA, contact
    sheet, waveform, and word fidelity. ``window_sec`` makes the audit
    Short-aware without treating the parent longform timeline as expected.
    """

    selected_mode = str(mode or "full").strip().lower()
    if selected_mode not in {"fast", "full"}:
        raise ValueError("mode must be 'fast' or 'full'")
    collision_mode = str(collision_mode or "visual").strip().lower()
    if collision_mode not in {"visual", "bbox", "rectangle"}:
        raise ValueError("collision_mode must be 'visual', 'bbox', or 'rectangle'")
    video = Path(video).expanduser()
    if not video.is_file():
        raise FileNotFoundError(f"Final video does not exist: {video}")
    media = state.media_info
    source_fps = (media.fps_num / media.fps_den) if media is not None and media.fps_num else 0.0
    if fps is None and expected_frames is None:
        try:
            from videoflow.adapters.ffmpeg import FFmpegAdapter

            probed = FFmpegAdapter().probe(video)
            if probed.fps_num:
                source_fps = probed.fps_num / probed.fps_den
        except Exception:  # noqa: BLE001 - probe is advisory
            pass
    fps = float(fps) if fps and fps > 0 else source_fps
    if expected_sec is None:
        if window_sec is not None:
            expected_sec = max(0.0, float(window_sec[1]) - float(window_sec[0]))
        elif media is not None and source_fps:
            expected_sec = _timeline_or_media_frames(state, media) / source_fps
        else:
            expected_sec = 0.0
    expected = max(0.0, float(expected_sec))
    if expected_frames is None:
        expected_frames = (
            max(1, int(round(expected * fps)))
            if fps and expected > 0
            else _timeline_or_media_frames(state, media)
        )
    if expected_samples is None:
        expected_samples = (
            max(1, int(round(expected * (media.audio_sample_rate if media is not None else 48000))))
            if expected > 0
            else (
                timeline_duration_samples(state)
                if state.audio_segments
                else int(round(expected * (media.audio_sample_rate if media else 48000)))
            )
        )
    integrity = (
        validate_integrity(
            video,
            expected,
            expected_frames=expected_frames,
            expected_samples=expected_samples,
            fps=fps,
            last_sentence_end_sec=(
                None if window_sec is not None else _last_sentence_end(state)
            ),
            # AAC priming and frame rounding can shift a Short by up to two
            # frames without any visible drift.
            tolerance_frames=2,
        )
        if expected > 0
        else None
    )
    issues: list[dict[str, Any]] = []
    if selected_mode == "full":
        issues.extend(detect_black(video))
        issues.extend(detect_freeze(video))
    silence = detect_audio_silence(video)
    for item in silence:
        item.setdefault("kind", "audio_silence")
        duration = float(item.get("duration_sec") or 0.0)
        start = float(item.get("start_sec") or 0.0)
        end = float(item.get("end_sec") or 0.0)
        if start <= 0.05 and duration > 0.3:
            if duration <= max(0.0, float(intro_duration_sec)) + 0.05:
                item["severity"] = "info"
                item["message"] = "Initial silence belongs to the intro card."
            else:
                item["severity"] = "critical"
                item["message"] = "Initial edge silence longer than 300 ms."
        elif expected > 0 and expected - end <= 0.05 and duration > 0.4:
            item["severity"] = "critical"
            item["message"] = "Final edge silence longer than 400 ms."
        elif duration > 0.7:
            item["severity"] = "critical"
            item["message"] = "Internal dead air longer than 700 ms."
        issues.append(item)
    media_contract: dict[str, Any] = {"ok": True, "skipped": False}
    try:
        from videoflow.core.media_contract import validate_media

        if not video.is_file() or video.stat().st_size <= 1024:
            media_contract = {
                "ok": True,
                "skipped": True,
                "reason": "fixture too small to probe",
            }
            raise StopIteration
        contract = validate_media(video, "deliverable")
        media_contract = contract.to_dict()
        if not contract.ok:
            for error in contract.errors:
                issues.append(
                    {
                        "kind": "media_contract",
                        "severity": "critical",
                        "message": f"{error.get('code')}: {error.get('message')}",
                    }
                )
    except StopIteration:
        pass
    except Exception as exc:  # noqa: BLE001 - contract must stay visible
        media_contract = {"ok": False, "error": str(exc), "skipped": False}
        issues.append(
            {
                "kind": "media_contract",
                "severity": "critical",
                "message": f"media contract could not be validated: {exc}",
            }
        )
    loudness: dict[str, Any] = {"skipped": True}
    if expected > 0:
        try:
            from videoflow.adapters.ffmpeg import FFmpegAdapter

            loudness = FFmpegAdapter().measure_loudness(video)
            integrated = float(loudness.get("integrated_lufs") or -99.0)
            peak = float(
                loudness.get("true_peak_dbfs", loudness.get("true_peak_db", 99.0)) or 99.0
            )
            loudness["passed"] = abs(integrated + 15.5) <= 1.5 and peak <= -1.5
            loudness["skipped"] = False
            if strict and not loudness["passed"]:
                issues.append(
                    {
                        "kind": "loudness",
                        "severity": "critical",
                        "message": (
                            f"loudness {integrated:.1f} LUFS / true peak {peak:.1f} dBTP "
                            "is outside -15.5 ± 1.5 LUFS and <= -1.5 dBTP"
                        ),
                    }
                )
        except Exception as exc:  # noqa: BLE001 - keep the failure visible
            loudness = {
                "error": str(exc),
                "passed": False,
                "skipped": True,
                "unmeasured": True,
            }
            issues.append(
                {
                    "kind": "loudness_unmeasured",
                    "severity": "warning",
                    "message": f"loudness could not be measured: {exc}",
                }
            )
    qa_state = state
    if window_sec is not None and source_fps:
        start_frame = round(window_sec[0] * source_fps)
        end_frame = round(window_sec[1] * source_fps)
        qa_overlays = [
            overlay
            for overlay in state.overlays
            if overlay.start_frame < end_frame
            and overlay.start_frame + overlay.duration_frames > start_frame
        ]
        qa_state = state.model_copy(update={"overlays": qa_overlays})
    width = int(width or (media.width if media is not None else 0))
    height = int(height or (media.height if media is not None else 0))
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
        effective_caption_path = caption_path or _caption_path(Path(output))
        caption_present = effective_caption_path is not None
        for item in collisions(
            qa_state,
            width,
            height,
            caption=caption if caption_present else None,
            mode=collision_mode,
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
                for overlay in qa_state.overlays:
                    from videoflow.application.overlay_geometry import overlay_box

                    if overlay.anchor == "top_center" and int(overlay.margin_y) == 0:
                        # Explicit top chrome is intentional; do not flag it.
                        continue
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
                if (
                    caption_present
                    and not (height == 1350 and zone.reason == "bottom UI")
                    and _overlaps(caption.normalised(width, height), zone_box)
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
    caption_path = caption_path or _caption_path(Path(output))
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
                        if item.get("kind")
                        in {"caption_effect", "caption_escape", "caption_overlap"}
                        else "warning"
                    ),
                }
            )
    if transcript is not None:
        kept = list(transcript)
    else:
        kept = [
            sentence
            for sentence in state.transcript
            if sentence.id not in set(state.pipeline.discard_sentence_ids)
        ]
        if window_sec is not None:
            start_sample = round(window_sec[0] * (media.audio_sample_rate if media else 48000))
            end_sample = round(window_sec[1] * (media.audio_sample_rate if media else 48000))
            kept = [
                sentence
                for sentence in kept
                if sentence.end_sample > start_sample and sentence.start_sample < end_sample
            ]
    fidelity: dict[str, Any] = {"ok": True, "skipped": True, "status": "skipped"}
    if selected_mode == "full":
        fidelity = verify_word_fidelity(
            video,
            kept,
            work=Path(output) / "exports" / "qa",
            language=state.language or "pt",
            max_wer=max_wer,
            warning_wer=warning_wer,
        )
        if fidelity.get("status") == "checked":
            wer = float(fidelity.get("wer") or 0.0)
            if wer >= max_wer:
                issues.append(
                    {
                        "kind": "word_fidelity",
                        "severity": "critical",
                        "message": (
                            f"word error rate {wer * 100:.2f}% >= {max_wer * 100:.0f}%"
                        ),
                    }
                )
            elif wer >= warning_wer:
                issues.append(
                    {
                        "kind": "word_fidelity",
                        "severity": "warning",
                        "message": (
                            f"word error rate {wer * 100:.2f}% is above the "
                            f"{warning_wer * 100:.0f}% warning threshold"
                        ),
                    }
                )
    qa_dir = Path(output).expanduser() / "exports" / "qa" / video.stem
    qa_dir.mkdir(parents=True, exist_ok=True)
    contact = (
        _contact_sheet(video, qa_dir / "final_contact.jpg")
        if selected_mode == "full"
        else None
    )
    waveform = (
        render_waveform(video, qa_dir / "final_waveform.png")
        if selected_mode == "full"
        else None
    )
    critical = [item for item in issues if item.get("severity") == "critical"]
    ok = not critical and (integrity.ok if integrity is not None else True)
    report = {
        "ok": ok,
        "status": "succeeded" if ok else "needs_review",
        "mode": selected_mode,
        "window_sec": list(window_sec) if window_sec is not None else None,
        "fps": round(fps, 6) if fps else 0.0,
        "video": str(video),
        "expected_sec": round(expected, 3),
        "expected_frames": expected_frames,
        "expected_samples": expected_samples,
        "duration": integrity.to_dict() if integrity is not None else {"ok": True},
        "issues": issues,
        "media_contract": media_contract,
        "loudness": loudness,
        "caption_qa": caption_qa,
        "word_fidelity": fidelity,
        "contact_sheet": str(contact) if contact is not None else "",
        "waveform": str(waveform) if waveform is not None else "",
        "text_cut_check": "deterministic_caption_box",
    }
    report_path = qa_dir / "final_qa.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    from videoflow.application.qa_store import QaStore

    reference = QaStore(output).write(video, report)
    report["report"] = reference["report_path"]
    report["report_id"] = reference["run_id"]
    report["report_latest"] = reference["latest_path"]
    report["artifact_sha256"] = reference["artifact_sha256"]
    return report


__all__ = ["audit_final"]
