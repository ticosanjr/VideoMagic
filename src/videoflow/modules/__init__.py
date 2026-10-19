"""The eight rack modules, in execution order."""

from videoflow.domain.config import (
    ExportConfig,
    IngestConfig,
    JlCutsConfig,
    RetakesConfig,
    ShortsConfig,
    TranscribeConfig,
    VadConfig,
    ZoomsConfig,
)
from videoflow.modules.base import RackModule

__all__ = [
    "ExportModule",
    "IngestModule",
    "JlCutsModule",
    "RetakesModule",
    "ShortsModule",
    "TranscribeModule",
    "VadModule",
    "ZoomsModule",
    "modules",
]


class IngestModule(RackModule):
    id = "ingest"
    requires = ()

    def config_model(self) -> type[IngestConfig]:
        return IngestConfig


class VadModule(RackModule):
    id = "vad"
    requires = ("ingest",)

    def config_model(self) -> type[VadConfig]:
        return VadConfig


class TranscribeModule(RackModule):
    id = "transcribe"
    requires = ("ingest",)

    def config_model(self) -> type[TranscribeConfig]:
        return TranscribeConfig


class RetakesModule(RackModule):
    id = "retakes"
    requires = ("transcribe",)

    def config_model(self) -> type[RetakesConfig]:
        return RetakesConfig


class JlCutsModule(RackModule):
    id = "jl_cuts"
    requires = ("vad", "retakes")

    def config_model(self) -> type[JlCutsConfig]:
        return JlCutsConfig


class ZoomsModule(RackModule):
    id = "zooms"
    requires = ("jl_cuts",)

    def config_model(self) -> type[ZoomsConfig]:
        return ZoomsConfig


class ShortsModule(RackModule):
    id = "shorts"
    requires = ("transcribe", "retakes")

    def config_model(self) -> type[ShortsConfig]:
        return ShortsConfig


class ExportModule(RackModule):
    id = "export"
    requires = ("ingest", "vad", "transcribe", "retakes", "jl_cuts", "zooms", "shorts")

    def config_model(self) -> type[ExportConfig]:
        return ExportConfig


def modules() -> tuple[RackModule, ...]:
    return (
        IngestModule(),
        VadModule(),
        TranscribeModule(),
        RetakesModule(),
        JlCutsModule(),
        ZoomsModule(),
        ShortsModule(),
        ExportModule(),
    )
