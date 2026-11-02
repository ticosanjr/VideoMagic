from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from videoflow.core.context import PipelineContext
from videoflow.core.recipe import parse_recipe
from videoflow.domain.state import InactiveSpan, MediaInfo, Sentence
from videoflow.engine.runner import RecipeRunner
from videoflow.steps import requirements_by_type, step_types
from videoflow.steps.audio import VadParams, VadStep
from videoflow.steps.base import StepIO
from videoflow.steps.retakes import RetakesParams, RetakesStep
from videoflow.steps.timeline import TimelineParams, TimelineStep


class FakeVadAdapter:
    def __init__(self, spans: list[tuple[int, int]]) -> None:
        self.spans = spans

    def detect_speech(self, wav_path: Path, **kwargs: object) -> list[tuple[int, int]]:
        return self.spans


def context(tmp_path: Path, *, digest: str | None = None) -> PipelineContext:
    media = MediaInfo(
        source_path=str(tmp_path / "source.mp4"),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=media,
        pcm_digest=digest or uuid4().hex,
    )


def test_vad_emits_silence_spans(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    step = VadStep()
    step.run(
        ctx,
        VadParams(engine="ffmpeg", apply_pads=False),
        StepIO(adapter=FakeVadAdapter([(0, 48000), (96000, 144000)])),
    )

    assert [(span.start_sample, span.end_sample) for span in ctx.silence_spans] == [
        (48000, 96000)
    ]
    assert ctx.silence_spans[0].reason == "silence"


def test_retakes_emit_manual_and_automatic_spans(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    ctx.transcript = [
        Sentence(id=0, start_sample=0, end_sample=48000, text="Manual cut."),
        Sentence(id=1, start_sample=48000, end_sample=96000, text="Repeat."),
        Sentence(id=2, start_sample=96000, end_sample=144000, text="Repeat."),
    ]
    ctx.speech_intervals = [(0, 144000)]
    step = RetakesStep()
    step.run(
        ctx,
        RetakesParams(
            enabled=True,
            manual_overrides=[{"sentence_id": 0, "action": "discard"}],
        ),
        StepIO(),
    )

    assert [
        (span.start_sample, span.end_sample, span.reason)
        for span in ctx.retake_spans
    ] == [(0, 48000, "manual"), (48000, 96000, "retake")]


def test_timeline_creates_inactive_segments_with_reasons(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    ctx.speech_intervals = [(48000, 96000)]
    ctx.silence_spans = [
        InactiveSpan(start_sample=start, end_sample=end, reason="silence")
        for start, end in [(0, 48000), (96000, 144000)]
    ]
    ctx.retake_spans = [
        InactiveSpan(start_sample=0, end_sample=48000, reason="manual")
    ]
    step = TimelineStep()
    step.run(
        ctx,
        TimelineParams(
            cut_mode="hard",
            pad_before_ms=0,
            pad_after_ms=0,
            zoom_mode="manual_rules",
        ),
        StepIO(),
    )

    assert ctx.state is not None
    assert [
        (
            item.video.source_in_frame,
            item.video.source_out_frame,
            item.reason,
        )
        for item in ctx.state.inactive_segments
    ] == [(0, 30, "manual"), (60, 90, "silence")]
    assert [span.reason for span in ctx.inactive_spans] == ["manual", "silence"]


class FakeRecipeAdapter:
    def __init__(self) -> None:
        self.digest = uuid4().hex

    def probe(self, path: Path) -> MediaInfo:
        return MediaInfo(
            source_path=str(path),
            duration_frames=90,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        )

    def extract_pcm(
        self, source: Path, destination: Path, *, sample_rate: int = 16000
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"RIFF")
        return destination

    def pcm_digest(self, path: Path) -> str:
        return self.digest

    def detect_speech(self, wav_path: Path, **kwargs: object) -> list[tuple[int, int]]:
        return [(0, 48000), (96000, 144000)]


def test_recipe_wires_silence_into_inactive_segments(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "silence_inactive",
            "name": "Silence inactive",
            "steps": [
                {"id": "ingest", "type": "ingest", "params": {"extract_pcm": True}},
                {
                    "id": "vad",
                    "type": "audio.vad",
                    "needs": ["ingest"],
                    "inputs": {"media": "ingest.media"},
                    "params": {"engine": "ffmpeg", "apply_pads": False},
                },
                {
                    "id": "timeline",
                    "type": "edit.timeline",
                    "needs": ["vad"],
                    "inputs": {
                        "speech": "vad.speech",
                        "silence": "vad.silence",
                    },
                    "params": {
                        "cut_mode": "hard",
                        "pad_before_ms": 0,
                        "pad_after_ms": 0,
                        "zoom_mode": "manual_rules",
                    },
                },
            ],
        }
    )
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    result = RecipeRunner(recipe, adapter=FakeRecipeAdapter()).run(
        source, tmp_path / "out", resume=False
    )

    assert result.context.state is not None
    assert [
        (item.video.source_in_frame, item.video.source_out_frame, item.reason)
        for item in result.context.state.inactive_segments
    ] == [(30, 60, "silence")]
    assert result.context.port_outputs["timeline"]["inactive"][0].reason == "silence"
