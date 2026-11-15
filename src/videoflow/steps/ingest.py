"""Ingest: normalise, probe, proxy, and extract the analysis PCM."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.sync import detect_drift_ms
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import MediaNotFoundError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import adapter_for
from videoflow.steps.registry import register_step


class IngestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="", max_length=2000)
    extract_pcm: bool = True
    force_cfr: bool = True
    generate_proxy: bool = False
    proxy_height: int = Field(default=540, ge=144, le=2160)
    sync_reference_path: str = Field(default="", max_length=2000)


@register_step
class IngestStep(BaseStep):
    type = "ingest"
    title = "Ingest media"
    description = (
        "Probe the source, normalise VFR to CFR, optionally build a proxy, and "
        "extract the analysis PCM."
    )
    requires = ()
    produces = ("media", "pcm")
    params_model = IngestParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = IngestParams.model_validate(params)
        source = (
            resolve_allowed(Path(options.source), allowed_roots())
            if options.source.strip()
            else Path(context.source).expanduser()
        )
        context.source = source
        if not source.is_file():
            raise MediaNotFoundError(str(source))
        context.work.mkdir(parents=True, exist_ok=True)
        adapter = adapter_for(context, io)
        io.report(10, "Reading media metadata")
        media = adapter.probe(source)
        original = source
        normalized: Path | None = None
        if options.force_cfr and hasattr(adapter, "is_vfr") and adapter.is_vfr(source):
            io.report(25, "Normalising variable frame rate to CFR")
            normalized = adapter.normalize_cfr(
                source,
                context.work / "source_cfr.mp4",
                fps_num=media.fps_num,
                fps_den=media.fps_den,
            )
            context.source = normalized
            context.metadata["source_original"] = str(original)
            media = adapter.probe(normalized)
            io.emit(
                "info",
                f"VFR normalised to {media.fps_num}/{media.fps_den} "
                f"({media.duration_frames} frames)",
            )
        context.media = media
        proxy: Path | None = None
        if options.generate_proxy and hasattr(adapter, "build_proxy"):
            io.report(38, "Building preview proxy")
            proxy = adapter.build_proxy(
                context.source,
                context.work / "proxy.mp4",
                height=options.proxy_height,
            )
            context.metadata["proxy"] = str(proxy)
        if options.extract_pcm:
            io.report(55, "Extracting analysis audio")
            wav = adapter.extract_pcm(
                context.source,
                context.work / "source.wav",
                sample_rate=media.audio_sample_rate,
            )
            context.pcm_path = Path(wav)
            context.pcm_digest = adapter.pcm_digest(wav)
            io.emit("info", f"PCM SHA-256 {context.pcm_digest}")
        reference = options.sync_reference_path.strip()
        if reference and context.pcm_path is not None and hasattr(adapter, "extract_pcm"):
            reference_path = resolve_allowed(Path(reference), allowed_roots())
            if reference_path.is_file():
                io.report(75, "Measuring external microphone drift")
                reference_wav = adapter.extract_pcm(
                    reference_path,
                    context.work / "sync-reference.wav",
                    sample_rate=media.audio_sample_rate,
                )
                drift = detect_drift_ms(context.pcm_path, reference_wav)
                context.metadata["sync_reference"] = str(reference_path)
                if drift is not None:
                    context.metadata["sync_drift_ms"] = drift
        context.metadata["ingest_report"] = {
            "source": str(original),
            "normalized": str(normalized) if normalized is not None else "",
            "proxy": str(proxy) if proxy is not None else "",
            "fps_num": media.fps_num,
            "fps_den": media.fps_den,
            "duration_frames": media.duration_frames,
            "force_cfr": options.force_cfr,
        }
        context.hashes["ingest"] = context.pcm_digest or media.model_dump_json()
        io.report(100, "Media ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        outputs: list[Path] = []
        if context.pcm_path is not None:
            outputs.append(context.pcm_path)
        proxy = context.metadata.get("proxy")
        if isinstance(proxy, str) and proxy:
            outputs.append(Path(proxy))
        return tuple(outputs)
