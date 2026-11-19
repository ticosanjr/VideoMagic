"""Canonical media contract shared by ingest, render, export, and QA.

The contract is intentionally small: it validates the properties that caused
silent delivery failures (audio rate/channels/bit depth, alpha, color, exact
frame rate, and duration). Callers should use :func:`assert_media` at the
boundary and treat any failure as a hard error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from videoflow.application.media_integrity import probe_media as _probe_media

MediaKind = Literal[
    "source",
    "audio_master",
    "audio_delivery",
    "overlay",
    "deliverable",
]
ALPHA_PIX_FMTS = frozenset({"yuva420p", "yuva444p10le", "rgba", "bgra", "argb", "abgr"})
SDR_PIX_FMTS = frozenset({"yuv420p", "yuvj420p", "yuv422p", "yuv444p"})
AUDIO_MASTER_RATE = 48_000
AUDIO_MASTER_CHANNELS = 2
AUDIO_MASTER_CODEC = "pcm_s24le"
AUDIO_DELIVERY_CODECS = frozenset({"aac", "libfdk_aac"})
AUDIO_DELIVERY_MIN_BITRATE = 192_000


class MediaContractError(RuntimeError):
    """A media file violates the canonical contract."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: str = "",
        report: MediaReport | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.report = report

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error_code": self.code,
            "message": self.message,
        }
        if self.path:
            payload["path"] = self.path
        if self.report is not None:
            payload["report"] = self.report.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ExpectedMedia:
    duration_sec: float | None = None
    frames: int | None = None
    fps_num: int | None = None
    fps_den: int | None = None
    sample_rate: int | None = None
    channels: int | None = None


@dataclass(slots=True)
class MediaReport:
    ok: bool
    kind: MediaKind
    path: str
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "kind": self.kind,
            "path": self.path,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": dict(self.metrics),
        }


def _stream(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    for stream in payload.get("streams") or []:
        if isinstance(stream, dict) and stream.get("codec_type") == kind:
            return stream
    return {}


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _fps(stream: dict[str, Any]) -> tuple[int, int] | None:
    raw = str(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "")
    if not raw or raw in {"0/0", "N/A"}:
        return None
    left, _, right = raw.partition("/")
    try:
        num = int(left)
        den = int(right or "1")
    except ValueError:
        return None
    if num <= 0 or den <= 0:
        return None
    return num, den


def _bit_rate(stream: dict[str, Any]) -> int | None:
    direct = _int(stream.get("bit_rate"))
    if direct:
        return direct
    tags = stream.get("tags")
    if isinstance(tags, dict):
        return _int(tags.get("BPS"))
    return None


def _audio_metrics(stream: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_rate": _int(stream.get("sample_rate")),
        "channels": _int(stream.get("channels")),
        "codec": str(stream.get("codec_name") or ""),
        "bit_rate": _bit_rate(stream),
        "duration_sec": _float(stream.get("duration")),
    }


def _video_metrics(stream: dict[str, Any]) -> dict[str, Any]:
    fps = _fps(stream)
    return {
        "width": _int(stream.get("width")),
        "height": _int(stream.get("height")),
        "fps_num": fps[0] if fps else None,
        "fps_den": fps[1] if fps else None,
        "fps": round(fps[0] / fps[1], 6) if fps else None,
        "pix_fmt": str(stream.get("pix_fmt") or ""),
        "codec": str(stream.get("codec_name") or ""),
        "color_transfer": str(stream.get("color_transfer") or ""),
        "color_primaries": str(stream.get("color_primaries") or ""),
        "color_space": str(stream.get("color_space") or ""),
        "bits_per_raw_sample": _int(stream.get("bits_per_raw_sample")),
        "duration_sec": _float(stream.get("duration")),
        "nb_frames": _int(stream.get("nb_read_frames")) or _int(stream.get("nb_frames")),
    }


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
            if pix_fmt not in ALPHA_PIX_FMTS:
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


def color_profile(path: str | Path) -> dict[str, Any]:
    """Return the color metadata used to choose a decode/tonemap policy."""

    report = validate_media(path, "source")
    video = report.metrics.get("video") or {}
    transfer = str(video.get("color_transfer") or "")
    pix_fmt = str(video.get("pix_fmt") or "")
    ten_bit = "10le" in pix_fmt or "10be" in pix_fmt
    hdr = transfer in {"smpte2084", "arib-std-b67"}
    return {
        "ok": report.ok,
        "pix_fmt": pix_fmt,
        "color_transfer": transfer,
        "color_primaries": str(video.get("color_primaries") or ""),
        "color_space": str(video.get("color_space") or ""),
        "ten_bit": ten_bit,
        "hdr": hdr,
        "needs_cpu_decode": ten_bit or hdr or pix_fmt in {"yuv422p10le", "yuv420p10le"},
        "needs_tonemap": hdr,
    }


__all__ = [
    "ALPHA_PIX_FMTS",
    "ExpectedMedia",
    "MediaContractError",
    "MediaKind",
    "MediaReport",
    "assert_media",
    "color_profile",
    "validate_alpha",
    "validate_media",
]
