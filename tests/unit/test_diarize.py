from pathlib import Path

from videoflow.application.shorts import CaptionLine, build_ass_lines
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.domain.state import MediaInfo, Sentence
from videoflow.steps.base import StepIO
from videoflow.steps.diarize import DiarizeParams, DiarizeStep


def context(tmp_path: Path) -> PipelineContext:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=300,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    return PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=media,
        transcript=[
            Sentence(id=0, start_sample=0, end_sample=48000, text="One."),
            Sentence(id=1, start_sample=96000, end_sample=144000, text="Two."),
            Sentence(id=2, start_sample=192000, end_sample=240000, text="Three."),
        ],
    )


def test_heuristic_speaker_turns(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    step = DiarizeStep()
    step.run(ctx, DiarizeParams(pause_ms=500, max_speakers=3), StepIO())
    assert [sentence.speaker for sentence in ctx.transcript] == [0, 1, 2]
    assert ctx.metadata["speaker_count"] == 3


def test_speaker_color_is_emitted_in_ass() -> None:
    ass = build_ass_lines(
        [CaptionLine(start=0.0, end=1.0, text="Hello", speaker=1)],
        style=CaptionStyle(speaker_colors=["#FFFFFF", "#00E5FF"]),
        width=1080,
        height=1920,
    )
    assert "\\c&H" in ass


def test_model_turns_are_assigned_by_overlap(tmp_path: Path, monkeypatch) -> None:
    from videoflow.adapters.diarization import SpeakerTurn
    from videoflow.domain.errors import CapabilityUnavailableError

    ctx = context(tmp_path)
    ctx.pcm_path = tmp_path / "source.wav"
    ctx.pcm_path.write_bytes(b"RIFF")

    class FakeDiarizer:
        def __init__(self, **kwargs):
            pass

        def diarize(self, audio_path, *, sample_rate):
            return [
                SpeakerTurn(0, 48000, "A"),
                SpeakerTurn(96000, 240000, "B"),
            ]

    monkeypatch.setattr("videoflow.steps.diarize.PyannoteDiarizer", FakeDiarizer)
    DiarizeStep().run(
        ctx,
        DiarizeParams(method="pyannote", fallback_to_heuristic=False),
        StepIO(),
    )
    assert [sentence.speaker for sentence in ctx.transcript] == [0, 1, 1]
    assert ctx.metadata["diarization_method"] == "pyannote"

    class MissingDiarizer:
        def __init__(self, **kwargs):
            pass

        def diarize(self, audio_path, *, sample_rate):
            raise CapabilityUnavailableError("diarization", "missing model")

    monkeypatch.setattr("videoflow.steps.diarize.PyannoteDiarizer", MissingDiarizer)
    (tmp_path / "fallback").mkdir()
    fallback = context(tmp_path / "fallback")
    fallback.pcm_path = tmp_path / "source.wav"
    DiarizeStep().run(fallback, DiarizeParams(method="pyannote"), StepIO())
    assert fallback.metadata["diarization_method"] == "heuristic"
    assert fallback.warnings


def test_reframe_enables_split_screen_for_multi_speaker_clip(tmp_path: Path) -> None:
    from videoflow.application.shorts import ShortClip
    from videoflow.steps.shorts_reframe import ReframeParams, ReframeStep

    ctx = context(tmp_path)
    ctx.transcript[1] = ctx.transcript[1].model_copy(update={"speaker": 1})
    ctx.selected_shorts = [
        ShortClip(
            title="Dialogue",
            start_sample=0,
            end_sample=240000,
            sentence_ids=(0, 1, 2),
            pieces=((0, 240000),),
        )
    ]
    ReframeStep().run(
        ctx,
        ReframeParams(mode="center_crop_9_16", split_screen_on_dialogue=True),
        StepIO(),
    )
    clip = ctx.selected_shorts[0]
    assert clip.split_screen is True
    assert clip.split_screen_focus_left < clip.split_screen_focus_right
