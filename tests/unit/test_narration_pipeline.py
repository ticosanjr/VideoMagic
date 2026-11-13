from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import narration, voice_clone
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import TranscriptionError, TtsError
from videoflow.domain.state import Sentence
from videoflow.steps.base import StepIO
from videoflow.steps.narration import (
    NarrationAlignParams,
    NarrationAlignStep,
    NarrationParams,
    NarrationSynthesizeStep,
    _script_texts,
)


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir(parents=True)
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_provider_chain_prefers_the_requested_provider(monkeypatch) -> None:
    chain = [{"id": "a"}, {"id": "b"}]
    monkeypatch.setattr(narration, "resolve_chain", lambda capability: chain)
    assert narration._provider_chain("b") == [{"id": "b"}, {"id": "a"}]
    assert narration._provider_chain("missing") == chain


def test_synth_part_uses_an_openai_provider(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "part.mp3"
    calls: list[dict[str, object]] = []

    class Adapter:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def synthesize(self, text, destination, *, speed):
            Path(destination).write_bytes(b"audio")
            return Path(destination)

    monkeypatch.setattr(
        narration, "_provider_chain", lambda provider_id: [{
            "id": "openai",
            "kind": "openai_compatible",
            "base_url": "http://127.0.0.1:1/v1",
            "model": "tts",
            "api_key_env": "KEY",
        }]
    )
    monkeypatch.setattr(narration, "OpenAITtsAdapter", Adapter)
    monkeypatch.setattr(narration, "get_secret", lambda name: "secret")

    provider = narration._synth_part("hello", target, provider_id="", speed=1.2)

    assert provider == "openai"
    assert target.read_bytes() == b"audio"
    assert calls[0]["voice"]


def test_synth_part_uses_piper_when_configured(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "part.wav"
    used: list[str] = []

    class Piper:
        def __init__(self, **kwargs):
            used.append("piper")

        def synthesize(self, text, destination, *, speed):
            Path(destination).write_bytes(b"piper")
            return Path(destination)

    monkeypatch.setattr(narration, "_provider_chain", lambda provider_id: [])
    monkeypatch.setattr(
        narration,
        "load_settings",
        lambda: SimpleNamespace(tts=SimpleNamespace(provider="piper")),
    )
    monkeypatch.setattr(narration, "PiperTtsAdapter", Piper)

    assert narration._synth_part("hello", target, provider_id="", speed=1.0) == "piper"
    assert used == ["piper"]


def test_synth_part_rejects_missing_providers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(narration, "_provider_chain", lambda provider_id: [])
    monkeypatch.setattr(
        narration,
        "load_settings",
        lambda: SimpleNamespace(tts=SimpleNamespace(provider="none")),
    )
    with pytest.raises(TtsError):
        narration._synth_part("hello", tmp_path / "x.mp3", provider_id="", speed=1.0)


def test_concat_and_normalize_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(narration, "find_binary", lambda name: "ffmpeg")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        target = Path(command[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"wav")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(narration.subprocess, "run", fake_run)
    first = tmp_path / "a.wav"
    first.write_bytes(b"a")
    target = tmp_path / "joined.wav"
    assert narration._concat_parts([first], target, 48000) == target
    assert target.is_file()

    source = tmp_path / "source.wav"
    source.write_bytes(b"s")
    assert narration._normalize(source, source, 48000) == source
    assert commands


def test_concat_failure_is_actionable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(narration, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        narration.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(TtsError, match="concatenate"):
        narration._concat_parts([tmp_path / "a.wav"], tmp_path / "out.wav", 48000)


def test_probe_duration_and_copy_narration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(narration, "find_binary", lambda name: "ffprobe")
    monkeypatch.setattr(
        narration.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="2.500\n", returncode=0, stderr=""),
    )
    assert narration.probe_duration(tmp_path / "x.wav") == 2.5

    source = tmp_path / "voice.wav"
    source.write_bytes(b"wav")
    target = tmp_path / "copied.wav"
    result = narration.copy_narration(source, target)
    assert target.read_bytes() == b"wav"
    assert result["provider"] == "human"

    with pytest.raises(TtsError):
        narration.copy_narration(tmp_path / "missing.wav", tmp_path / "x.wav")


def test_synthesize_narration_assembles_parts(tmp_path: Path, monkeypatch) -> None:
    def fake_synth(text, target, provider_id, speed):
        Path(target).write_bytes(b"part")
        return "openai"

    monkeypatch.setattr(narration, "_synth_part", fake_synth)
    monkeypatch.setattr(
        narration,
        "_concat_parts",
        lambda parts, target, sample_rate: (Path(target).write_bytes(b"joined") or target),
    )
    monkeypatch.setattr(
        narration,
        "_normalize",
        lambda source, target, sample_rate: (Path(target).write_bytes(b"final") or target),
    )
    monkeypatch.setattr(narration, "probe_duration", lambda path: 3.0)

    result = narration.synthesize_narration(
        ["hello", "world"], tmp_path / "audio", sample_rate=48000
    )

    assert Path(result["path"]).read_bytes() == b"final"
    assert result["sections"] == 2
    assert result["provider"] == "openai"


def test_synthesize_narration_uses_a_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        voice_clone,
        "synthesize",
        lambda request: b"cloned",
    )
    monkeypatch.setattr(
        narration,
        "_concat_parts",
        lambda parts, target, sample_rate: (Path(target).write_bytes(b"joined") or target),
    )
    monkeypatch.setattr(
        narration,
        "_normalize",
        lambda source, target, sample_rate: (Path(target).write_bytes(b"final") or target),
    )
    monkeypatch.setattr(narration, "probe_duration", lambda path: 2.0)

    result = narration.synthesize_narration(
        ["hello"], tmp_path / "audio", profile_id="voice-1"
    )

    assert result["provider"] == "voice_clone"
    assert (tmp_path / "audio" / "parts" / "part-001.mp3").read_bytes() == b"cloned"


def test_script_texts_reads_script_and_narration_file(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (context.output / "script").mkdir(parents=True)
    (context.output / "script" / "script.json").write_text(
        '{"sections":[{"narration":"hello"},{"narration":""}]}',
        encoding="utf-8",
    )
    assert _script_texts(context) == ["hello"]

    (context.output / "script" / "script.json").unlink()
    (context.output / "script" / "narration.txt").write_text("fallback", encoding="utf-8")
    assert _script_texts(context) == ["fallback"]


def test_narration_synthesize_requires_a_source_or_script(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(TtsError):
        NarrationSynthesizeStep().run(context, NarrationParams(), StepIO())


def test_narration_synthesize_copies_a_human_track(tmp_path: Path) -> None:
    context = _context(tmp_path)
    source = tmp_path / "voice.wav"
    source.write_bytes(b"wav")
    NarrationSynthesizeStep().run(
        context, NarrationParams(source_path=str(source)), StepIO()
    )
    assert Path(context.artifacts["audio_narration"]).is_file()
    assert context.metadata["narration"]["provider"] == "human"


def test_narration_align_uses_an_srt(tmp_path: Path) -> None:
    context = _context(tmp_path)
    audio = context.output / "audio" / "narration.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"wav")
    context.artifacts["audio_narration"] = str(audio)
    srt = tmp_path / "narration.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

    NarrationAlignStep().run(
        context,
        NarrationAlignParams(srt_path=str(srt)),
        StepIO(),
    )

    assert context.transcript
    assert context.transcript_source == "narration"
    assert Path(context.artifacts["narration_words"]).is_file()


def test_narration_align_requires_audio(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(TranscriptionError):
        NarrationAlignStep().run(context, NarrationAlignParams(), StepIO())


def test_available_mode_prefers_faster_whisper(monkeypatch) -> None:
    import sys
    from types import ModuleType

    monkeypatch.setitem(sys.modules, "faster_whisper", ModuleType("faster_whisper"))
    assert NarrationAlignStep._available_mode() == "faster_whisper"


def test_align_http_mode(tmp_path: Path, monkeypatch) -> None:

    from videoflow.domain.state import Sentence

    context = _context(tmp_path)
    audio = context.output / "audio" / "narration.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"wav")
    context.artifacts["audio_narration"] = str(audio)

    class Client:
        def __init__(self, **kwargs):
            pass

        def transcribe(self, path, sample_rate):
            return [Sentence(id=0, start_sample=0, end_sample=100, text="hello")]

    monkeypatch.setattr(
        "videoflow.steps.narration.WhisperHttpAdapter", Client
    )
    NarrationAlignStep().run(
        context,
        NarrationAlignParams(
            mode="http", base_url="http://127.0.0.1:1/v1", srt_path=""
        ),
        StepIO(),
    )
    assert context.transcript[0].text == "hello"
    assert context.metadata["narration_transcript"]["sample_rate"] == 48000


def test_align_whisper_cpp_mode(tmp_path: Path, monkeypatch) -> None:
    from videoflow.domain.state import Sentence

    context = _context(tmp_path)
    audio = context.output / "audio" / "narration.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"wav")
    context.artifacts["audio_narration"] = str(audio)

    class Client:
        def __init__(self, **kwargs):
            pass

        def transcribe(self, path, sample_rate):
            return [Sentence(id=0, start_sample=0, end_sample=100, text="hello")]

    monkeypatch.setattr("videoflow.steps.narration.WhisperCliAdapter", Client)
    monkeypatch.setattr("videoflow.runtime.find_whisper_binary", lambda: "whisper")
    monkeypatch.setattr("videoflow.runtime.find_whisper_model", lambda: "model.bin")
    NarrationAlignStep().run(
        context, NarrationAlignParams(mode="whisper_cpp"), StepIO()
    )
    assert context.transcript[0].text == "hello"


def test_synthesize_uses_the_returned_path_and_cache(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    (context.output / "script").mkdir(parents=True)
    (context.output / "script" / "script.json").write_text(
        '{"sections":[{"narration":"hello"}]}', encoding="utf-8"
    )
    produced = context.output / "audio" / "narration" / "voice.wav"
    produced.parent.mkdir(parents=True)
    produced.write_bytes(b"wav")

    monkeypatch.setattr(
        "videoflow.steps.narration.synthesize_narration",
        lambda *args, **kwargs: {
            "path": str(produced),
            "duration_sec": 1.0,
            "provider": "test",
            "sections": 1,
        },
    )
    NarrationSynthesizeStep().run(context, NarrationParams(), StepIO())
    assert context.artifacts["audio_narration"] == str(produced)
    assert NarrationSynthesizeStep().cache_outputs(context)

    missing = _context(tmp_path / "missing")
    (missing.output / "script").mkdir(parents=True)
    (missing.output / "script" / "script.json").write_text(
        '{"sections":[{"narration":"hello"}]}', encoding="utf-8"
    )
    monkeypatch.setattr(
        "videoflow.steps.narration.synthesize_narration",
        lambda *args, **kwargs: {"path": str(missing.output / "gone.wav")},
    )
    with pytest.raises(TtsError, match="did not write"):
        NarrationSynthesizeStep().run(missing, NarrationParams(), StepIO())


def test_available_mode_falls_back_to_whisper_cpp_and_http(monkeypatch) -> None:
    import sys
    from types import ModuleType

    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    monkeypatch.setattr(
        "videoflow.runtime.find_whisper_binary", lambda: "/bin/whisper", raising=False
    )
    assert NarrationAlignStep._available_mode() == "whisper_cpp"
    monkeypatch.setattr(
        "videoflow.runtime.find_whisper_binary",
        lambda: (_ for _ in ()).throw(RuntimeError("no runtime")),
        raising=False,
    )
    assert NarrationAlignStep._available_mode() == "http"
    monkeypatch.setitem(sys.modules, "faster_whisper", ModuleType("faster_whisper"))


def test_align_transcribe_errors(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        "videoflow.steps.narration.load_settings",
        lambda: SimpleNamespace(llm=SimpleNamespace(base_url="")),
    )
    context = _context(tmp_path)
    audio = context.output / "audio" / "narration.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"wav")
    context.artifacts["audio_narration"] = str(audio)
    step = NarrationAlignStep()
    with pytest.raises(TranscriptionError, match="base URL"):
        step._transcribe(audio, 48000, NarrationAlignParams(), StepIO(), "http")

    monkeypatch.setattr("videoflow.runtime.find_whisper_binary", lambda: None)
    monkeypatch.setattr("videoflow.runtime.find_whisper_model", lambda: None)
    with pytest.raises(TranscriptionError, match="Whisper CLI"):
        step._transcribe(audio, 48000, NarrationAlignParams(), StepIO(), "whisper_cpp")

    class Adapter:
        def __init__(self, **kwargs):
            pass

        def transcribe(self, path, sample_rate):
            return [Sentence(id=0, start_sample=0, end_sample=10, text="hi")]

    monkeypatch.setattr("videoflow.steps.narration.FasterWhisperAdapter", Adapter)
    assert step._transcribe(
        audio, 48000, NarrationAlignParams(), StepIO(), "faster_whisper"
    )


def test_align_empty_transcript_and_cache(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    audio = context.output / "audio" / "narration.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"wav")
    context.artifacts["audio_narration"] = str(audio)
    monkeypatch.setattr(
        NarrationAlignStep,
        "_transcribe",
        lambda self, *args: [],
    )
    with pytest.raises(TranscriptionError, match="no sentences"):
        NarrationAlignStep().run(context, NarrationAlignParams(mode="http"), StepIO())
    assert NarrationAlignStep().cache_outputs(context) == ()
