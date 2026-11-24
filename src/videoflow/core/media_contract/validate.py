"""Canonical media validation for every delivery boundary."""

from __future__ import annotations

from pathlib import Path

from videoflow.application.media_integrity import probe_media as _probe_media
from videoflow.core.media_contract.constants import (
    ALPHA_PIX_FMTS,
    AUDIO_DELIVERY_CODECS,
    AUDIO_DELIVERY_MIN_BITRATE,
    AUDIO_MASTER_CHANNELS,
    AUDIO_MASTER_CODEC,
    AUDIO_MASTER_RATE,
    MediaKind,
)
from videoflow.core.media_contract.metrics import (
    _audio_metrics,
    _float,
    _int,
    _stream,
    _video_metrics,
)
from videoflow.core.media_contract.models import (
    ExpectedMedia,
    MediaContractError,
    MediaReport,
)


def _add_error(report: MediaReport, code: str, message: str) -> None:
    report.errors.append({"code": code, "message": message})


def _add_warning(report: MediaReport, code: str, message: str) -> None:
    report.warnings.append({"code": code, "message": message})


def validate_media(
    path: str | Path,
    kind: MediaKind,
    expected: ExpectedMedia | None = None,
) -> MediaReport:
    """Probe a file and validate the canonical contract for ``kind``."""

    source = Path(path).expanduser()
    report = MediaReport(ok=True, kind=kind, path=str(source))
    if not source.is_file():
        _add_error(report, "media_not_found", f"media does not exist: {source}")
        report.ok = False
        return report
    try:
        payload = _probe_media(
            source,
            count_frames=kind == "deliverable"
            or (expected is not None and expected.frames is not None),
        )
    except Exception as exc:  # noqa: BLE001 - probe errors become contract errors
        _add_error(report, "media_probe_failed", str(exc))
        report.ok = False
        return report
    video = _stream(payload, "video")
    audio = _stream(payload, "audio")
    report.metrics = {
        "format": {
            "duration_sec": _float((payload.get("format") or {}).get("duration")),
            "size": _int((payload.get("format") or {}).get("size")),
        },
        "video": _video_metrics(video) if video else None,
        "audio": _audio_metrics(audio) if audio else None,
    }
    if kind == "source":
        if not video and not audio:
            _add_error(report, "media_empty", "source has no audio or video stream")
    elif kind in {"audio_master", "audio_delivery"}:
        if not audio:
            _add_error(report, "audio_missing", "file has no audio stream")
        else:
            metrics = report.metrics["audio"]
            if metrics["sample_rate"] != AUDIO_MASTER_RATE:
                _add_error(
                    report,
                    "audio_sample_rate",
                    f"audio must be 48000 Hz, got {metrics['sample_rate']}",
                )
            if metrics["channels"] != AUDIO_MASTER_CHANNELS:
                _add_error(
                    report,
                    "audio_channels",
                    f"audio must have 2 channels, got {metrics['channels']}",
                )
            if kind == "audio_master" and metrics["codec"] != AUDIO_MASTER_CODEC:
                _add_error(
                    report,
                    "audio_codec",
                    f"audio master must be {AUDIO_MASTER_CODEC}, got {metrics['codec']}",
                )
            if kind == "audio_delivery":
                if metrics["codec"] not in AUDIO_DELIVERY_CODECS:
                    _add_error(
                        report,
                        "audio_codec",
                        f"audio delivery must be AAC, got {metrics['codec']}",
                    )
                if metrics["bit_rate"] and metrics["bit_rate"] < AUDIO_DELIVERY_MIN_BITRATE:
                    _add_error(
                        report,
                        "audio_bitrate",
                        "audio delivery bitrate is below 192 kbps",
                    )
    elif kind == "overlay":
        if not video:
            _add_error(report, "overlay_video_missing", "overlay has no video stream")
        else:
            pix_fmt = str(report.metrics["video"]["pix_fmt"] or "")
            alpha_mode = str(report.metrics["video"].get("alpha_mode") or "")
            if pix_fmt not in ALPHA_PIX_FMTS and alpha_mode != "1":
                _add_error(
                    report,
                    "alpha_channel_missing",
                    f"overlay must carry alpha, got pix_fmt={pix_fmt or 'unknown'}",
                )
    elif kind == "deliverable":
        if not video:
            _add_error(report, "video_missing", "deliverable has no video stream")
        if not audio:
            _add_error(report, "audio_missing", "deliverable has no audio stream")
        if video:
            metrics = report.metrics["video"]
            width = metrics["width"] or 0
            height = metrics["height"] or 0
            if width % 2 or height % 2:
                _add_error(
                    report,
                    "odd_dimensions",
                    f"deliverable dimensions must be even, got {width}x{height}",
                )
            if not metrics["fps_num"]:
                _add_error(report, "fps_unknown", "deliverable has no frame rate")
        if audio:
            metrics = report.metrics["audio"]
            if metrics["sample_rate"] != AUDIO_MASTER_RATE:
                _add_error(
                    report,
                    "audio_sample_rate",
                    f"deliverable audio must be 48000 Hz, got {metrics['sample_rate']}",
                )
    if expected is not None:
        _check_expected(report, expected)
    report.ok = not report.errors
    return report


def _check_expected(report: MediaReport, expected: ExpectedMedia) -> None:
    format_sec = report.metrics.get("format", {}).get("duration_sec")
    video = report.metrics.get("video") or {}
    audio = report.metrics.get("audio") or {}
    if expected.duration_sec is not None and format_sec is not None:
        tolerance = 1.0 / 30.0 + 1e-6
        if expected.fps_num and expected.fps_den:
            tolerance = expected.fps_den / expected.fps_num + 1e-6
        if audio:
            # AAC priming/padding is 1024-2048 samples; at 60 fps that is
            # larger than one video frame and must not fail the duration gate.
            tolerance = max(tolerance, 0.045)
        if abs(float(format_sec) - float(expected.duration_sec)) > tolerance:
            _add_error(
                report,
                "duration_mismatch",
                f"duration {format_sec:.6f}s != expected {expected.duration_sec:.6f}s",
            )
    if (
        expected.frames is not None
        and video.get("nb_frames") is not None
        and abs(int(video["nb_frames"]) - int(expected.frames)) > 1
    ):
        _add_error(
            report,
            "frame_count_mismatch",
            f"frames {video['nb_frames']} != expected {expected.frames}",
        )
    if expected.fps_num and expected.fps_den and video.get("fps_num") and (
        int(video["fps_num"]) * int(expected.fps_den)
        != int(expected.fps_num) * int(video["fps_den"])
    ):
        _add_error(
            report,
            "fps_mismatch",
            f"fps {video['fps_num']}/{video['fps_den']} != "
            f"{expected.fps_num}/{expected.fps_den}",
        )
    if (
        expected.sample_rate is not None
        and audio.get("sample_rate") is not None
        and int(audio["sample_rate"]) != int(expected.sample_rate)
    ):
        _add_error(
            report,
            "audio_sample_rate",
            f"audio sample rate {audio['sample_rate']} != {expected.sample_rate}",
        )
    if (
        expected.channels is not None
        and audio.get("channels") is not None
        and int(audio["channels"]) != int(expected.channels)
    ):
        _add_error(
            report,
            "audio_channels",
            f"audio channels {audio['channels']} != {expected.channels}",
        )


def source_needs_normalization(path: str | Path) -> list[str]:
    """Return reasons the ingest stage must transcode the source."""

    report = validate_media(path, "source")
    video = report.metrics.get("video") or {}
    reasons: list[str] = []
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width and height and (width % 2 or height % 2):
        reasons.append("odd_dimensions")
    pix_fmt = str(video.get("pix_fmt") or "")
    if pix_fmt and pix_fmt not in {"yuv420p", "yuvj420p"}:
        reasons.append("pixel_format")
    transfer = str(video.get("color_transfer") or "")
    if transfer and transfer not in {"bt709", "smpte170m", "bt470bg", ""}:
        reasons.append("color_transfer")
    fps_num = int(video.get("fps_num") or 0)
    fps_den = int(video.get("fps_den") or 0)
    if fps_num and fps_den:
        fps = fps_num / fps_den
        if abs(fps - round(fps)) > 0.001 or round(fps) not in {24, 25, 30, 50, 60}:
            reasons.append("fps")
    return reasons


def assert_media(
    path: str | Path,
    kind: MediaKind,
    expected: ExpectedMedia | None = None,
) -> MediaReport:
    """Validate and raise :class:`MediaContractError` on the first failure."""

    report = validate_media(path, kind, expected)
    if report.ok:
        return report
    first = report.errors[0] if report.errors else {"code": "media_contract", "message": "invalid"}
    raise MediaContractError(
        str(first.get("code") or "media_contract"),
        str(first.get("message") or "media contract failed"),
        path=str(Path(path).expanduser()),
        report=report,
    )


def validate_alpha(path: str | Path) -> MediaReport:
    """Validate that a video/image overlay carries a real alpha channel."""

    return validate_media(path, "overlay")


def assert_audio_duration(
    path: str | Path,
    expected_sec: float,
    *,
    tolerance_sec: float = 1.0 / 30.0,
) -> float:
    """Fail when a rendered audio master does not match the timeline duration.

    A half/double sample-rate mistake (the historical 2:1 bug) shows up here as
    a duration far outside one frame of tolerance.
    """

    report = validate_media(path, "audio_master")
    duration = (report.metrics.get("format") or {}).get("duration_sec")
    if duration is None:
        raise MediaContractError(
            "audio_duration_unknown",
            f"could not measure audio duration: {path}",
            path=str(Path(path).expanduser()),
            report=report,
        )
    delta = abs(float(duration) - float(expected_sec))
    if delta > max(0.0, float(tolerance_sec)):
        raise MediaContractError(
            "audio_duration_mismatch",
            f"audio duration {float(duration):.6f}s != timeline "
            f"{float(expected_sec):.6f}s (delta {delta:.6f}s)",
            path=str(Path(path).expanduser()),
            report=report,
        )
    return float(duration)
