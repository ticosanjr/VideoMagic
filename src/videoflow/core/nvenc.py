"""Real NVENC capability probing and safe encoder arguments.

Checking ``ffmpeg -encoders`` is not enough: a driver can expose
``h264_nvenc`` and still reject the preset/rate-control options used by the
renderer. Every caller must therefore prove that a short encode produces
bytes, and reuse exactly the argument set that passed.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ARGS: tuple[str, ...] = (
    "-preset",
    "p4",
    "-rc",
    "vbr",
    "-cq",
    "19",
    "-b:v",
    "0",
)

# Ordered from best quality to the most permissive command. FFmpeg 7/8/9 use
# the hyphenated ``-spatial-aq``; older drivers get a candidate without AQ.
CANDIDATES: tuple[tuple[str, ...], ...] = (
    (*DEFAULT_ARGS, "-spatial-aq", "1"),
    DEFAULT_ARGS,
    ("-preset", "fast"),
    ("-preset", "p4", "-tune", "hq", "-rc", "constqp", "-qp", "23"),
    ("-preset", "fast", "-tune", "hq", "-rc", "constqp", "-qp", "23"),
    ("-preset", "p1", "-rc", "constqp", "-qp", "23"),
    ("-preset", "p1"),
    (),
)

_FATAL = (
    "cannot load libnvidia-encode",
    "libnvidia-encode.so",
    "openencodesessionex failed",
    "no capable devices",
    "no nvidia",
    "unsupported device",
    "unknown encoder",
    "encoder not found",
)

_CACHE: dict[str, NvencProbe] = {}


@dataclass(frozen=True, slots=True)
class NvencProbe:
    available: bool
    reason: str
    advice: str
    args: tuple[str, ...] = ()
    log: str = ""


def _classify(log: str) -> tuple[str, str]:
    lowered = (log or "").casefold()
    if "cannot load libnvidia-encode" in lowered or "libnvidia-encode.so" in lowered:
        return (
            "O FFmpeg não conseguiu carregar a biblioteca NVENC do driver.",
            "Atualize o driver NVIDIA e use um FFmpeg compilado com NVENC.",
        )
    if "openencodesessionex failed" in lowered:
        return (
            "A sessão NVENC não pôde ser aberta.",
            "Feche outros apps que usam NVENC e reinicie o worker.",
        )
    if "no capable devices" in lowered or "unsupported device" in lowered:
        return (
            "A GPU não oferece H.264 NVENC utilizável.",
            "Use libx264 neste host.",
        )
    if "unknown encoder" in lowered or "encoder not found" in lowered:
        return (
            "Este FFmpeg não inclui h264_nvenc.",
            "Substitua o FFmpeg por um build gpl com NVENC.",
        )
    if "invalid argument" in lowered:
        return (
            "O driver recusou as opções do encoder NVIDIA.",
            "Atualize FFmpeg e driver; o host já testou as combinações compatíveis.",
        )
    return (
        "O encode de teste com h264_nvenc falhou.",
        "Confira o driver NVIDIA; se persistir, use libx264.",
    )


def probe_nvenc(ffmpeg: str | None = None, *, force: bool = False) -> NvencProbe:
    """Encode a real 640x360 clip and return the first compatible profile."""

    binary = ffmpeg or shutil.which("ffmpeg") or "ffmpeg"
    key = str(binary)
    if not force and key in _CACHE:
        return _CACHE[key]
    try:
        listed = subprocess.run(
            [binary, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        probe = NvencProbe(
            False,
            f"FFmpeg não executou: {exc}",
            "Verifique o FFmpeg.",
            log=str(exc),
        )
        _CACHE[key] = probe
        return probe
    if listed.returncode != 0 or "h264_nvenc" not in (listed.stdout or ""):
        probe = NvencProbe(
            False,
            "Este FFmpeg não inclui h264_nvenc.",
            "Instale um FFmpeg gpl com NVENC.",
            log=(listed.stderr or listed.stdout or "").strip()[-500:],
        )
        _CACHE[key] = probe
        return probe

    last_log = ""
    with tempfile.TemporaryDirectory(prefix="vf-nvenc-") as raw:
        output = Path(raw) / "probe.mp4"
        for candidate in CANDIDATES:
            output.unlink(missing_ok=True)
            command = [
                binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=640x360:r=30:d=1",
                "-vf",
                "format=yuv420p",
                "-c:v",
                "h264_nvenc",
                *candidate,
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-t",
                "1",
                str(output),
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
            except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
                last_log = str(exc)
                break
            last_log = (completed.stderr or completed.stdout or "").strip()[-500:]
            if (
                completed.returncode == 0
                and output.is_file()
                and output.stat().st_size > 1024
            ):
                probe = NvencProbe(True, "", "", args=tuple(candidate), log=last_log)
                _CACHE[key] = probe
                return probe
            if any(marker in last_log.casefold() for marker in _FATAL):
                break

    reason, advice = _classify(last_log)
    probe = NvencProbe(False, reason, advice, log=last_log)
    _CACHE[key] = probe
    return probe


def nvenc_available(ffmpeg: str | None = None) -> bool:
    return probe_nvenc(ffmpeg).available


def local_gpu_available(ffmpeg: str | None = None) -> bool:
    """Whether this host has an NVIDIA CUDA device and a working NVENC."""

    from vf_shared.compute.local_gpu import cuda_device_count

    if cuda_device_count() <= 0:
        return False
    return probe_nvenc(ffmpeg).available


def nvenc_args(ffmpeg: str | None = None) -> list[str]:
    """Return the proven encoder flags, or the default profile when forced."""

    return list(probe_nvenc(ffmpeg).args or DEFAULT_ARGS)


__all__ = [
    "CANDIDATES",
    "DEFAULT_ARGS",
    "NvencProbe",
    "local_gpu_available",
    "nvenc_args",
    "nvenc_available",
    "probe_nvenc",
]
