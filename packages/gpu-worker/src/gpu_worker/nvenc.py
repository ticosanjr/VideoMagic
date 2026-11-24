"""NVENC probing and proven encoder arguments for the GPU worker.

The probe encodes a real clip because ``ffmpeg -encoders`` can list
``h264_nvenc`` while the driver rejects the preset/rate-control options used by
the renderer. The first profile that produces bytes is cached and reused.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from gpu_worker.handlers import HandlerError


@dataclass(frozen=True, slots=True)
class NvencProbe:
    """Result of a real NVENC encode probe."""

    available: bool
    reason: str
    advice: str
    args: tuple[str, ...] = ()
    log: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "reason": self.reason,
            "advice": self.advice,
            "args": list(self.args),
            "log": self.log[-500:],
        }


# Ordered from best quality/throughput to the most permissive command. A
# driver or FFmpeg build that rejects modern options still gets a real chance
# to prove that the GPU can encode.
_NVENC_CANDIDATES: tuple[tuple[str, ...], ...] = (
    (
        "-preset",
        "p4",
        "-rc",
        "vbr",
        "-cq",
        "19",
        "-b:v",
        "0",
        "-spatial-aq",
        "1",
    ),
    ("-preset", "p4", "-rc", "vbr", "-cq", "19", "-b:v", "0"),
    ("-preset", "fast"),
    ("-preset", "p4", "-tune", "hq", "-rc", "constqp", "-qp", "23"),
    ("-preset", "fast", "-tune", "hq", "-rc", "constqp", "-qp", "23"),
    ("-preset", "p1", "-rc", "constqp", "-qp", "23"),
    ("-preset", "p1"),
    (),
)
_FATAL_NVENC_MARKERS = (
    "cannot load libnvidia-encode",
    "libnvidia-encode.so",
    "openencodesessionex failed",
    "no capable devices",
    "no nvidia",
    "unsupported device",
    "unknown encoder",
    "encoder not found",
)

_NVENC_CACHE: dict[str, bool] = {}
_NVENC_REASONS: dict[str, str] = {}
_NVENC_PROBES: dict[str, NvencProbe] = {}


def _classify_nvenc_failure(log: str) -> tuple[str, str]:
    text = (log or "").strip()
    lowered = text.casefold()
    if "cannot load libnvidia-encode" in lowered or "libnvidia-encode.so" in lowered:
        return (
            "O FFmpeg não conseguiu carregar a biblioteca NVENC do driver.",
            "Atualize o driver NVIDIA e confirme que o bin\ffmpeg.exe do worker "
            "foi compilado com NVENC (build gpl).",
        )
    if "openencodesessionex failed" in lowered:
        return (
            "A sessão NVENC não pôde ser aberta (limite de sessões ou driver).",
            "Feche OBS/navegadores que usam NVENC, reinicie o worker e tente de novo.",
        )
    if "no capable devices" in lowered or "unsupported device" in lowered:
        return (
            "A GPU não oferece um encoder H.264 NVENC utilizável.",
            "Use libx264 neste worker; H.264 por hardware não está disponível na GPU.",
        )
    if "unknown encoder" in lowered or "encoder not found" in lowered:
        return (
            "Este FFmpeg não inclui o encoder h264_nvenc.",
            "Substitua bin\ffmpeg.exe por um build gpl com NVENC e reinicie o worker.",
        )
    if "invalid argument" in lowered:
        return (
            "O driver recusou as opções do encoder NVIDIA.",
            "O worker já testou as combinações compatíveis; atualize o FFmpeg e o "
            "driver NVIDIA. Enquanto isso, use libx264.",
        )
    if "permission" in lowered or "access is denied" in lowered:
        return (
            "O processo do worker não tem permissão para usar a GPU.",
            "Rode o worker com o mesmo usuário que executa nvidia-smi e verifique "
            "as políticas de GPU do Windows.",
        )
    return (
        "O encode de teste com h264_nvenc falhou.",
        "Confira o log do worker e execute nvidia-smi; se persistir, use libx264.",
    )


def probe_nvenc(ffmpeg: str = "ffmpeg", *, force: bool = False) -> NvencProbe:
    """Prove that NVENC works by encoding a real 640x360 H.264 file.

    Encoder presence is not enough: older drivers reject presets/rate-control
    options that newer FFmpeg builds pass by default. This probe tries a short
    list of compatible profiles and caches the first one that produces bytes.
    """

    key = str(ffmpeg)
    if not force and key in _NVENC_PROBES:
        return _NVENC_PROBES[key]
    try:
        listed = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        probe = NvencProbe(
            False,
            f"FFmpeg não executou: {exc}",
            "Verifique o caminho do FFmpeg do worker.",
            log=str(exc),
        )
        _NVENC_PROBES[key] = probe
        _NVENC_CACHE[key] = False
        _NVENC_REASONS[key] = probe.reason
        return probe
    if listed.returncode != 0 or "h264_nvenc" not in (listed.stdout or ""):
        log = (listed.stderr or listed.stdout or "").strip()[-500:]
        probe = NvencProbe(
            False,
            "Este FFmpeg não inclui o encoder h264_nvenc.",
            "Substitua bin\ffmpeg.exe por um build gpl com NVENC e reinicie o worker.",
            log=log,
        )
        _NVENC_PROBES[key] = probe
        _NVENC_CACHE[key] = False
        _NVENC_REASONS[key] = probe.reason
        return probe

    last_log = ""
    with tempfile.TemporaryDirectory(prefix="vf-nvenc-probe-") as raw:
        output = Path(raw) / "probe.mp4"
        for candidate in _NVENC_CANDIDATES:
            output.unlink(missing_ok=True)
            command = [
                ffmpeg,
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
            if completed.returncode == 0 and output.is_file() and output.stat().st_size > 1024:
                probe = NvencProbe(True, "", "", args=tuple(candidate), log=last_log)
                _NVENC_PROBES[key] = probe
                _NVENC_CACHE[key] = True
                _NVENC_REASONS[key] = ""
                return probe
            if any(marker in last_log.casefold() for marker in _FATAL_NVENC_MARKERS):
                break

    reason, advice = _classify_nvenc_failure(last_log)
    probe = NvencProbe(False, reason, advice, log=last_log)
    _NVENC_PROBES[key] = probe
    _NVENC_CACHE[key] = False
    _NVENC_REASONS[key] = reason
    return probe


def nvenc_available(ffmpeg: str = "ffmpeg") -> bool:
    """Return whether FFmpeg can really encode H.264 with NVENC."""

    return probe_nvenc(ffmpeg).available


def nvenc_error(ffmpeg: str = "ffmpeg") -> str:
    return probe_nvenc(ffmpeg).reason


def nvenc_advice(ffmpeg: str = "ffmpeg") -> str:
    return probe_nvenc(ffmpeg).advice


def nvenc_args(ffmpeg: str = "ffmpeg") -> list[str]:
    """Return the encoder flags proven by :func:`probe_nvenc`."""

    probe = probe_nvenc(ffmpeg)
    if not probe.available:
        raise HandlerError(probe.reason or "h264_nvenc is unavailable")
    return list(probe.args)
