from __future__ import annotations

import base64
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from videoflow.application import image_gen
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError, IngestError
from videoflow.domain.state import MediaInfo, Sentence
from videoflow.steps import alignment_forced, audio_isolate, video_export
from videoflow.steps.alignment_forced import (
    ForcedAlignmentParams,
    ForcedAlignmentStep,
    _align_words,
    _device,
    _faster_whisper_words,
    _whisperx_words,
    _words_in_range,
)
from videoflow.steps.audio_isolate import AudioIsolateStep, IsolateParams
from videoflow.steps.base import StepIO
from videoflow.steps.video_export import VideoExportParams, VideoExportStep


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir(parents=True)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    return PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=MediaInfo(
            source_path=str(source),
            duration_frames=30,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        ),
    )


def test_image_generation_with_base64_and_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(image_gen, "ensure_external_allowed", lambda *args, **kwargs: None)
    encoded = base64.b64encode(b"image").decode()
    monkeypatch.setattr(
        image_gen.httpx,
        "post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200, json=lambda: {"data": [{"b64_json": encoded}]}
        ),
    )
    assert image_gen.generate_image("prompt", base_url="http://x", model="m") == b"image"

    monkeypatch.setattr(
        image_gen.httpx,
        "post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200, json=lambda: {"data": [{"url": "http://x/i.png"}]}
        ),
    )
    monkeypatch.setattr(
        image_gen.httpx,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, content=b"download"),
    )
    assert image_gen.generate_image("prompt", base_url="http://x", model="m") == b"download"
    target = image_gen.write_generated(tmp_path / "a" / "i.png", b"data")
    assert target.read_bytes() == b"data"


def test_image_generation_errors(monkeypatch) -> None:
    monkeypatch.setattr(image_gen, "ensure_external_allowed", lambda *args, **kwargs: None)
    with pytest.raises(IngestError, match="base URL"):
        image_gen.generate_image("prompt", base_url="", model="m")
    monkeypatch.setattr(
        image_gen.httpx,
        "post",
        lambda *args, **kwargs: SimpleNamespace(status_code=500, text="bad"),
    )
    with pytest.raises(IngestError, match="HTTP 500"):
        image_gen.generate_image("prompt", base_url="http://x", model="m")
    monkeypatch.setattr(
        image_gen.httpx,
        "post",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, json=lambda: {"data": []}),
    )
    with pytest.raises(IngestError, match="invalid payload"):
        image_gen.generate_image("prompt", base_url="http://x", model="m")


def test_alignment_helpers() -> None:
    assert _device("cuda") == "cuda"
    assert _device("cpu") == "cpu"
    words = [("one", 0, 10), ("two", 20, 30), ("three", 40, 50)]
    assert _words_in_range(words, 15, 35) == [("two", 20, 30)]


def test_whisperx_words_with_fake_module(monkeypatch) -> None:
    module = ModuleType("whisperx")
    module.load_audio = lambda path: "audio"  # type: ignore[attr-defined]
    module.load_model = lambda *args, **kwargs: SimpleNamespace(  # type: ignore[attr-defined]
        transcribe=lambda audio, language=None: {
            "language": "en",
            "segments": [{"words": [{"word": " hello ", "start": 0, "end": 1}]}],
        }
    )
    module.load_align_model = lambda **kwargs: (object(), {})  # type: ignore[attr-defined]
    module.align = lambda *args, **kwargs: {  # type: ignore[attr-defined]
        "segments": [{"words": [{"word": "hello", "start": 0, "end": 1}]}]
    }
    monkeypatch.setitem(sys.modules, "whisperx", module)
    words = _whisperx_words(Path("a.wav"), ForcedAlignmentParams(), 1000)
    assert words == [("hello", 0, 1000)]


def test_faster_whisper_words_and_align_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        alignment_forced.FasterWhisperAdapter,
        "available",
        lambda size: True,
    )

    class Adapter:
        available = staticmethod(lambda size: True)

        def __init__(self, **kwargs):
            pass

        def transcribe(self, source, sample_rate):
            return [
                Sentence(
                    id=0,
                    start_sample=0,
                    end_sample=100,
                    text="hi",
                    words=[],
                )
            ]

    monkeypatch.setattr(alignment_forced, "FasterWhisperAdapter", Adapter)
    assert _faster_whisper_words(Path("a.wav"), ForcedAlignmentParams(), 1000) == []
    words, backend = _align_words(
        Path("a.wav"), ForcedAlignmentParams(backend="none"), 1000, StepIO()
    )
    assert words == [] and backend == "none"


def test_forced_alignment_step(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    pcm = context.work / "audio.wav"
    pcm.parent.mkdir(parents=True, exist_ok=True)
    pcm.write_bytes(b"wav")
    context.pcm_path = pcm
    context.transcript = [
        Sentence(id=0, start_sample=0, end_sample=2000, text="hello world")
    ]
    monkeypatch.setattr(
        alignment_forced,
        "_align_words",
        lambda *args, **kwargs: ([("hello", 0, 1000), ("world", 1000, 2000)], "fake"),
    )
    ForcedAlignmentStep().run(context, ForcedAlignmentParams(), StepIO())
    assert context.transcript[0].words
    assert context.metadata["forced_alignment"]["aligned"] == 1
    assert Path(context.artifacts["forced_alignment"]).is_file()

    empty = _context(tmp_path / "empty")
    ForcedAlignmentStep().run(empty, ForcedAlignmentParams(), StepIO())
    assert "forced_alignment" not in empty.metadata


def test_audio_isolate_run_and_fallback(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    source = context.output / "audio" / "master.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"wav")
    context.artifacts["audio_master"] = str(source)
    AudioIsolateStep().run(context, IsolateParams(backend="none"), StepIO())
    assert Path(context.artifacts["audio_isolated"]).read_bytes() == b"wav"
    assert context.metadata["audio_isolated"]["backend"] == "master"

    with pytest.raises(IngestError):
        AudioIsolateStep().run(
            context, IsolateParams(backend="none", fallback_to_master=False), StepIO()
        )


def test_audio_isolate_rnnoise_backend(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    source = context.output / "audio" / "master.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"wav")
    context.artifacts["audio_master"] = str(source)
    model = tmp_path / "model.rnnn"
    model.write_bytes(b"model")
    monkeypatch.setattr(audio_isolate, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        audio_isolate,
        "_run",
        lambda command, timeout=1800: (Path(command[-1]).write_bytes(b"isolated") or True),
    )
    AudioIsolateStep().run(
        context,
        IsolateParams(backend="rnnoise", model_path=str(model)),
        StepIO(),
    )
    assert context.metadata["audio_isolated"]["backend"] == "rnnoise"


def test_video_export_fixed_and_mix(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    context.state = SimpleNamespace()
    mix = context.output / "audio" / "final.wav"
    mix.parent.mkdir(parents=True)
    mix.write_bytes(b"wav")
    context.artifacts["audio_mix"] = str(mix)

    def fake_export(state, destination, **kwargs):
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"video")
        return Path(destination)

    monkeypatch.setattr(video_export, "export_mp4", fake_export)
    replaced: list[Path] = []
    monkeypatch.setattr(
        video_export,
        "_replace_audio",
        lambda video, audio: replaced.append(Path(video)),
    )
    VideoExportStep().run(
        context,
        VideoExportParams(filename_mode="fixed", filename="out.mp4", audio_source="mix"),
        StepIO(),
    )
    assert Path(context.artifacts["video"]).read_bytes() == b"video"
    assert replaced


def test_video_export_errors(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    with pytest.raises(ExportError, match="timeline"):
        VideoExportStep().run(context, VideoExportParams(), StepIO())

    context.state = SimpleNamespace()
    with pytest.raises(ExportError, match="filename"):
        VideoExportStep().run(
            context,
            VideoExportParams(filename_mode="fixed", filename="."),
            StepIO(),
        )

    monkeypatch.setattr(
        video_export,
        "export_mp4",
        lambda state, destination, **kwargs: Path(destination).write_bytes(b"v"),
    )
    with pytest.raises(ExportError, match="mixed audio"):
        VideoExportStep().run(
            context,
            VideoExportParams(filename_mode="fixed", filename="out.mp4", audio_source="mix"),
            StepIO(),
        )


def test_replace_audio_errors(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"v")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"a")
    monkeypatch.setattr(video_export, "find_binary", lambda name: None)
    with pytest.raises(ExportError, match="FFmpeg"):
        video_export._replace_audio(video, audio)

    monkeypatch.setattr(video_export, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        video_export.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad"),
    )
    with pytest.raises(ExportError, match="replace"):
        video_export._replace_audio(video, audio)


def test_audio_isolate_backend_paths(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    source = context.output / "audio" / "master.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"wav")
    context.artifacts["audio_master"] = str(source)

    monkeypatch.setattr(audio_isolate, "find_binary", lambda name: None)
    AudioIsolateStep().run(context, IsolateParams(backend="auto"), StepIO())
    assert context.metadata["audio_isolated"]["backend"] == "master"

    def deep_filter(command, **kwargs):
        directory = Path(command[-1])
        (directory / "clean.wav").write_bytes(b"clean")
        return True

    monkeypatch.setattr(
        audio_isolate,
        "find_binary",
        lambda name: "/bin/deepFilter" if name == "deepFilter" else None,
    )
    monkeypatch.setattr(audio_isolate, "_run", deep_filter)
    AudioIsolateStep().run(context, IsolateParams(backend="deepfilternet"), StepIO())
    assert context.metadata["audio_isolated"]["backend"] == "deepfilternet"

    def demucs(command, **kwargs):
        directory = Path(command[command.index("-o") + 1])
        nested = directory / "source" / "vocals.wav"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_bytes(b"vocals")
        return True

    monkeypatch.setattr(
        audio_isolate,
        "find_binary",
        lambda name: "/bin/demucs" if name == "demucs" else None,
    )
    monkeypatch.setattr(audio_isolate, "_run", demucs)
    AudioIsolateStep().run(context, IsolateParams(backend="demucs"), StepIO())
    assert context.metadata["audio_isolated"]["backend"] == "demucs"

    monkeypatch.setattr(
        audio_isolate,
        "find_binary",
        lambda name: "/bin/deepFilter" if name == "deepFilter" else None,
    )
    import shutil

    shutil.rmtree(context.output / "audio" / "deepfilter", ignore_errors=True)
    monkeypatch.setattr(audio_isolate, "_run", lambda *args, **kwargs: True)
    AudioIsolateStep().run(context, IsolateParams(backend="deepfilternet"), StepIO())
    assert context.metadata["audio_isolated"]["backend"] == "master"
    assert AudioIsolateStep().cache_outputs(context)


def test_audio_isolate_run_reports_failures(monkeypatch) -> None:
    monkeypatch.setattr(
        audio_isolate.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing")),
    )
    assert audio_isolate._run(["x"]) is False
    monkeypatch.setattr(
        audio_isolate.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    assert audio_isolate._run(["x"]) is False
