"""Ingest: probe media and extract the analysis PCM."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import MediaNotFoundError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import adapter_for
from videoflow.steps.registry import register_step


class IngestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extract_pcm: bool = True


@register_step
class IngestStep(BaseStep):
    type = "ingest"
    title = "Ingest media"
    description = "Probe the source, validate it with FFprobe, and extract analysis PCM."
    requires = ()
    produces = ("media", "pcm")
    params_model = IngestParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = IngestParams.model_validate(params)
        source = Path(context.source).expanduser()
        if not source.is_file():
            raise MediaNotFoundError(str(source))
        context.work.mkdir(parents=True, exist_ok=True)
        adapter = adapter_for(context, io)
        io.report(10, "Reading media metadata")
        media = adapter.probe(source)
        context.media = media
        if options.extract_pcm:
            io.report(55, "Extracting analysis audio")
            wav = adapter.extract_pcm(
                source,
                context.work / "source.wav",
                sample_rate=media.audio_sample_rate,
            )
            context.pcm_path = Path(wav)
            context.pcm_digest = adapter.pcm_digest(wav)
            io.emit("info", f"PCM SHA-256 {context.pcm_digest}")
        context.hashes["ingest"] = context.pcm_digest or media.model_dump_json()
        io.report(100, "Media ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return (context.pcm_path,) if context.pcm_path is not None else ()
