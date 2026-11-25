"""One timeline to NLE documents or a direct MP4. The API and MCP call this service."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState
from videoflow.exporters.edl import export_edl
from videoflow.exporters.extras import EMPTY, NleExtras
from videoflow.exporters.fcpxml import Dialect, export_fcpxml
from videoflow.exporters.kdenlive import export_kdenlive
from videoflow.exporters.mp4 import export_mp4
from videoflow.exporters.xmeml import export_xmeml

Target = Literal["resolve", "premiere", "kdenlive", "edl", "mp4"]
DEFAULT_TARGETS: tuple[Target, ...] = ("resolve", "premiere", "kdenlive")
ALL_TARGETS: tuple[Target, ...] = ("mp4", "resolve", "premiere", "kdenlive")
TARGET_ALIASES: dict[str, str] = {
    "mp4_youtube": "mp4",
    "youtube": "mp4",
    "social": "mp4",
    "all": "all",
}

FILENAMES: dict[str, str] = {
    "resolve": "timeline.fcpxml",
    "premiere": "timeline.xml",
    "kdenlive": "timeline.kdenlive",
    "edl": "timeline.edl",
    "mp4": "timeline.mp4",
}

SUFFIXES: dict[str, str] = {
    "resolve": ".fcpxml",
    "premiere": ".xml",
    "kdenlive": ".kdenlive",
    "edl": ".edl",
    "mp4": ".mp4",
}


def resolve_targets(targets: Sequence[str] | str | None) -> list[Target]:
    """Expand aliases (``all``, ``mp4_youtube``) into export targets."""

    if targets is None:
        return list(DEFAULT_TARGETS)
    if isinstance(targets, str):
        targets = [targets]
    resolved: list[Target] = []
    for raw in targets:
        name = str(raw).strip().lower()
        if not name:
            continue
        if name == "all":
            for item in ALL_TARGETS:
                if item not in resolved:
                    resolved.append(item)
            continue
        canonical = TARGET_ALIASES.get(name, name)
        if canonical == "all":
            for item in ALL_TARGETS:
                if item not in resolved:
                    resolved.append(item)
            continue
        if canonical not in resolved:
            resolved.append(canonical)  # type: ignore[arg-type]
    return resolved


def export_timeline(
    state: ProjectState,
    output_dir: Path,
    *,
    targets: Sequence[str] = DEFAULT_TARGETS,
    dialect: Dialect = "1.10",
    basename: str | None = None,
    extras: NleExtras = EMPTY,
    progress: Callable[[str, int], None] | None = None,
    should_cancel: Callable[[], object] | None = None,
    adapter: Any | None = None,
    cache_dir: Path | None = None,
    filenames: Mapping[str, str] | None = None,
    mp4_profile: str = "",
    mp4_audio_bitrate: str = "192k",
    mp4_loudness_lufs: float | None = None,
    mp4_true_peak_db: float = -1.0,
    mp4_cfr: bool = False,
) -> dict[str, Path]:
    """Write every requested artifact from the same validated timeline."""

    directory = Path(output_dir).expanduser()
    artifacts: dict[str, Path] = {}
    requested = resolve_targets(targets)
    ordered = [target for target in requested if target != "mp4"] + [
        target for target in requested if target == "mp4"
    ]
    for target in ordered:
        if should_cancel is not None and should_cancel():
            from videoflow.domain.errors import JobCancelledError

            raise JobCancelledError("Cancelled")
        if progress is not None:
            progress(target, 0)
        if target not in FILENAMES:
            raise ExportError(f"Unknown export target: {target}")
        if filenames is not None and target in filenames:
            destination = directory / filenames[target]
        else:
            destination = (
                directory / f"{basename}{SUFFIXES[target]}"
                if basename is not None and target in SUFFIXES
                else directory / FILENAMES[target]
            )
        if target == "resolve":
            artifacts[target] = export_fcpxml(state, destination, dialect=dialect, extras=extras)
        elif target == "premiere":
            artifacts[target] = export_xmeml(state, destination, extras=extras)
        elif target == "kdenlive":
            artifacts[target] = export_kdenlive(state, destination, extras=extras)
        elif target == "edl":
            artifacts[target] = export_edl(state, destination)
        else:
            project_root = (
                directory.parent if directory.name == "exports" else directory
            )
            final_mix = project_root / "audio" / "final_mix.wav"
            artifacts[target] = export_mp4(
                state,
                destination,
                adapter=adapter,
                profile=mp4_profile,
                audio_bitrate=mp4_audio_bitrate,
                loudness_lufs=mp4_loudness_lufs,
                true_peak_db=mp4_true_peak_db,
                cfr=mp4_cfr,
                audio_master=final_mix if final_mix.is_file() else None,
                progress=((lambda value, name=target: progress(name, value)) if progress else None),
                cache_dir=cache_dir,
            )
        if progress is not None:
            progress(target, 100)
    return artifacts
