"""Typed ports exposed by recipe steps, plus wiring validation helpers."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from videoflow.domain.errors import RecipeError, VideoFlowError
from videoflow.steps.base import PortSpec

_ARTIFACTS = "artifacts"

PORTS: dict[str, tuple[tuple[PortSpec, ...], tuple[PortSpec, ...]]] = {
    "ingest": (
        (),
        (
            PortSpec("media", "Media info", "media", "media"),
            PortSpec("pcm", "PCM audio", "pcm", "pcm_path"),
            PortSpec("digest", "PCM digest", "string", "pcm_digest"),
        ),
    ),
    "audio.vad": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (
            PortSpec("speech", "Speech spans", "sample_spans", "speech_intervals"),
            PortSpec("engine", "VAD engine", "string", "vad_engine"),
        ),
    ),
    "transcribe": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (
            PortSpec("transcript", "Transcript", "transcript", "transcript"),
            PortSpec("source", "Transcript source", "string", "transcript_source"),
        ),
    ),
    "retakes.cull": (
        (
            PortSpec("speech", "Speech spans", "sample_spans", "speech_intervals", True),
            PortSpec("transcript", "Transcript", "transcript", "transcript", True),
        ),
        (
            PortSpec("speech", "Kept speech", "sample_spans", "speech_intervals"),
            PortSpec("discarded", "Discarded sentence ids", "integer_list", "discard_sentence_ids"),
        ),
    ),
    "edit.timeline": (
        (
            PortSpec("speech", "Speech spans", "sample_spans", "speech_intervals", True),
            PortSpec("transcript", "Transcript", "transcript", "transcript", False),
        ),
        (
            PortSpec("timeline", "Timeline state", "timeline", "state"),
            PortSpec("warnings", "Warnings", "string_list", "warnings"),
        ),
    ),
    "export.nle": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("artifacts", "NLE artifacts", "artifact_map", "artifacts"),),
    ),
    "shorts.select": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (PortSpec("shorts", "Selected Shorts", "short_list", "shorts"),),
    ),
    "shorts.score": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("shorts", "Scored Shorts", "short_list", "shorts"),),
    ),
    "shorts.reframe": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("shorts", "Reframed Shorts", "short_list", "shorts"),),
    ),
    "shorts.captions": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("captions", "Short captions", "dict", "short_captions"),),
    ),
    "shorts.render": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts"),),
    ),
    "broll.plan": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("plan", "B-roll plan", "dict", "metadata:broll_plan"),),
    ),
    "assets.shots": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("shots", "Shot detection", "dict", "metadata:shots"),),
    ),
    "assets.match": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("matches", "B-roll matches", "dict", "metadata:broll_matches"),),
    ),
    "music.beat": ((), (PortSpec("beat", "Beat grid", "dict", "metadata:beat"),)),
    "sfx.plan": ((), (PortSpec("plan", "SFX plan", "dict", "metadata:sfx_plan"),)),
    "assets.index": ((), (PortSpec("assets", "Asset index", "dict", "artifacts"),)),
    "audio.master": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("artifacts", "Audio master", "artifact_map", "artifacts"),),
    ),
    "audio.qa": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("artifacts", "Audio QA", "artifact_map", "artifacts"),),
    ),
    "color.grade": ((), (PortSpec("artifacts", "Colour filters", "artifact_map", "artifacts"),)),
    "titles.plan": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("artifacts", "Titles", "artifact_map", "artifacts"),),
    ),
    "thumbnail.generate": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("artifacts", "Thumbnails", "artifact_map", "artifacts"),),
    ),
    "storyboard.plan": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("artifacts", "Storyboard", "artifact_map", "artifacts"),),
    ),
    "transcript.translate": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (PortSpec("transcript", "Translated transcript", "transcript", "transcript"),),
    ),
    "audio.diarize": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (PortSpec("speakers", "Speaker turns", "dict", "metadata:speaker_turns"),),
    ),
    "localization.dub": (
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Dubbed Shorts", "artifact_map", "artifacts"),),
    ),
    "human.gate": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", False),),
        (),
    ),
    "metadata.pack": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("artifacts", "Metadata", "artifact_map", "artifacts"),),
    ),
    "thumbnail.pack": (
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Thumbnails", "artifact_map", "artifacts"),),
    ),
    "publish.queue": (
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Publish queue", "artifact_map", "artifacts"),),
    ),
    "chapters.plan": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (PortSpec("artifacts", "Chapters", "artifact_map", "artifacts"),),
    ),
    "nle.qa": (
        (PortSpec("artifacts", "NLE artifacts", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "NLE QA", "artifact_map", "artifacts"),),
    ),
    "delivery.package": (
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Delivery package", "artifact_map", "artifacts"),),
    ),
    "shorts.ab": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("artifacts", "A/B variants", "artifact_map", "artifacts"),),
    ),
    "analytics.import": ((), (PortSpec("artifacts", "Analytics", "artifact_map", "artifacts"),)),
    "review.queue": ((), (PortSpec("artifacts", "Review queue", "artifact_map", "artifacts"),)),
    "analytics.review": ((), (PortSpec("artifacts", "Review", "artifact_map", "artifacts"),)),
    "content.idea": ((), (PortSpec("artifacts", "Idea", "artifact_map", "artifacts"),)),
    "content.research": ((), (PortSpec("artifacts", "Research", "artifact_map", "artifacts"),)),
    "content.script": ((), (PortSpec("artifacts", "Script", "artifact_map", "artifacts"),)),
    "publish.webhook": (
        (PortSpec("artifacts", "Artifacts", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Published", "artifact_map", "artifacts"),),
    ),
    "flow.conditional": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "flow.loop": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "flow.subflow": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "flow.map": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "flow.reduce": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "experiment.evaluate": ((), (PortSpec("artifacts", "Winner", "artifact_map", "artifacts"),)),
}


def ports_for_type(
    step_type: str,
) -> tuple[tuple[PortSpec, ...], tuple[PortSpec, ...]]:
    return PORTS.get(step_type, ((), ()))


def type_compatible(source: str, target: str) -> bool:
    return source == target or source == "any" or target == "any"


def validate_recipe_ports(recipe: Any) -> None:
    """Validate explicit port wiring while leaving legacy ``needs`` untouched."""

    from videoflow.steps import get_step

    step_by_id = {step.id: step for step in recipe.steps}
    order = [step.id for step in recipe.topological_order()]
    position = {step_id: index for index, step_id in enumerate(order)}
    for step in recipe.steps:
        if not step.inputs:
            continue
        input_ports = {port.id: port for port in get_step(step.type).input_ports}
        for input_id, reference in step.inputs.items():
            port = input_ports.get(input_id)
            if port is None:
                raise RecipeError(f"{step.id}: unknown input port {input_id}")
            source_id, separator, source_port = str(reference).partition(".")
            if not separator or not source_id or not source_port:
                raise RecipeError(
                    f"{step.id}.{input_id}: expected node.port, got {reference}"
                )
            source = step_by_id.get(source_id)
            if source is None:
                raise RecipeError(f"{step.id}.{input_id}: unknown node {source_id}")
            if position.get(source_id, 10**9) >= position.get(step.id, -1):
                raise RecipeError(
                    f"{step.id}.{input_id}: source {source_id} must run earlier"
                )
            ancestors: set[str] = set()
            stack = list(step.needs)
            while stack:
                dependency = stack.pop()
                if dependency in ancestors:
                    continue
                ancestors.add(dependency)
                parent = step_by_id.get(dependency)
                if parent is not None:
                    stack.extend(parent.needs)
            if source_id not in ancestors:
                raise RecipeError(
                    f"{step.id}.{input_id}: add {source_id} to needs to guarantee ordering"
                )
            outputs = {port.id: port for port in _output_ports(source.type)}
            output_port = outputs.get(source_port)
            if output_port is None:
                raise RecipeError(
                    f"{step.id}.{input_id}: unknown output {source_id}.{source_port}"
                )
            if not type_compatible(output_port.type, port.type):
                raise RecipeError(
                    f"{step.id}.{input_id}: type mismatch "
                    f"{output_port.type} -> {port.type}"
                )
    from videoflow.domain.paths import resolve_allowed
    from videoflow.runtime import allowed_roots

    for step in recipe.steps:
        try:
            if step.media_override.strip():
                media = resolve_allowed(Path(step.media_override), allowed_roots())
                if not media.is_file():
                    raise RecipeError(
                        f"{step.id}: media override is not a file: {media}"
                    )
            if step.output_mode == "folder":
                if not step.output_dir.strip():
                    raise RecipeError(f"{step.id}: output folder is required")
                resolve_allowed(Path(step.output_dir), allowed_roots())
        except VideoFlowError as exc:
            raise RecipeError(f"{step.id}: {exc}") from exc

    # Required ports may remain implicit for legacy recipes. Explicit wiring must
    # supply every required input it declares.
    for step in recipe.steps:
        if not step.inputs:
            continue
        required = {port.id for port in _input_ports(step.type) if port.required}
        missing = sorted(required - set(step.inputs))
        if missing:
            raise RecipeError(f"{step.id}: missing required inputs {missing}")


def _input_ports(step_type: str) -> tuple[PortSpec, ...]:
    return ports_for_type(step_type)[0]


def _output_ports(step_type: str) -> tuple[PortSpec, ...]:
    return ports_for_type(step_type)[1]


def read_context(context: Any, key: str) -> Any:
    if key.startswith("artifacts:"):
        return context.artifacts.get(key.split(":", 1)[1])
    if key.startswith("metadata:"):
        return context.metadata.get(key.split(":", 1)[1])
    return getattr(context, key, None)


def write_context(context: Any, key: str, value: Any) -> None:
    if key.startswith("artifacts:"):
        context.artifacts[key.split(":", 1)[1]] = value
    elif key.startswith("metadata:"):
        context.metadata[key.split(":", 1)[1]] = value
    else:
        setattr(context, key, value)


def capture_outputs(context: Any, step: Any, node_id: str) -> None:
    outputs: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for port in step.output_ports:
        value = copy.deepcopy(read_context(context, port.context_key))
        outputs[port.id] = value
        hashes[port.id] = digest_value(value)
    context.port_outputs[node_id] = outputs
    context.port_hashes[node_id] = hashes


def apply_inputs(context: Any, step: Any, wiring: dict[str, str]) -> None:
    input_ports = {port.id: port for port in step.input_ports}
    for input_id, reference in wiring.items():
        port = input_ports[input_id]
        source_id, _, source_port = reference.partition(".")
        if source_id not in context.port_outputs:
            raise RecipeError(f"Input source {source_id} has not produced an output")
        source_outputs = context.port_outputs[source_id]
        if source_port not in source_outputs:
            raise RecipeError(f"Input source {source_id}.{source_port} is missing")
        write_context(context, port.context_key, copy.deepcopy(source_outputs[source_port]))


def input_fingerprint(context: Any, wiring: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for input_id, reference in wiring.items():
        source_id, _, source_port = reference.partition(".")
        result[input_id] = context.port_hashes.get(source_id, {}).get(source_port, "")
    return result


def digest_value(value: Any) -> str:
    try:
        serialized = json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        serialized = repr(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]
