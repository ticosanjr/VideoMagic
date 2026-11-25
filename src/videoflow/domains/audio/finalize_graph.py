"""FFmpeg filter graphs for the final audio bed."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _build_graph(
    *,
    duration: float,
    mono_repair: str,
    music: bool,
    sfx: bool,
    music_gain: float,
    sfx_gain: float,
    ducking: bool = True,
    finalize_mix: bool = True,
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
        chains.append(
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"aresample=48000,aloop=loop=-1:size=2880000,atrim=0:{duration:.6f},"
            f"volume={music_gain:.3f},"
            f"afade=t=out:st={max(0.0, duration - 2.5):.6f}:"
            f"d={min(2.5, duration):.6f}[music]"
        )
        if ducking:
            chains.append("[voice]asplit=2[voice_sc][voice_mix]")
            chains.append(
                "[music][voice_sc]sidechaincompress=threshold=0.02:ratio=8:"
                "attack=20:release=300[ducked]"
            )
            chains.append(
                "[voice_mix][ducked]amix=inputs=2:weights=1 1:normalize=0[mix0]"
            )
        else:
            chains.append("[voice][music]amix=inputs=2:weights=1 1:normalize=0[mix0]")
    else:
        chains.append("[voice]anull[mix0]")
    if sfx:
        chains.append(
            f"[2:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"aresample=48000,atrim=0:{duration:.6f},apad=whole_dur={duration:.6f},"
            f"volume={sfx_gain:.3f}[sfx]"
        )
        chains.append("[mix0][sfx]amix=inputs=2:weights=1 1:normalize=0[mix]")
    elif finalize_mix:
        chains.append("[mix0]anull[mix]")
    return ";".join(chains)


def _sfx_chains(
    events: list[dict[str, Any]],
    *,
    first_input: int,
    duration: float,
    sfx_gain: float,
) -> tuple[list[str], list[str], list[str]]:
    """Build per-event delay/trim chains and return extra inputs/labels."""

    chains: list[str] = []
    inputs: list[str] = []
    labels: list[str] = []
    for index, event in enumerate(events):
        path = Path(str(event.get("path") or "")).expanduser()
        if not path.is_file():
            continue
        start_sec = max(0.0, float(event.get("start_sec") or 0.0))
        gain_db = float(event.get("gain_db") or 0.0)
        gain = max(0.0, min(4.0, sfx_gain * (10 ** (gain_db / 20.0))))
        delay_ms = int(round(start_sec * 1000))
        label = f"sfx{index}"
        inputs.extend(["-i", str(path)])
        chains.append(
            f"[{first_input + index}:a]"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"aresample=48000,atrim=0:{duration:.6f},"
            f"adelay={delay_ms}|{delay_ms},volume={gain:.4f}[{label}]"
        )
        labels.append(f"[{label}]")
    return chains, inputs, labels


__all__ = ["_build_graph", "_sfx_chains"]
