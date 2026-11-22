"""Music/Foley generation and dialogue/music mastering."""

from __future__ import annotations

import hashlib
import tempfile
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..toolkit import commands, storage
from ..toolkit.assets import (
    _ensure_input,
    _ffmpeg,
    _materialize_remote,
    _payload,
    _require_output,
    _slug,
)
from ..toolkit.errors import InvalidArgumentError
from . import studio_common
from .studio_common import _output_name


def generate_music_or_sfx(
    project_id: str,
    prompt: str,
    duration_sec: float,
    type: str = "music",
) -> dict[str, Any]:
    """Generate a deterministic local bed or use a remote `music`/`sfx` capability."""

    tool = "generate_music_or_sfx"
    kind = (type or "").strip().lower()
    if kind not in {"music", "sfx"}:
        raise InvalidArgumentError(
            "type must be 'music' or 'sfx'",
            details={"argument": "type", "value": type},
        )
    if not isinstance(prompt, str) or not prompt.strip():
        raise InvalidArgumentError("prompt must not be empty", details={"argument": "prompt"})
    try:
        duration = float(duration_sec)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "duration_sec must be a number",
            details={"argument": "duration_sec", "value": duration_sec},
        ) from exc
    if not 0.25 <= duration <= 600.0:
        raise InvalidArgumentError(
            "duration_sec must be between 0.25 and 600",
            details={"argument": "duration_sec", "value": duration_sec},
        )

    key = storage.cache_key(tool, prompt, duration, kind)
    relative = f"assets/audio/{kind}_{_slug(prompt)}_{key[:8]}.wav"
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    if studio_common.ROUTER.health(kind):
        result = studio_common.ROUTER.submit(
            kind,
            {"prompt": prompt, "duration_sec": duration, "type": kind},
        )
        record = _materialize_remote(
            project_id=project_id,
            relative_path=relative,
            result=result,
            capability=kind,
            cache_key=key,
            kind=kind,
        )
        return _payload(tool, project_id, record, mode="remote")

    ffmpeg = _ffmpeg()
    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vf-bed-") as raw:
        workdir = Path(raw)
        if kind == "music":
            bed = workdir / "bed.wav"
            _write_music_bed(bed, duration, prompt)
            commands.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(bed),
                    "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar",
                    "48000",
                    "-c:a",
                    "pcm_s16le",
                    str(target),
                ]
            )
            source_name = "procedural:numpy+ffmpeg"
        else:
            fade_out = max(0.05, duration - 0.35)
            filter_chain = (
                "highpass=f=200,lowpass=f=6000,"
                f"afade=t=in:st=0:d=0.15,afade=t=out:st={fade_out:.3f}:d=0.35,"
                "volume=0.8"
            )
            commands.run(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"anoisesrc=color=pink:duration={duration:.3f}:amplitude=0.35",
                    "-af",
                    filter_chain,
                    "-ar",
                    "48000",
                    "-c:a",
                    "pcm_s16le",
                    str(target),
                ]
            )
            source_name = "procedural:ffmpeg"

    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind=kind,
        license="generated",
        source=source_name,
        cache_key=key,
        ai_generated=True,
        metadata={"prompt": prompt, "duration_sec": duration, "type": kind},
    )
    return _payload(tool, project_id, record, mode="local")


def mix_and_master_track(
    project_id: str,
    voice_path: str,
    music_path: str | None = None,
    sfx_events: Sequence[dict[str, Any]] | None = None,
    target_lufs: float = -15.5,
    output_name: str = "master.wav",
) -> dict[str, Any]:
    """Duck music under the voice, place SFX, and master with loudnorm."""

    tool = "mix_and_master_track"
    voice = _ensure_input(voice_path, "voice_path")
    music = _ensure_input(music_path, "music_path") if music_path else None
    events = _normalize_sfx_events(sfx_events or [])
    try:
        lufs = float(target_lufs)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "target_lufs must be a number",
            details={"argument": "target_lufs", "value": target_lufs},
        ) from exc
    if not -60.0 <= lufs <= 0.0:
        raise InvalidArgumentError(
            "target_lufs must be between -60 and 0",
            details={"argument": "target_lufs", "value": target_lufs},
        )

    name = _output_name(output_name, "master.wav")
    if not name.lower().endswith(".wav"):
        name = f"{Path(name).stem}.wav"
    relative = f"assets/audio/{name}"

    key = storage.cache_key(
        tool,
        storage.file_fingerprint(voice),
        storage.file_fingerprint(music) if music else "",
        [
            (
                storage.file_fingerprint(event["path"]),
                event["start"],
                event["gain_db"],
            )
            for event in events
        ],
        lufs,
    )
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    ffmpeg = _ffmpeg()
    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    argv = [ffmpeg, "-y", "-i", str(voice)]
    if music:
        argv.extend(["-i", str(music)])
    for event in events:
        argv.extend(["-i", event["path"]])

    graph = build_mix_graph(
        has_music=music is not None,
        sfx_count=len(events),
        target_lufs=lufs,
        sfx_starts=[event["start"] for event in events],
        sfx_gains=[event["gain_db"] for event in events],
    )
    argv.extend(
        [
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
    )
    commands.run(argv)
    _require_output(target)

    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="voice",
        license="generated",
        source="ffmpeg:mix",
        cache_key=key,
        metadata={
            "voice": str(voice),
            "music": str(music) if music else "",
            "sfx_events": len(events),
            "target_lufs": lufs,
            "ducking": music is not None,
        },
    )
    return _payload(
        tool,
        project_id,
        record,
        mode="local",
        ducking=music is not None,
        sfx_count=len(events),
    )


def build_mix_graph(
    *,
    has_music: bool,
    sfx_count: int,
    target_lufs: float = -15.5,
    sfx_starts: Sequence[float] | None = None,
    sfx_gains: Sequence[float] | None = None,
) -> str:
    """Build the filter_complex graph for sidechain ducking and mastering."""

    starts = list(sfx_starts or [0.0] * sfx_count)
    gains = list(sfx_gains or [0.0] * sfx_count)
    if len(starts) != sfx_count or len(gains) != sfx_count:
        raise InvalidArgumentError("sfx timing lists must match sfx_count")

    lines: list[str] = []
    mix_inputs: list[str] = []
    if has_music:
        lines.append("[0:a]asplit=2[voice][key]")
        lines.append("[1:a]volume=0.9[music]")
        lines.append(
            "[music][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[ducked]"
        )
        mix_inputs.extend(["[voice]", "[ducked]"])
    else:
        mix_inputs.append("[0:a]")

    first_sfx_index = 2 if has_music else 1
    for index in range(sfx_count):
        delay = max(0, int(round(float(starts[index]) * 1000)))
        gain = float(gains[index])
        gain_filter = f",volume={gain:g}dB" if gain else ""
        lines.append(
            f"[{first_sfx_index + index}:a]adelay={delay}|{delay}{gain_filter}[sfx{index}]"
        )
        mix_inputs.append(f"[sfx{index}]")

    loudnorm = f"loudnorm=I={float(target_lufs):.1f}:TP=-1.0:LRA=11"
    if len(mix_inputs) == 1:
        lines.append(f"{mix_inputs[0]}{loudnorm}[out]")
    else:
        lines.append(
            "".join(mix_inputs)
            + f"amix=inputs={len(mix_inputs)}:normalize=0:duration=longest[mixed]"
        )
        lines.append(f"[mixed]{loudnorm}[out]")
    return ";\n".join(lines)


def _write_music_bed(path: Path, duration: float, prompt: str, sample_rate: int = 48000) -> None:
    """Render a deterministic stereo pad/bass bed with numpy."""

    seed = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    frames = max(1, int(round(duration * sample_rate)))
    timeline = np.arange(frames, dtype=np.float64) / sample_rate

    scale = (0.0, 2.0, 3.0, 5.0, 7.0, 8.0, 10.0)
    root = 110.0 * (2.0 ** ((seed % 5) / 12.0))
    signal = np.zeros(frames, dtype=np.float64)

    chord_length = max(0.5, duration / 4.0)
    for start in np.arange(0.0, duration, chord_length):
        begin = int(start * sample_rate)
        end = min(frames, int((start + chord_length) * sample_rate))
        if end <= begin:
            continue
        local = timeline[begin:end] - start
        envelope = np.sin(np.pi * local / chord_length) ** 2
        for degree in (0, 3, 4, 5):
            frequency = root * 2.0 ** (scale[degree] / 12.0)
            signal[begin:end] += envelope * np.sin(2.0 * np.pi * frequency * local)
        signal[begin:end] += 0.5 * envelope * np.sin(np.pi * root * local)

    for start in np.arange(0.0, duration, 0.5):
        begin = int(start * sample_rate)
        end = min(frames, int((start + 0.15) * sample_rate))
        if end <= begin:
            continue
        local = timeline[begin:end] - start
        signal[begin:end] += 0.35 * np.exp(-local * 18.0) * np.sin(2.0 * np.pi * 60.0 * local)

    signal += 0.01 * rng.standard_normal(frames)
    peak = float(np.max(np.abs(signal))) or 1.0
    signal = signal / peak * 0.30
    stereo = np.stack([signal, np.roll(signal, 240)], axis=1)
    pcm = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def _normalize_sfx_events(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise InvalidArgumentError(
                f"sfx_events[{index}] must be an object",
                details={"argument": "sfx_events", "index": index},
            )
        raw_path = event.get("path") or event.get("file")
        resolved = _ensure_input(raw_path, f"sfx_events[{index}].path")
        try:
            start = float(event.get("start", 0.0))
            gain = float(event.get("gain_db", 0.0))
        except (TypeError, ValueError) as exc:
            raise InvalidArgumentError(
                f"sfx_events[{index}] start and gain_db must be numbers",
                details={"argument": "sfx_events", "index": index},
            ) from exc
        if start < 0:
            raise InvalidArgumentError(
                f"sfx_events[{index}].start must be >= 0",
                details={"argument": "sfx_events", "index": index},
            )
        normalized.append({"path": str(resolved), "start": start, "gain_db": gain})
    return normalized
