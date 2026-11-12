# ruff: noqa: E501
from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, Sentence, WordTiming
from videoflow.steps.base import StepIO
from videoflow.steps.captions import CaptionsPlanParams, CaptionsPlanStep
from videoflow.steps.motion_attach import (
    MotionAttachParams,
    MotionAttachStep,
    MotionCalloutParams,
    MotionCalloutStep,
)
from videoflow.steps.narration import NarrationParams, NarrationSynthesizeStep
from videoflow.steps.qa_media import (
    QaFramesParams,
    QaFramesStep,
    QaRepairParams,
    QaRepairStep,
    QaTranscriptParams,
    QaTranscriptStep,
)
from videoflow.steps.scene_web import (
    SceneCodegenParams,
    SceneCodegenStep,
    SceneRenderParams,
)
from videoflow.steps.storyboard_timed import StoryboardTimedStep, TimedUnitsParams
from videoflow.steps.vision_analysis import VisionOcrParams, VisionOcrStep
from videoflow.steps.vision_qa import VisionQaParams, VisionQaStep


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir()
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def _wav(path: Path, seconds: float = 1.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


def test_narration_synthesize_copies_a_human_track(tmp_path: Path) -> None:
    context = _context(tmp_path)
    sample = _wav(tmp_path / "voice.wav", seconds=0.4)

    NarrationSynthesizeStep().run(
        context,
        NarrationParams(source_path=str(sample)),
        StepIO(),
    )

    assert Path(context.artifacts["audio_narration"]).is_file()
    assert context.metadata["narration_duration_sec"] > 0
    assert context.metadata["narration"]["provider"] == "human"


def test_storyboard_timed_uses_word_timestamps(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (context.output / "script").mkdir(parents=True)
    (context.output / "script" / "script.json").write_text(
        json.dumps(
            {
                "sections": [
                    {
                        "id": 1,
                        "title": "Abertura",
                        "narration": "isto e um teste",
                        "visual": "lista de passos",
                        "duration_sec": 3,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (context.output / "narration").mkdir(parents=True)
    (context.output / "narration" / "transcript.json").write_text(
        json.dumps(
            {
                "sample_rate": 1000,
                "sentences": [
                    {
                        "id": 0,
                        "start_sample": 0,
                        "end_sample": 4000,
                        "text": "isto e um teste",
                        "speaker": 0,
                        "words": [
                            {"word": "isto", "start_sample": 0, "end_sample": 500, "probability": 1.0},
                            {"word": "e", "start_sample": 500, "end_sample": 1000, "probability": 1.0},
                            {"word": "um", "start_sample": 1000, "end_sample": 1500, "probability": 1.0},
                            {"word": "teste", "start_sample": 1500, "end_sample": 4000, "probability": 1.0},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    StoryboardTimedStep().run(context, TimedUnitsParams(), StepIO())

    units = json.loads(
        (context.output / "storyboard" / "units.json").read_text(encoding="utf-8")
    )["units"]
    assert units[0]["start_sec"] == 0.0
    assert units[0]["end_sec"] == 4.0
    assert units[0]["layout"] == "full_screen"


def test_scene_codegen_writes_html_and_scene_graph(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (context.output / "storyboard").mkdir(parents=True)
    (context.output / "storyboard" / "units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "UNIT-0001",
                        "title": "Teste",
                        "start_sec": 0,
                        "end_sec": 4,
                        "duration_sec": 4,
                        "narration": "texto",
                        "layout": "full_screen",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (context.output / "style").mkdir(parents=True)
    (context.output / "style" / "style-guide.json").write_text(
        json.dumps({"palette": ["#080B10", "#F8FAFC", "#FF3B30"]}),
        encoding="utf-8",
    )

    SceneCodegenStep().run(context, SceneCodegenParams(), StepIO())

    scenes = json.loads(
        (context.output / "motion" / "scenes.json").read_text(encoding="utf-8")
    )["scenes"]
    assert len(scenes) == 1
    html = context.output / "motion" / "code" / "SCENE-0001.html"
    assert html.is_file()
    assert "window.setTime" in html.read_text(encoding="utf-8")
    assert SceneRenderParams().engine == "auto"


def test_captions_plan_writes_ass_and_merged_subtitles(tmp_path: Path) -> None:
    context = _context(tmp_path)
    words = [
        WordTiming(word=word, start_sample=index * 4000, end_sample=(index + 1) * 4000, probability=1.0)
        for index, word in enumerate(["uma", "frase", "curta"])
    ]
    context.transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=12000,
            text="uma frase curta",
            words=words,
        )
    ]

    CaptionsPlanStep().run(context, CaptionsPlanParams(max_chars=20), StepIO())

    assert (context.output / "captions" / "captions.ass").is_file()
    assert (context.output / "subtitles.ass").is_file()


def test_vision_ocr_records_boxes(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    context.source.write_bytes(b"x")
    monkeypatch.setattr(
        "videoflow.steps.vision_analysis.extract_frames",
        lambda *args, **kwargs: [context.source],
    )
    monkeypatch.setattr(
        "videoflow.steps.vision_analysis.ocr_boxes",
        lambda *args, **kwargs: [
            {"text": "Olá", "confidence": 0.9, "x": 10, "y": 10, "width": 20, "height": 10}
        ],
    )

    VisionOcrStep().run(context, VisionOcrParams(), StepIO())

    payload = json.loads(
        (context.output / "vision" / "ocr.json").read_text(encoding="utf-8")
    )
    assert payload["frames"][0]["boxes"][0]["text"] == "Olá"


def test_motion_callout_and_attach(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    context = _context(tmp_path)
    (context.output / "storyboard").mkdir(parents=True)
    (context.output / "storyboard" / "units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "UNIT-0001",
                        "title": "Ponto principal",
                        "start_sec": 0,
                        "end_sec": 4,
                        "duration_sec": 4,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    context.media = MediaInfo(
        source_path=str(context.source),
        duration_frames=120,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    from videoflow.domain.state import ProjectState

    context.state = ProjectState(media_info=context.media)

    MotionCalloutStep().run(context, MotionCalloutParams(), StepIO())
    callouts = json.loads(
        (context.output / "motion" / "callouts.json").read_text(encoding="utf-8")
    )["callouts"]
    assert callouts
    assert Path(callouts[0]["path"]).is_file()

    MotionAttachStep().run(context, MotionAttachParams(), StepIO())
    assert context.state.overlays
    assert context.state.overlays[0].overlay_id.startswith("callout-")


def test_qa_frames_transcript_vision_and_repair(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    video = context.output / "exports" / "master.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    context.artifacts["video"] = str(video)
    monkeypatch.setattr(
        "videoflow.steps.qa_media.detect_black",
        lambda *args, **kwargs: [
            {
                "kind": "black_frame",
                "severity": "critical",
                "start_sec": 1.0,
                "end_sec": 1.2,
                "message": "black",
            }
        ],
    )
    monkeypatch.setattr(
        "videoflow.steps.qa_media.detect_freeze", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        "videoflow.steps.qa_media.extract_frames", lambda *args, **kwargs: []
    )

    QaFramesStep().run(context, QaFramesParams(), StepIO())
    assert context.metadata["qa_frames"]["critical_count"] == 1

    (context.output / "script").mkdir(parents=True)
    (context.output / "script" / "narration.txt").write_text(
        "uma frase curta", encoding="utf-8"
    )
    (context.output / "narration").mkdir(parents=True)
    (context.output / "narration" / "transcript.json").write_text(
        json.dumps(
            {
                "sentences": [
                    {"text": "uma frase curta", "start_sample": 0, "end_sample": 1}
                ]
            }
        ),
        encoding="utf-8",
    )
    QaTranscriptStep().run(context, QaTranscriptParams(), StepIO())
    assert context.metadata["qa_transcript"]["passed"] is True

    (context.output / "storyboard").mkdir(parents=True)
    (context.output / "storyboard" / "units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "UNIT-0001",
                        "start_sec": 0,
                        "end_sec": 4,
                        "title": "Abertura",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    VisionQaStep().run(context, VisionQaParams(), StepIO())
    assert context.metadata["vision_qa"]["critical_count"] == 1

    QaRepairStep().run(context, QaRepairParams(), StepIO())
    assert context.metadata["qa_repair"]["issues"][0]["unit_id"] == "UNIT-0001"


def test_qa_frames_flags_near_empty_layouts(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    context = _context(tmp_path)
    video = context.output / "exports" / "master.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    context.artifacts["video"] = str(video)
    frame = tmp_path / "empty.png"
    Image.new("L", (64, 64), color=2).save(frame)
    monkeypatch.setattr(
        "videoflow.steps.qa_media.detect_black", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        "videoflow.steps.qa_media.detect_freeze", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        "videoflow.steps.qa_media.extract_frames",
        lambda *args, **kwargs: [frame],
    )

    QaFramesStep().run(context, QaFramesParams(), StepIO())

    kinds = [item["kind"] for item in context.metadata["qa_frames"]["issues"]]
    assert "empty_frame" in kinds
    assert context.metadata["qa_frames"]["passed"] is False


def test_vision_qa_uses_a_configured_vision_provider(monkeypatch) -> None:
    from videoflow.steps import vision_qa

    monkeypatch.setattr(
        vision_qa,
        "resolve_chain",
        lambda capability: [
            {
                "id": "vision-test",
                "kind": "openai_compatible",
                "base_url": "http://127.0.0.1:9999/v1",
                "model": "vision-model",
                "api_key_env": "",
            }
        ],
    )
    client = vision_qa._vision_client()
    assert client is not None
    assert client.id == "vision-test"
    assert client.model == "vision-model"


def test_vision_qa_extracts_structured_issues() -> None:
    from videoflow.steps.vision_qa import _extract_issues

    assert _extract_issues(
        {
            "issues": [
                {
                    "kind": "text_clipped",
                    "severity": "critical",
                    "message": "Title clipped",
                    "start_sec": 2.5,
                }
            ]
        }
    ) == [
        {
            "kind": "text_clipped",
            "severity": "critical",
            "message": "Title clipped",
            "start_sec": 2.5,
        }
    ]
