"""Canonical final audio stage: dialogue + music + Foley, 48 kHz / 24-bit.

The previous pipeline mixed dialogue, music, and Foley in separate steps with
different sample formats and a single-pass ``loudnorm``. This module is the one
place that produces the delivery audio bed:

1. dialogue cleanup (high-pass + denoise);
2. optional mono repair (left/right imbalance from XLR interfaces);
3. music loop/trim to the timeline duration;
4. sidechain ducking;
5. Foley mix;
6. two-pass linear EBU R128 loudness;
7. 48 kHz stereo PCM 24-bit output.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.core.media_contract import (
    TARGET_LRA,
    TARGET_LUFS,
    TRUE_PEAK_MAX,
    MediaContractError,
    channel_rms,
    needs_mono_repair,
    validate_media,
)
from videoflow.domain.errors import ExportError
from videoflow.runtime import find_binary

from .exact import pad_to_duration
from .finalize_graph import _build_graph, _sfx_chains

DEFAULT_TARGET_LUFS = TARGET_LUFS
DEFAULT_TRUE_PEAK_DB = TRUE_PEAK_MAX
DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_MUSIC_GAIN = 0.22
DEFAULT_SFX_GAIN = 0.55


@dataclass(slots=True)
class AudioFinalizeResult:
    ok: bool
    path: str
    duration_sec: float
    sample_rate: int
    channels: int
    codec: str
    integrated_lufs: float
    true_peak_db: float
    mono_repaired: bool = False
    warnings: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "duration_sec": round(self.duration_sec, 6),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "codec": self.codec,
            "integrated_lufs": round(self.integrated_lufs, 3),
            "true_peak_db": round(self.true_peak_db, 3),
            "mono_repaired": self.mono_repaired,
            "warnings": list(self.warnings),
            "filters": list(self.filters),
        }


def _ffmpeg() -> str:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise ExportError("FFmpeg is required for audio finalization")
    return str(binary)


def _ffprobe() -> str:
    binary = find_binary("ffprobe")
    if binary is None:
        raise ExportError("ffprobe is required for audio finalization")
    return str(binary)


def _probe(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            _ffprobe(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise ExportError(f"ffprobe failed for {path}: {completed.stderr.strip()[-300:]}")
    try:
        payload = json.loads(completed.stdout or "{}")
    except ValueError as exc:
        raise ExportError(f"ffprobe returned invalid JSON for {path}") from exc
    return payload if isinstance(payload, dict) else {}


def _audio_stream(payload: dict[str, Any]) -> dict[str, Any]:
    for stream in payload.get("streams") or []:
        if isinstance(stream, dict) and stream.get("codec_type") == "audio":
            return stream
    return {}


def _duration(path: Path) -> float:
    payload = _probe(path)
    raw = (payload.get("format") or {}).get("duration")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.0


def _channel_rms(path: Path, *, seconds: float = 8.0) -> tuple[float, float]:
    """Compatibility wrapper around the shared media-contract measurement."""

    return channel_rms(path, seconds=seconds)


def _needs_mono_repair(left_db: float, right_db: float) -> str:
    """Compatibility wrapper around the shared mono-repair policy."""

    return needs_mono_repair(left_db, right_db)


def _measure_loudnorm(
    graph: str,
    inputs: list[str],
    *,
    target_lufs: float,
    true_peak_db: float,
) -> dict[str, float]:
    filter_graph = (
        f"{graph};[mix]loudnorm=I={target_lufs}:TP={true_peak_db}:LRA={TARGET_LRA}:"
        "print_format=json[measured]"
    )
    completed = subprocess.run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "info",
            "-y",
            *inputs,
            "-filter_complex",
            filter_graph,
            "-map",
            "[measured]",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    text = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', text, re.DOTALL)
    if completed.returncode != 0 or match is None:
        raise ExportError(
            "loudnorm measurement failed: "
            + (text.strip()[-1000:] or f"exit {completed.returncode}")
        )
    try:
        payload = json.loads(match.group(0))
    except ValueError as exc:
        raise ExportError("loudnorm returned invalid JSON") from exc
    try:
        return {
            "input_i": float(payload["input_i"]),
            "input_tp": float(payload["input_tp"]),
            "input_lra": float(payload["input_lra"]),
            "input_thresh": float(payload["input_thresh"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ExportError("loudnorm returned incomplete measurements") from exc


def finalize_audio(
    voice_path: str | Path,
    output: str | Path,
    *,
    music_path: str | Path | None = None,
    sfx_path: str | Path | None = None,
    sfx_events: list[dict[str, Any]] | None = None,
    duration_sec: float | None = None,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    true_peak_db: float = DEFAULT_TRUE_PEAK_DB,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    music_gain: float = DEFAULT_MUSIC_GAIN,
    sfx_gain: float = DEFAULT_SFX_GAIN,
    ducking: bool = True,
    music_gain_db: float | None = None,
    target_name: str = "final_mix.wav",
) -> AudioFinalizeResult:
    """Render the canonical final audio bed and return measured loudness."""

    voice = Path(voice_path).expanduser()
    if not voice.is_file():
        raise ExportError(f"Dialogue audio does not exist: {voice}")
    root = Path(output).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    target = root / "audio" / target_name
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.parent / ".final_mix.tmp.wav"
    music = Path(music_path).expanduser() if music_path else None
    if music is not None and not music.is_file():
        raise ExportError(f"Music bed does not exist: {music}")
    duration = float(duration_sec) if duration_sec is not None else _duration(voice)
    if duration <= 0:
        raise ExportError("Audio duration must be positive")
    left_db, right_db = _channel_rms(voice)
    mono_repair = _needs_mono_repair(left_db, right_db)
    warnings: list[str] = []
    if mono_repair:
        warnings.append(f"mono repaired from the {mono_repair} channel")
    if music_gain_db is not None:
        music_gain = 10 ** (float(music_gain_db) / 20.0)
    requested_events = [item for item in (sfx_events or []) if isinstance(item, dict)]
    if sfx_path:
        requested_events.append({"path": str(sfx_path), "start_sec": 0.0, "gain_db": 0.0})
    valid_events: list[dict[str, Any]] = []
    for event in requested_events:
        path = Path(str(event.get("path") or "")).expanduser()
        if path.is_file():
            valid_events.append({**event, "path": str(path)})
        else:
            warnings.append(f"SFX event is missing and was skipped: {path}")
    if requested_events and not valid_events:
        raise ExportError("No SFX events could be mixed; check the event paths.")
    graph = _build_graph(
        duration=duration,
        mono_repair=mono_repair,
        music=music is not None,
        sfx=False,
        music_gain=max(0.0, min(1.0, float(music_gain))),
        sfx_gain=max(0.0, min(1.0, float(sfx_gain))),
        ducking=bool(ducking),
        finalize_mix=not bool(valid_events),
    )
    inputs = ["-i", str(voice)]
    if music is not None:
        inputs.extend(["-i", str(music)])
    sfx_chains, sfx_inputs, sfx_labels = _sfx_chains(
        valid_events,
        first_input=1 + (1 if music is not None else 0),
        duration=duration,
        sfx_gain=max(0.0, min(1.0, float(sfx_gain))),
    )
    if sfx_chains:
        graph = (
            graph
            + ";"
            + ";".join(sfx_chains)
            + ";[mix0]"
            + "".join(sfx_labels)
            + f"amix=inputs={1 + len(sfx_labels)}:normalize=0[mix]"
        )
        inputs.extend(sfx_inputs)
    measured = _measure_loudnorm(
        graph,
        inputs,
        target_lufs=float(target_lufs),
        true_peak_db=float(true_peak_db),
    )
    loudnorm = (
        f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA={TARGET_LRA}:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        "linear=true"
    )
    final_graph = (
        f"{graph};[mix]apad=whole_dur={duration:.6f},"
        f"atrim=0:{duration:.6f},asetpts=PTS-STARTPTS,{loudnorm},"
        "aformat=sample_fmts=s32:sample_rates=48000:channel_layouts=stereo,"
        f"apad=whole_dur={duration:.6f},atrim=end_sample={int(round(duration * 48000))},"
        "asetpts=PTS-STARTPTS[out]"
    )
    command = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *inputs,
        "-filter_complex",
        final_graph,
        "-map",
        "[out]",
        "-t",
        f"{duration:.6f}",
        "-ar",
        str(int(sample_rate)),
        "-ac",
        "2",
        "-c:a",
        "pcm_s24le",
        str(temp),
    ]
    temp.unlink(missing_ok=True)
    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=900)
    if completed.returncode != 0 or not temp.is_file():
        temp.unlink(missing_ok=True)
        raise ExportError(
            "Audio finalization failed: "
            + (completed.stderr.strip()[-600:] or f"exit {completed.returncode}")
        )
    # ``loudnorm`` upsamples internally and can shave a couple of frames from
    # the tail. Re-pad/trim once on a plain PCM pass so the master length is
    # sample-exact against the video timeline.
    if abs(_duration(temp) - duration) > 0.001:
        pad_to_duration(temp, duration)
    try:
        contract = validate_media(temp, "audio_master")
    except MediaContractError as exc:
        temp.unlink(missing_ok=True)
        raise ExportError(f"Audio finalization violated the media contract: {exc.message}") from exc
    if not contract.ok:
        temp.unlink(missing_ok=True)
        raise ExportError(f"Audio finalization violated the media contract: {contract.to_dict()}")
    os.replace(temp, target)
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    loudness = FFmpegAdapter().measure_loudness(target)
    return AudioFinalizeResult(
        ok=True,
        path=str(target),
        duration_sec=duration,
        sample_rate=int(sample_rate),
        channels=2,
        codec="pcm_s24le",
        integrated_lufs=float(loudness.get("integrated_lufs") or -99.0),
        true_peak_db=float(
            loudness.get("true_peak_dbfs", loudness.get("true_peak_db", 99.0)) or 99.0
        ),
        mono_repaired=bool(mono_repair),
        warnings=warnings,
        filters=[loudnorm],
    )


__all__ = [
    "AudioFinalizeResult",
    "DEFAULT_MUSIC_GAIN",
    "DEFAULT_SAMPLE_RATE",
    "DEFAULT_SFX_GAIN",
    "DEFAULT_TARGET_LUFS",
    "DEFAULT_TRUE_PEAK_DB",
    "finalize_audio",
]
