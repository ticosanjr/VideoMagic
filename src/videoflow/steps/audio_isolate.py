"""Optional voice isolation / source separation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.runtime import find_binary
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class IsolateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["auto", "rnnoise", "deepfilternet", "demucs", "none"] = "auto"
    model_path: str = ""
    device: str = "cpu"
    fallback_to_master: bool = True
    sample_rate: int = Field(default=48000, ge=8000, le=192000)


def _run(command: list[str], timeout: int = 1800) -> bool:
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


@register_step
class AudioIsolateStep(BaseStep):
    type = "audio.isolate"
    title = "Voice isolation"
    description = (
        "Separate speech from music and noise with an optional local backend. "
        "Falls back to the mastered source when no backend is available."
    )
    status = "partial"
    icon = "◌"
    color = "#a78bfa"
    requires = ("ingest",)
    produces = ("audio_isolated",)
    params_model = IsolateParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = IsolateParams.model_validate(params)
        source = Path(
            context.artifacts.get("audio_master")
            or context.pcm_path
            or context.source
        )
        target = context.output / "audio" / "isolated.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        backend = "none"
        if options.backend != "none":
            backend = self._try_backends(options, source, target, io)
        if backend == "none":
            if not options.fallback_to_master:
                raise IngestError(
                    "Voice isolation backend is unavailable and fallback is disabled."
                )
            self._fallback(source, target, options.sample_rate)
            backend = "master"
            context.warnings.append(
                "Voice isolation backend unavailable; using the mastered audio."
            )
        context.artifacts["audio_isolated"] = str(target)
        context.metadata["audio_isolated"] = {
            "backend": backend,
            "source": str(source),
            "path": str(target),
        }
        io.report(100, f"Voice isolation ready ({backend})")

    def _try_backends(
        self,
        options: IsolateParams,
        source: Path,
        target: Path,
        io: StepIO,
    ) -> str:
        if options.backend in {"auto", "rnnoise"} and options.model_path:
            ffmpeg = find_binary("ffmpeg")
            model = Path(options.model_path).expanduser()
            if ffmpeg and model.is_file():
                io.report(30, "Applying RNNoise")
                if _run(
                    [
                        ffmpeg,
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        str(source),
                        "-af",
                        f"arnndn=model={model}",
                        "-ar",
                        str(options.sample_rate),
                        str(target),
                    ]
                ) and target.is_file():
                    return "rnnoise"
        if options.backend in {"auto", "deepfilternet"}:
            binary = find_binary("deepFilter")
            if binary:
                io.report(30, "Applying DeepFilterNet")
                directory = target.parent / "deepfilter"
                directory.mkdir(parents=True, exist_ok=True)
                if _run([binary, str(source), "-o", str(directory)]):
                    produced = sorted(directory.glob("*.wav"))
                    if produced:
                        shutil.copy2(produced[0], target)
                        return "deepfilternet"
        if options.backend in {"auto", "demucs"}:
            binary = find_binary("demucs")
            if binary:
                io.report(30, "Separating vocals with Demucs")
                directory = target.parent / "demucs"
                directory.mkdir(parents=True, exist_ok=True)
                if _run(
                    [
                        binary,
                        "--two-stems=vocals",
                        "-d",
                        options.device,
                        "-o",
                        str(directory),
                        str(source),
                    ]
                ):
                    produced = sorted(directory.rglob("vocals.wav"))
                    if produced:
                        shutil.copy2(produced[0], target)
                        return "demucs"
        return "none"

    def _fallback(self, source: Path, target: Path, sample_rate: int) -> None:
        if source.suffix.casefold() == ".wav":
            shutil.copy2(source, target)
            return
        FFmpegAdapter().extract_pcm(source, target, sample_rate=sample_rate)

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("audio_isolated")
        return (Path(path),) if path else ()
