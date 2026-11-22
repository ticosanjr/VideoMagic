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
    text = completed.stderr or ""
    start = text.rfind("{")
    end = text.rfind("}")
    if completed.returncode != 0 or start < 0 or end <= start:
        raise ExportError(
            "loudnorm measurement failed: "
            + (text.strip()[-500:] or f"exit {completed.returncode}")
        )
    try:
        payload = json.loads(text[start : end + 1])
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


def _build_graph(
    *,
    duration: float,
    mono_repair: str,
    music: bool,
    sfx: bool,
    music_gain: float,
    sfx_gain: float,
) -> str:
    voice_filters = []
    if mono_repair == "left":
        voice_filters.append("pan=stereo|c0=c0|c1=c0")
    elif mono_repair == "right":
        voice_filters.append("pan=stereo|c0=c1|c1=c1")
    voice_filters.extend(
        [
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
            "aresample=48000",
            "highpass=f=80",
            "afftdn=nf=-30",
        ]
    )
    chains = [f"[0:a]{','.join(voice_filters)},apad=whole_dur={duration:.6f}[voice]"]
    if music:
        chains.append("[voice]asplit=2[voice_sc][voice_mix]")
        chains.append(
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"aresample=48000,aloop=loop=-1:size=2880000,atrim=0:{duration:.6f},"
            f"volume={music_gain:.3f}[music]"
        )
        chains.append(
            "[music][voice_sc]sidechaincompress=threshold=0.02:ratio=8:"
            "attack=20:release=300[ducked]"
        )
        chains.append("[voice_mix][ducked]amix=inputs=2:weights=1 1:normalize=0[mix0]")
    else:
        chains.append("[voice]anull[mix0]")
    if sfx:
        chains.append(
            f"[2:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"aresample=48000,atrim=0:{duration:.6f},apad=whole_dur={duration:.6f},"
            f"volume={sfx_gain:.3f}[sfx]"
        )
        chains.append("[mix0][sfx]amix=inputs=2:weights=1 1:normalize=0[mix]")
    else:
        chains.append("[mix0]anull[mix]")
    return ";".join(chains)


def finalize_audio(
    voice_path: str | Path,
    output: str | Path,
    *,
    music_path: str | Path | None = None,
    sfx_path: str | Path | None = None,
    duration_sec: float | None = None,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    true_peak_db: float = DEFAULT_TRUE_PEAK_DB,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    music_gain: float = DEFAULT_MUSIC_GAIN,
    sfx_gain: float = DEFAULT_SFX_GAIN,
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
    music = Path(music_path).expanduser() if music_path else None
    sfx = Path(sfx_path).expanduser() if sfx_path else None
    if music is not None and not music.is_file():
        raise ExportError(f"Music bed does not exist: {music}")
    if sfx is not None and not sfx.is_file():
        raise ExportError(f"Foley track does not exist: {sfx}")
    duration = float(duration_sec) if duration_sec is not None else _duration(voice)
    if duration <= 0:
        raise ExportError("Audio duration must be positive")
    left_db, right_db = _channel_rms(voice)
    mono_repair = _needs_mono_repair(left_db, right_db)
    warnings: list[str] = []
    if mono_repair:
        warnings.append(f"mono repaired from the {mono_repair} channel")
    graph = _build_graph(
        duration=duration,
        mono_repair=mono_repair,
        music=music is not None,
        sfx=sfx is not None,
        music_gain=max(0.0, min(1.0, float(music_gain))),
        sfx_gain=max(0.0, min(1.0, float(sfx_gain))),
    )
    inputs = ["-i", str(voice)]
    if music is not None:
        inputs.extend(["-i", str(music)])
    if sfx is not None:
        inputs.extend(["-i", str(sfx)])
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
        f"apad=whole_dur={duration:.6f},atrim=0:{duration:.6f},"
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
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=900)
    if completed.returncode != 0 or not target.is_file():
        raise ExportError(
            "Audio finalization failed: "
            + (completed.stderr.strip()[-600:] or f"exit {completed.returncode}")
        )
    try:
        contract = validate_media(target, "audio_master")
    except MediaContractError as exc:
        raise ExportError(f"Audio finalization violated the media contract: {exc.message}") from exc
    if not contract.ok:
        raise ExportError(f"Audio finalization violated the media contract: {contract.to_dict()}")
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
