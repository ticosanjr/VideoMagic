"""PCM ingest and final loudness handlers for the Windows worker."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gpu_worker.gpu_handlers.common import _ffmpeg, _run
from gpu_worker.handlers import Handler, HandlerError

if TYPE_CHECKING:
    from gpu_worker.settings import Settings


def _ffprobe_path(ffmpeg: str) -> str:
    sibling = Path(ffmpeg).with_name("ffprobe")
    if sibling.is_file():
        return str(sibling)
    return shutil.which("ffprobe") or "ffprobe"


def _probe_json(ffprobe: str, source: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        raise HandlerError(
            f"ffprobe failed: {(completed.stderr or completed.stdout).strip()[-400:]}"
        )
    try:
        payload = json.loads(completed.stdout or "{}")
    except ValueError as exc:
        raise HandlerError("ffprobe returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise HandlerError("ffprobe returned a non-object payload")
    return payload


def make_ingest_pcm_handler(settings: Settings) -> Handler:
    """Extract 48 kHz stereo PCM and probe the source stream layout."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("ingest_pcm requires a media artifact")
        source = input_paths[0]
        output = work_dir / str(params.get("output_name") or "ingest.wav")
        ffmpeg = _ffmpeg(settings)
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s24le",
        ]
        duration = params.get("duration_sec")
        if duration:
            command.extend(["-t", f"{float(duration):.3f}"])
        command.append(str(output))
        _run(command)
        if not output.is_file() or output.stat().st_size == 0:
            raise HandlerError("ingest_pcm produced no audio")
        probe = _probe_json(_ffprobe_path(ffmpeg), source)
        video = next(
            (
                stream
                for stream in probe.get("streams") or []
                if isinstance(stream, dict) and stream.get("codec_type") == "video"
            ),
            {},
        )
        probe["cfr"] = bool(
            video
            and video.get("avg_frame_rate")
            and video.get("r_frame_rate")
            and video.get("avg_frame_rate") == video.get("r_frame_rate")
            and video.get("avg_frame_rate") != "0/0"
        )
        probe["pcm"] = {
            "sample_rate": 48000,
            "channels": 2,
            "codec": "pcm_s24le",
        }
        probe_path = work_dir / "probe.json"
        probe_path.write_text(
            json.dumps(probe, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return [output, probe_path]

    return handler


def make_audio_finalize_handler(settings: Settings) -> Handler:
    """Run two-pass EBU R128 loudness normalization at 48 kHz stereo."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("audio_finalize requires an audio artifact")
        source = input_paths[0]
        output = work_dir / str(params.get("output_name") or "audio_final.wav")
        ffmpeg = _ffmpeg(settings)
        target = float(params.get("target_lufs") or -15.5)
        true_peak = float(params.get("true_peak_db") or -1.0)
        lra = float(params.get("lra") or 11.0)
        measure_filter = (
            f"loudnorm=I={target}:TP={true_peak}:LRA={lra}:print_format=json"
        )
        measured = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "info",
                "-y",
                "-i",
                str(source),
                "-af",
                measure_filter,
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        text = measured.stderr or ""
        start, end = text.rfind("{"), text.rfind("}")
        if measured.returncode != 0 or start < 0 or end <= start:
            raise HandlerError(
                "loudnorm measurement failed: "
                + (text.strip()[-500:] or f"exit {measured.returncode}")
            )
        try:
            values = json.loads(text[start : end + 1])
            measured_i = float(values["input_i"])
            measured_tp = float(values["input_tp"])
            measured_lra = float(values["input_lra"])
            measured_thresh = float(values["input_thresh"])
            offset = float(values.get("target_offset") or 0.0)
        except (KeyError, TypeError, ValueError) as exc:
            raise HandlerError("loudnorm returned incomplete measurements") from exc
        final_filter = (
            f"loudnorm=I={target}:TP={true_peak}:LRA={lra}:"
            f"measured_I={measured_i}:measured_TP={measured_tp}:"
            f"measured_LRA={measured_lra}:measured_thresh={measured_thresh}:"
            f"offset={offset}:linear=true,aresample=48000"
        )
        _run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-af",
                final_filter,
                "-ac",
                "2",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s24le",
                str(output),
            ]
        )
        if not output.is_file() or output.stat().st_size == 0:
            raise HandlerError("audio_finalize produced no audio")
        return [output]

    return handler
