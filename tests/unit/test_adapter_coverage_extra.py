"""Extra hermetic coverage for adapters and LLM/tracking application helpers."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import numpy as np
import pytest

from videoflow.adapters import faster_whisper as fw_module
from videoflow.adapters import opencode as oc_module
from videoflow.adapters import silero as silero_module
from videoflow.adapters.faster_whisper import FasterWhisperAdapter
from videoflow.adapters.opencode import MAX_OUTPUT, PREFIX, OpenCodeLlm
from videoflow.adapters.silero import WINDOW_SAMPLES, SileroVadAdapter
from videoflow.adapters.vision import OpenAIVisionClient
from videoflow.application import caption_ai, tracking
from videoflow.application import multimodal_llm as mm_module
from videoflow.application.caption_ai import apply_llm_emoji, generate_emoji_map
from videoflow.application.multimodal_llm import (
    analyze_short_llm,
    analyze_short_llm_entry,
    sample_frames,
)
from videoflow.domain.errors import (
    CapabilityUnavailableError,
    IngestError,
    LlmError,
    ShortEditError,
    StateNotReadyError,
    TranscriptionError,
)
from videoflow.domain.state import ProjectState, Sentence

# --------------------------------------------------------------------------- helpers


def _write_wav(
    path: Path,
    *,
    seconds: float = 0.1,
    rate: int = 16000,
    channels: int = 1,
    width: int = 2,
) -> Path:
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(width)
        audio.setframerate(rate)
        audio.writeframes(b"\0" * (frames * channels * width))
    return path


def _model_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.bin").write_bytes(b"model")
    (path / "config.json").write_text("{}", encoding="utf-8")
    return path


def _segment(text: str, words: list[object] | None) -> SimpleNamespace:
    return SimpleNamespace(text=text, words=words)


def _word(
    word: str,
    start: object,
    end: object,
    probability: object = 0.9,
) -> SimpleNamespace:
    return SimpleNamespace(word=word, start=start, end=end, probability=probability)


class _FakeWhisperEngine:
    def __init__(self, segments: list[object]) -> None:
        self.segments = segments
        self.calls: list[dict[str, object]] = []

    def transcribe(self, audio: str, **kwargs: object) -> tuple[list[object], object]:
        self.calls.append({"audio": audio, **kwargs})
        return self.segments, SimpleNamespace(language="en")


def _fake_module(name: str, **attributes: object) -> ModuleType:
    module = ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


class _RecordingLog:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, level: str, message: str) -> None:
        self.calls.append((level, message))


# --------------------------------------------------------------------------- opencode


def test_opencode_success_builds_command_and_logs_opt_in_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["command"] = command
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr(oc_module.subprocess, "run", fake_run)
    logged: list[tuple[str, str, str]] = []
    llm = OpenCodeLlm(
        binary="/opt/opencode",
        model="local-model",
        timeout=12.5,
        log=lambda level, kind, message: logged.append((level, kind, message)),
    )

    assert llm.complete_json("Summarize this.", "summary") == {"ok": True}

    assert seen["command"] == [
        "/opt/opencode",
        "run",
        "--model",
        "local-model",
        seen["command"][-1],  # type: ignore[index]
    ]
    instruction = str(seen["command"][-1])  # type: ignore[index]
    assert instruction.startswith(PREFIX)
    assert "Schema: summary" in instruction
    assert instruction.endswith("Summarize this.")
    assert seen["kwargs"]["capture_output"] is True
    assert seen["kwargs"]["text"] is True
    assert seen["kwargs"]["timeout"] == 12.5
    assert seen["kwargs"]["check"] is False
    assert logged == [
        (
            "llm",
            "warning",
            "OpenCode provider is opt-in and slower than an OpenAI-compatible endpoint",
        )
    ]


def test_opencode_defaults_do_not_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        oc_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="{}", stderr=""),
    )
    llm = OpenCodeLlm()

    assert llm.binary == "opencode"
    assert llm.model == "default"
    assert llm.timeout == 90.0
    assert llm.complete_json("prompt", "schema") == {}


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ('```json\n{"kind": "json-fence"}\n```', {"kind": "json-fence"}),
        ('```\n{"kind": "plain-fence"}\n```', {"kind": "plain-fence"}),
        ('  {"kind": "bare"}  ', {"kind": "bare"}),
    ],
)
def test_opencode_parses_fenced_and_bare_json(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    expected: dict[str, str],
) -> None:
    monkeypatch.setattr(
        oc_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=""),
    )

    assert OpenCodeLlm().complete_json("prompt", "schema") == expected


@pytest.mark.parametrize("stdout", ["not json", "[1, 2, 3]", '"text"'])
def test_opencode_rejects_unusable_or_non_object_json(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
) -> None:
    monkeypatch.setattr(
        oc_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=""),
    )

    with pytest.raises(LlmError):
        OpenCodeLlm().complete_json("prompt", "schema")


@pytest.mark.parametrize(
    ("stderr", "stdout", "expected"),
    [
        ("fatal boom", "ignored", "fatal boom"),
        ("", "stdout says no", "stdout says no"),
    ],
)
def test_opencode_reports_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
    stderr: str,
    stdout: str,
    expected: str,
) -> None:
    monkeypatch.setattr(
        oc_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 7, stdout=stdout, stderr=stderr
        ),
    )

    with pytest.raises(LlmError, match=f"exited with 7: {expected}"):
        OpenCodeLlm().complete_json("prompt", "schema")


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (FileNotFoundError("missing"), "OpenCode binary not found: opencode"),
        (subprocess.TimeoutExpired(["opencode"], 90), "OpenCode timed out after 90s"),
        (OSError("cannot spawn"), "Cannot start OpenCode: cannot spawn"),
    ],
)
def test_opencode_maps_process_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    message: str,
) -> None:
    def fail(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise error

    monkeypatch.setattr(oc_module.subprocess, "run", fail)

    with pytest.raises(LlmError, match=message):
        OpenCodeLlm().complete_json("prompt", "schema")


def test_opencode_rejects_oversized_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        oc_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="x" * (MAX_OUTPUT + 1), stderr=""
        ),
    )

    with pytest.raises(LlmError, match="output limit"):
        OpenCodeLlm().complete_json("prompt", "schema")


# --------------------------------------------------------------------------- vision


def _vision_client(
    handler: httpx.MockTransport,
    *,
    api_key: str | None = None,
) -> OpenAIVisionClient:
    return OpenAIVisionClient(
        base_url="https://vision.example.com/v1/",
        model="vision-model",
        api_key=api_key,
        timeout=5.0,
        transport=handler,
    )


def test_vision_analyze_sends_frames_and_parses_plain_json() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"scene": "ok"}'}}]})

    frames = [b"first-frame", b"second-frame"]

    assert _vision_client(httpx.MockTransport(handler)).analyze(frames, "Describe.") == {
        "scene": "ok"
    }

    assert captured["url"] == "https://vision.example.com/v1/chat/completions"
    headers = captured["headers"]
    assert headers["content-type"] == "application/json"
    assert "authorization" not in headers
    payload = captured["payload"]
    assert payload["model"] == "vision-model"
    assert payload["temperature"] == 0
    assert payload["stream"] is False
    content = payload["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "Describe."}
    first_url = content[1]["image_url"]["url"]
    assert first_url.endswith(base64.b64encode(frames[0]).decode("ascii"))
    assert first_url.startswith("data:image/jpeg;base64,")
    assert len(content) == 3


def test_vision_analyze_sends_api_key_and_serializes_dict_content() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": {"objects": ["cup"]}}}]},
        )

    result = _vision_client(httpx.MockTransport(handler), api_key="secret").analyze([], "Prompt")

    assert result == {"objects": ["cup"]}
    assert captured["headers"]["authorization"] == "Bearer secret"


def test_vision_analyze_reports_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="upstream down")

    with pytest.raises(LlmError, match="HTTP 502: upstream down"):
        _vision_client(httpx.MockTransport(handler)).analyze([b"frame"], "Prompt")


def test_vision_analyze_reports_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(LlmError, match="Cannot reach the vision endpoint: ConnectError"):
        _vision_client(httpx.MockTransport(handler)).analyze([], "Prompt")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, json=[]),
    ],
)
def test_vision_analyze_reports_unusable_response_json(response: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(LlmError, match="unusable JSON"):
        _vision_client(httpx.MockTransport(handler)).analyze([], "Prompt")


def test_vision_analyze_parses_fenced_json_content() -> None:
    fenced = '```json\n{"scene": "fenced"}\n```'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": fenced}}]})

    assert _vision_client(httpx.MockTransport(handler)).analyze([], "Prompt") == {"scene": "fenced"}


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_vision_analyze_rejects_unusable_model_json(content: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    with pytest.raises(LlmError):
        _vision_client(httpx.MockTransport(handler)).analyze([], "Prompt")


def test_vision_analyze_treats_a_short_fence_as_unusable_json() -> None:
    content = '```json {"inline": true}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    with pytest.raises(LlmError, match="did not return JSON"):
        _vision_client(httpx.MockTransport(handler)).analyze([], "Prompt")


# --------------------------------------------------------------------------- faster whisper


def test_faster_whisper_available_checks_runtime_model_and_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(fw_module, "find_faster_whisper_model", lambda size: None)
    assert FasterWhisperAdapter.available() is False

    model = _model_dir(tmp_path / "model")
    monkeypatch.setattr(fw_module, "find_faster_whisper_model", lambda size: model)
    monkeypatch.setattr(fw_module.importlib.util, "find_spec", lambda name: object())
    assert FasterWhisperAdapter.available() is True

    assert FasterWhisperAdapter.available(model=model) is True
    assert FasterWhisperAdapter.available(model=tmp_path / "missing") is False


def test_faster_whisper_validates_inputs_before_loading_a_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = FasterWhisperAdapter(model=_model_dir(tmp_path / "model"))

    with pytest.raises(TranscriptionError, match="Audio does not exist"):
        adapter.transcribe(tmp_path / "missing.wav", 16000)

    wav = _write_wav(tmp_path / "audio.wav")

    with pytest.raises(TranscriptionError, match="sample rate must be positive"):
        adapter.transcribe(wav, 0)

    unsupported = FasterWhisperAdapter(model=adapter.model, language="fr")  # type: ignore[arg-type]
    with pytest.raises(TranscriptionError, match="Unsupported transcription language: fr"):
        unsupported.transcribe(wav, 16000)

    no_beam = FasterWhisperAdapter(model=adapter.model, beam_size=0)  # type: ignore[arg-type]
    with pytest.raises(TranscriptionError, match="beam size must be positive"):
        no_beam.transcribe(wav, 16000)


def test_faster_whisper_wraps_unreadable_wav_header(tmp_path: Path) -> None:
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not a wav file")

    with pytest.raises(TranscriptionError, match="Cannot read WAV header"):
        FasterWhisperAdapter(model=_model_dir(tmp_path / "model")).transcribe(broken, 16000)


def test_faster_whisper_resolves_model_from_runtime_search(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "found-model")
    monkeypatch.setattr(fw_module, "find_faster_whisper_model", lambda size: model)
    engine = _FakeWhisperEngine([_segment("Hello.", [_word("Hello.", 0.0, 1.0)])])
    adapter = FasterWhisperAdapter(model=None, model_size="tiny")
    monkeypatch.setattr(adapter, "_load_engine", lambda path: engine)

    sentences = adapter.transcribe(wav, 16000)

    assert adapter.model is None
    assert [sentence.text for sentence in sentences] == ["Hello."]
    assert engine.calls[0]["beam_size"] == 5


def test_faster_whisper_reports_the_expected_missing_model_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    expected = tmp_path / "expected-model"
    monkeypatch.setattr(fw_module, "find_faster_whisper_model", lambda size: None)
    monkeypatch.setattr(fw_module, "expected_faster_whisper_model", lambda size: expected)
    adapter = FasterWhisperAdapter(model=None, model_size="tiny")

    with pytest.raises(TranscriptionError) as caught:
        adapter.transcribe(wav, 16000)

    message = str(caught.value)
    assert str(expected) in message
    assert "75 MB" in message
    assert "scripts/fetch_faster_whisper.py" in message


def test_faster_whisper_loads_engine_once_and_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")
    engine = _FakeWhisperEngine([_segment("Hello.", [_word("Hello.", 0.0, 1.0)])])
    created: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def factory(*args: object, **kwargs: object) -> _FakeWhisperEngine:
        created.append((args, kwargs))
        return engine

    monkeypatch.setitem(
        sys.modules, "faster_whisper", _fake_module("faster_whisper", WhisperModel=factory)
    )
    log = _RecordingLog()
    adapter = FasterWhisperAdapter(
        model=model,
        device="cpu",
        compute_type="int8",
        threads=2,
        log=log,
    )

    first = adapter.transcribe(wav, 16000)
    second = adapter.transcribe(wav, 16000)

    assert [sentence.text for sentence in first] == ["Hello."]
    assert [sentence.text for sentence in second] == ["Hello."]
    assert len(created) == 1
    args, kwargs = created[0]
    assert args == (str(model),)
    assert kwargs == {
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": 2,
        "local_files_only": True,
    }
    assert log.calls == [("debug", f"Faster-Whisper model loaded: {model}")]


def test_faster_whisper_requires_the_optional_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")
    monkeypatch.setitem(sys.modules, "faster_whisper", None)

    with pytest.raises(TranscriptionError, match="optional faster-whisper package"):
        FasterWhisperAdapter(model=model).transcribe(wav, 16000)


@pytest.mark.parametrize(
    ("device", "expected"),
    [
        ("cpu", "could not load"),
        ("cuda", "could not start on CUDA"),
    ],
)
def test_faster_whisper_maps_engine_load_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: str,
    expected: str,
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")

    def factory(*args: object, **kwargs: object) -> object:
        raise RuntimeError("driver exploded")

    monkeypatch.setitem(
        sys.modules, "faster_whisper", _fake_module("faster_whisper", WhisperModel=factory)
    )
    adapter = FasterWhisperAdapter(model=model, device=device)  # type: ignore[arg-type]

    with pytest.raises(TranscriptionError, match=expected):
        adapter.transcribe(wav, 16000)


@pytest.mark.parametrize(
    ("device", "expected"),
    [
        ("cpu", "transcription failed: engine exploded"),
        ("cuda", "Faster-Whisper failed on CUDA"),
    ],
)
def test_faster_whisper_maps_transcription_failures(
    tmp_path: Path,
    device: str,
    expected: str,
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")

    class BrokenEngine:
        def transcribe(self, audio: str, **kwargs: object) -> tuple[list[object], object]:
            raise RuntimeError("engine exploded")

    adapter = FasterWhisperAdapter(model=model, device=device)  # type: ignore[arg-type]
    adapter._engine = BrokenEngine()  # noqa: SLF001

    with pytest.raises(TranscriptionError, match=expected):
        adapter.transcribe(wav, 16000)


def test_faster_whisper_reports_an_empty_transcript_for_blank_segments(
    tmp_path: Path,
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")
    adapter = FasterWhisperAdapter(model=model)
    adapter._engine = _FakeWhisperEngine([_segment("   ", None)])  # noqa: SLF001

    with pytest.raises(TranscriptionError, match="empty transcript"):
        adapter.transcribe(wav, 16000)


def test_faster_whisper_rejects_a_wav_with_the_wrong_sample_rate(tmp_path: Path) -> None:
    wav = _write_wav(tmp_path / "audio.wav", rate=48000)
    model = _model_dir(tmp_path / "model")

    with pytest.raises(TranscriptionError, match="16 kHz audio, got 48000 Hz"):
        FasterWhisperAdapter(model=model).transcribe(wav, 16000)


def test_faster_whisper_loads_an_engine_without_a_log_callback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = _model_dir(tmp_path / "model")
    engine = _FakeWhisperEngine([])
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        _fake_module("faster_whisper", WhisperModel=lambda *args, **kwargs: engine),
    )

    loaded = FasterWhisperAdapter(model=model)._load_engine(model)  # noqa: SLF001

    assert loaded is engine


def test_faster_whisper_skips_blank_segments_and_words(
    tmp_path: Path,
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")
    engine = _FakeWhisperEngine(
        [
            _segment("   ", None),
            _segment("Kept.", [_word("   ", 0.0, 0.1), _word(" Kept. ", 0.0, 0.5)]),
        ]
    )
    adapter = FasterWhisperAdapter(model=model)
    adapter._engine = engine  # noqa: SLF001

    sentences = adapter.transcribe(wav, 16000)

    assert len(sentences) == 1
    assert sentences[0].text == "Kept."
    assert [word.word for word in sentences[0].words] == ["Kept."]
    assert sentences[0].start_sample == 0
    assert sentences[0].end_sample == 8000


def test_faster_whisper_rejects_a_segment_with_only_blank_words(
    tmp_path: Path,
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")
    adapter = FasterWhisperAdapter(model=model)
    adapter._engine = _FakeWhisperEngine(  # noqa: SLF001
        [_segment("Text without usable words.", [_word("   ", 0.0, 1.0)])]
    )

    with pytest.raises(TranscriptionError, match="no usable word timestamps"):
        adapter.transcribe(wav, 16000)


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("nonsense", 1.0, "invalid word timestamp"),
        (-0.5, 1.0, "invalid word timestamp"),
        ("1/0", 1.0, "invalid word timestamp"),
        (1.0, 0.5, "ends before it starts"),
    ],
)
def test_faster_whisper_rejects_invalid_word_times(
    tmp_path: Path,
    start: object,
    end: object,
    message: str,
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")
    adapter = FasterWhisperAdapter(model=model)
    adapter._engine = _FakeWhisperEngine(  # noqa: SLF001
        [_segment("Text.", [_word("Text.", start, end)])]
    )

    with pytest.raises(TranscriptionError, match=message):
        adapter.transcribe(wav, 16000)


def test_faster_whisper_clamps_and_defaults_word_probabilities(
    tmp_path: Path,
) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")
    adapter = FasterWhisperAdapter(model=model)
    adapter._engine = _FakeWhisperEngine(  # noqa: SLF001
        [
            _segment(
                "Words.",
                [
                    _word(" a", 0.0, 0.1, "not-a-number"),
                    _word(" b", 0.1, 0.2, 1.7),
                    _word(" c", 0.2, 0.3, -0.4),
                ],
            )
        ]
    )

    sentences = adapter.transcribe(wav, 16000)

    assert [word.probability for word in sentences[0].words] == [1.0, 1.0, 0.0]


def test_faster_whisper_truncates_long_previews_in_errors(tmp_path: Path) -> None:
    wav = _write_wav(tmp_path / "audio.wav")
    model = _model_dir(tmp_path / "model")
    adapter = FasterWhisperAdapter(model=model)
    adapter._engine = _FakeWhisperEngine([_segment("word " * 40, None)])  # noqa: SLF001

    with pytest.raises(TranscriptionError) as caught:
        adapter.transcribe(wav, 16000)

    assert "..." in str(caught.value)


# --------------------------------------------------------------------------- silero


class _SileroSession:
    def __init__(self, probabilities: list[float]) -> None:
        self.probabilities = probabilities
        self.calls = 0

    def run(self, output_names: list[str], inputs: dict[str, object]) -> tuple[np.ndarray, object]:
        assert output_names == ["output", "stateN"]
        probability = self.probabilities[self.calls]
        self.calls += 1
        return np.array([[probability]], dtype=np.float32), inputs["state"]


def _ort_session(
    probabilities: list[float],
    *,
    inputs: tuple[str, ...] = ("input", "state", "sr"),
    outputs: tuple[str, ...] = ("output", "stateN"),
) -> type:
    class Session:
        def __init__(self, path: str, sess_options: object, providers: list[str]) -> None:
            self.path = path
            self.sess_options = sess_options
            self.providers = providers
            self.probabilities = probabilities

        def get_inputs(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(name=name) for name in inputs]

        def get_outputs(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(name=name) for name in outputs]

        def run(
            self, output_names: list[str], feeds: dict[str, object]
        ) -> tuple[np.ndarray, object]:
            probability = self.probabilities.pop(0)
            return np.array([[probability]], dtype=np.float32), feeds["state"]

    return Session


def _fake_ort(session_class: object) -> ModuleType:
    class Options:
        intra_op_num_threads = 0
        log_severity_level = 0

    return _fake_module("onnxruntime", SessionOptions=Options, InferenceSession=session_class)


def test_silero_available_requires_model_and_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(silero_module, "find_silero_model", lambda: None)
    assert SileroVadAdapter.available() is False

    model = tmp_path / "silero.onnx"
    model.write_bytes(b"model")
    monkeypatch.setattr(silero_module, "find_silero_model", lambda: model)
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    assert SileroVadAdapter.available() is False

    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_module("onnxruntime"))
    assert SileroVadAdapter.available() is True


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"threshold": 0.05}, "threshold must be between"),
        ({"threshold": 0.95}, "threshold must be between"),
        ({"min_silence_ms": -1}, "durations must not be negative"),
        ({"min_speech_ms": -1}, "durations must not be negative"),
    ],
)
def test_silero_validates_parameters(
    tmp_path: Path, kwargs: dict[str, object], message: str
) -> None:
    adapter = SileroVadAdapter(model=tmp_path / "model.onnx", **kwargs)  # type: ignore[arg-type]

    with pytest.raises(IngestError, match=message):
        adapter.detect(_write_wav(tmp_path / "audio.wav"))


def test_silero_rejects_empty_and_unreadable_wav(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = SileroVadAdapter(model=tmp_path / "model.onnx")

    with pytest.raises(IngestError, match="empty WAV"):
        adapter.detect(_write_wav(tmp_path / "empty.wav", seconds=0))

    with pytest.raises(IngestError, match="Audio does not exist"):
        adapter.detect(tmp_path / "missing.wav")

    with pytest.raises(IngestError, match="mono 16-bit PCM"):
        adapter.detect(_write_wav(tmp_path / "stereo.wav", channels=2))

    with pytest.raises(IngestError, match="mono 16-bit PCM"):
        adapter.detect(_write_wav(tmp_path / "eight-bit.wav", width=1))

    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not wav")
    with pytest.raises(IngestError, match="Cannot read WAV"):
        adapter.detect(broken)


def test_silero_uses_a_cached_session_and_logs_progress(tmp_path: Path) -> None:
    log = _RecordingLog()
    session = _SileroSession([0.9, 0.9, 0.9])
    adapter = SileroVadAdapter(model=tmp_path / "model.onnx", min_speech_ms=0, log=log)
    adapter._session = session  # noqa: SLF001

    spans = adapter.detect(_write_wav(tmp_path / "audio.wav", seconds=0.096))

    assert spans == [(0, 3 * WINDOW_SAMPLES)]
    assert session.calls == 3
    assert log.calls == [("debug", f"Silero VAD {WINDOW_SAMPLES}/{3 * WINDOW_SAMPLES} samples")]


def test_silero_reports_a_missing_model(tmp_path: Path) -> None:
    adapter = SileroVadAdapter(model=tmp_path / "missing.onnx")

    with pytest.raises(IngestError, match="model was not found"):
        adapter.detect(_write_wav(tmp_path / "audio.wav"))


def test_silero_requires_onnxruntime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    adapter = SileroVadAdapter(model=model)

    with pytest.raises(IngestError, match="requires onnxruntime"):
        adapter.detect(_write_wav(tmp_path / "audio.wav"))


def test_silero_loads_a_valid_model_and_detects_speech(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_ort(_ort_session([0.1, 0.8, 0.1])))
    adapter = SileroVadAdapter(
        model=model,
        min_silence_ms=0,
        min_speech_ms=0,
        threads=3,
    )

    spans = adapter.detect(_write_wav(tmp_path / "audio.wav", seconds=0.096))

    assert spans == [(WINDOW_SAMPLES, 2 * WINDOW_SAMPLES)]
    assert adapter._session is not None  # noqa: SLF001


def test_silero_rejects_an_incompatible_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    monkeypatch.setitem(
        sys.modules,
        "onnxruntime",
        _fake_ort(_ort_session([0.9], inputs=("input", "state"))),
    )
    adapter = SileroVadAdapter(model=model)

    with pytest.raises(IngestError, match="incompatible"):
        adapter.detect(_write_wav(tmp_path / "audio.wav"))


def test_silero_reports_model_load_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")

    def factory(*args: object, **kwargs: object) -> object:
        raise RuntimeError("bad onnx")

    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_ort(factory))
    adapter = SileroVadAdapter(model=model)

    with pytest.raises(IngestError, match="Cannot load Silero VAD model"):
        adapter.detect(_write_wav(tmp_path / "audio.wav"))


def test_silero_returns_no_spans_when_every_window_is_silent(tmp_path: Path) -> None:
    session = _SileroSession([0.1, 0.1, 0.1])
    adapter = SileroVadAdapter(model=tmp_path / "model.onnx")
    adapter._session = session  # noqa: SLF001

    assert adapter.detect(_write_wav(tmp_path / "audio.wav", seconds=0.096)) == []


def test_silero_pads_the_final_partial_window(tmp_path: Path) -> None:
    probabilities = [0.0, 0.9, 0.9, 0.9]
    session = _SileroSession(probabilities)
    adapter = SileroVadAdapter(
        model=tmp_path / "model.onnx",
        min_silence_ms=0,
        min_speech_ms=0,
    )
    adapter._session = session  # noqa: SLF001

    spans = adapter.detect(_write_wav(tmp_path / "audio.wav", seconds=0.1))

    assert spans == [(WINDOW_SAMPLES, 1600)]
    assert session.calls == 4


def test_silero_rejects_the_wrong_sample_rate(tmp_path: Path) -> None:
    adapter = SileroVadAdapter(model=tmp_path / "model.onnx")

    with pytest.raises(IngestError, match="needs 16000 Hz audio, got 8000 Hz"):
        adapter.detect(_write_wav(tmp_path / "audio.wav", rate=8000))


def test_silero_default_model_uses_runtime_lookup_or_a_relative_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(silero_module, "find_silero_model", lambda: None)
    assert SileroVadAdapter().model == Path("silero_vad.onnx")

    found = tmp_path / "silero_vad.onnx"
    found.write_bytes(b"model")
    monkeypatch.setattr(silero_module, "find_silero_model", lambda: found)
    assert SileroVadAdapter().model == found


def test_silero_filters_short_spans_and_merges_nearby_windows(tmp_path: Path) -> None:
    probabilities = [0.0] * 20
    for index in list(range(0, 5)) + list(range(10, 15)):
        probabilities[index] = 0.9
    session = _SileroSession(probabilities)
    adapter = SileroVadAdapter(
        model=tmp_path / "model.onnx",
        min_silence_ms=100,
        min_speech_ms=100,
    )
    adapter._session = session  # noqa: SLF001

    spans = adapter.detect(_write_wav(tmp_path / "audio.wav", seconds=0.64))

    assert spans == [(0, 5 * WINDOW_SAMPLES), (10 * WINDOW_SAMPLES, 15 * WINDOW_SAMPLES)]

    short_session = _SileroSession([0.9, 0.0, 0.0, 0.0])
    short_adapter = SileroVadAdapter(
        model=tmp_path / "model.onnx",
        min_silence_ms=100,
        min_speech_ms=100,
    )
    short_adapter._session = short_session  # noqa: SLF001

    assert short_adapter.detect(_write_wav(tmp_path / "short.wav", seconds=0.128)) == []


# --------------------------------------------------------------------------- tracking


def _motion_frames(side: str = "left") -> np.ndarray:
    frames = np.zeros((2, 36, 64), dtype=np.uint8)
    if side == "left":
        frames[1, :, 0:2] = 255
    elif side == "right":
        frames[1, :, 62:64] = 255
    return frames


def test_focus_x_from_frames_guards_and_clamps() -> None:
    assert tracking.focus_x_from_frames(np.zeros((36, 64), dtype=np.uint8)) == 0.5
    assert tracking.focus_x_from_frames(np.zeros((1, 36, 64), dtype=np.uint8)) == 0.5
    assert tracking.focus_x_from_frames(np.zeros((2, 36, 64), dtype=np.uint8)) == 0.5
    assert tracking.focus_x_from_frames(_motion_frames("left")) == 0.05
    assert tracking.focus_x_from_frames(_motion_frames("right")) == 0.95


def test_track_focus_x_returns_motion_for_the_default_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tracking, "frames_from_pieces", lambda *args, **kwargs: _motion_frames())

    assert tracking.track_focus_x(tmp_path / "source.mp4", [(0, 16000)], 16000) == (
        0.05,
        "motion_tracking",
    )
    assert tracking.track_focus_x(
        tmp_path / "source.mp4", [(0, 16000)], 16000, mode="center_crop_9_16"
    ) == (0.05, "motion_tracking")


def test_track_focus_x_uses_face_tracking_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tracking, "frames_from_pieces", lambda *args, **kwargs: _motion_frames())
    monkeypatch.setattr(tracking, "_face_centers", lambda frames: [0.42] * len(frames))

    assert tracking.track_focus_x(
        tmp_path / "source.mp4",
        [(0, 16000)],
        16000,
        mode="face_tracking",
        backend="opencv_haar",
    ) == (0.42, "face_tracking")


def test_track_focus_x_falls_back_when_faces_are_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tracking, "frames_from_pieces", lambda *args, **kwargs: _motion_frames())
    monkeypatch.setattr(tracking, "_face_focus", lambda frames: None)

    assert tracking.track_focus_x(
        tmp_path / "source.mp4", [(0, 16000)], 16000, mode="face_tracking"
    ) == (0.05, "motion_tracking")

    def no_cv2(frames: np.ndarray) -> float | None:
        raise ImportError("cv2 is missing")

    monkeypatch.setattr(tracking, "_face_focus", no_cv2)

    assert tracking.track_focus_x(
        tmp_path / "source.mp4", [(0, 16000)], 16000, mode="face_tracking"
    ) == (0.05, "motion_tracking")


def test_frames_from_pieces_requires_ffmpeg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tracking, "find_binary", lambda name: None)

    with pytest.raises(IngestError, match="FFmpeg is not available"):
        tracking.frames_from_pieces(tmp_path / "source.mp4", [(0, 16000)], 16000)


def test_frames_from_pieces_skips_invalid_pieces_and_failed_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []
    frame = b"\x10" * (64 * 36 * 2)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        duration = command[command.index("-t") + 1]
        if duration == "0.500000":
            return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"failed")
        return subprocess.CompletedProcess(command, 0, stdout=frame, stderr=b"")

    monkeypatch.setattr(tracking, "find_binary", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(tracking.subprocess, "run", fake_run)

    frames = tracking.frames_from_pieces(
        tmp_path / "source.mp4",
        [(0, 16000), (16000, 24000), (24000, 24000)],
        16000,
    )

    assert frames.shape == (2, 36, 64)
    assert len(commands) == 2
    assert commands[0][commands[0].index("-ss") + 1] == "0.000000"
    assert commands[0][commands[0].index("-t") + 1] == "1.000000"
    assert "fps=2,scale=64:36,format=gray" in commands[0]


def test_frames_from_pieces_returns_empty_frames_when_nothing_decodes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tracking, "find_binary", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        tracking.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b""),
    )

    frames = tracking.frames_from_pieces(tmp_path / "source.mp4", [(0, 16000)], 16000)

    assert frames.shape == (0, 36, 64)
    assert frames.dtype == np.uint8

    monkeypatch.setattr(
        tracking.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout=b"x", stderr=b""),
    )
    short = tracking.frames_from_pieces(tmp_path / "source.mp4", [(0, 16000)], 16000)
    assert short.shape == (0, 36, 64)


@pytest.mark.parametrize(
    "error",
    [OSError("ffmpeg vanished"), subprocess.TimeoutExpired(["ffmpeg"], 120)],
)
def test_frames_from_pieces_maps_process_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: Exception
) -> None:
    def fail(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise error

    monkeypatch.setattr(tracking, "find_binary", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(tracking.subprocess, "run", fail)

    with pytest.raises(IngestError, match="Motion tracking failed"):
        tracking.frames_from_pieces(tmp_path / "source.mp4", [(0, 16000)], 16000)


def test_face_focus_returns_none_without_frames() -> None:
    assert tracking._face_focus(np.empty((0, 36, 64), dtype=np.uint8)) is None  # noqa: SLF001


def test_face_focus_requires_opencv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "cv2", None)

    with pytest.raises(ImportError):
        tracking._face_focus(_motion_frames())  # noqa: SLF001


def _install_fake_cv2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, faces: list[tuple[int, int, int, int]]
) -> list[str]:
    detector_paths: list[str] = []

    class Detector:
        def __init__(self, path: str) -> None:
            detector_paths.append(path)

        def detectMultiScale(
            self, frame: np.ndarray, scaleFactor: float, minNeighbors: int
        ) -> list[tuple[int, int, int, int]]:
            return faces

    fake = _fake_module(
        "cv2",
        data=SimpleNamespace(haarcascades=str(tmp_path)),
        CascadeClassifier=Detector,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake)
    return detector_paths


def test_face_focus_averages_face_centers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    paths = _install_fake_cv2(monkeypatch, tmp_path, [(10, 5, 20, 10)])

    assert tracking._face_focus(_motion_frames()) == pytest.approx(0.3125)  # noqa: SLF001
    assert paths == [str(tmp_path / "haarcascade_frontalface_default.xml")]


def test_face_focus_returns_none_when_no_faces_are_detected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_cv2(monkeypatch, tmp_path, [])

    assert tracking._face_focus(_motion_frames()) is None  # noqa: SLF001


# --------------------------------------------------------------------------- caption AI


class _FakeLlm:
    instances: list[_FakeLlm] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.prompts: list[str] = []
        _FakeLlm.instances.append(self)

    def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
        self.prompts.append(prompt)
        assert schema_name == "emoji_map"
        return {"emojis": {"fire": "🔥", "ok": "✅"}}


def _write_project(output: Path, sentences: list[tuple[int, int, str]]) -> ProjectState:
    state = ProjectState(
        transcript=[
            Sentence(id=index, start_sample=start, end_sample=end, text=text)
            for index, (start, end, text) in enumerate(sentences)
        ]
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "project_state.json").write_text(state.model_dump_json(), encoding="utf-8")
    return state


def test_generate_emoji_map_cleans_filters_and_caps_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeLlm.instances = []

    class RawLlm(_FakeLlm):
        def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
            self.prompts.append(prompt)
            raw: dict[object, object] = {
                " fire ": " 🔥 ",
                1: "🔥",
                "bad-value": 7,
                "too-long": "123456789",
                "empty": "   ",
                "ok": "✅",
            }
            raw.update({f"word{index}": "✨" for index in range(15)})
            return {"emojis": raw}

    monkeypatch.setattr(caption_ai, "OpenAICompatibleLlm", RawLlm)

    result = generate_emoji_map(
        "x" * 7000,
        base_url="http://127.0.0.1:9/v1",
        model="emoji-model",
        api_key=None,
        allow_external_services=False,
    )

    assert result["fire"] == "🔥"
    assert result["ok"] == "✅"
    assert "bad-value" not in result
    assert "too-long" not in result
    assert "empty" not in result
    assert len(result) == 12
    instance = _FakeLlm.instances[-1]
    assert instance.kwargs == {
        "base_url": "http://127.0.0.1:9/v1",
        "model": "emoji-model",
        "api_key": None,
    }
    assert "x" * 6000 in instance.prompts[0]
    assert "x" * 6001 not in instance.prompts[0]


def test_generate_emoji_map_validates_the_llm_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ListPayload(_FakeLlm):
        def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
            return {"emojis": ["🔥"]}

    monkeypatch.setattr(caption_ai, "OpenAICompatibleLlm", ListPayload)
    with pytest.raises(ShortEditError, match="did not return an emoji map"):
        generate_emoji_map(
            "text",
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )

    class EmptyPayload(_FakeLlm):
        def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
            return {"emojis": {}}

    monkeypatch.setattr(caption_ai, "OpenAICompatibleLlm", EmptyPayload)
    with pytest.raises(ShortEditError, match="empty emoji map"):
        generate_emoji_map(
            "text",
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )


def test_generate_emoji_map_requires_transcript_text() -> None:
    with pytest.raises(ShortEditError, match="no transcript text"):
        generate_emoji_map(
            "   ",
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )


@pytest.mark.parametrize(
    ("allow", "hosts"),
    [(False, ()), (True, ("other.example.com",))],
)
def test_generate_emoji_map_enforces_external_access(
    monkeypatch: pytest.MonkeyPatch,
    allow: bool,
    hosts: tuple[str, ...],
) -> None:
    monkeypatch.delenv("VIDEOWFLOW_ALLOW_EXTERNAL", raising=False)

    with pytest.raises(CapabilityUnavailableError):
        generate_emoji_map(
            "text",
            base_url="https://api.example.com/v1",
            model="model",
            api_key=None,
            allow_external_services=allow,
            allowed_external_hosts=hosts,
        )


def test_apply_llm_emoji_builds_text_from_overlapping_sentences(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "output"
    _write_project(output, [(0, 100, "First"), (100, 200, "Second"), (200, 300, "Third")])
    (output / "shorts.json").write_text(
        json.dumps({"clips": [{"pieces": [[90, 200]]}]}), encoding="utf-8"
    )
    captured: dict[str, object] = {}

    def fake_emoji_map(text: str, **kwargs: object) -> dict[str, str]:
        captured["text"] = text
        captured["kwargs"] = kwargs
        return {"First": "🔥"}

    def fake_edit_short(**kwargs: object) -> dict[str, object]:
        captured["edit"] = kwargs
        return {"index": 0, "path": "/tmp/short.mp4"}

    monkeypatch.setattr(caption_ai, "generate_emoji_map", fake_emoji_map)
    monkeypatch.setattr(caption_ai, "edit_short", fake_edit_short)
    result = {"shorts": [{"path": "/tmp/short.mp4"}]}

    updated = apply_llm_emoji(
        source=tmp_path / "source.mp4",
        output=output,
        index=0,
        result=result,
        base_url="http://127.0.0.1:9/v1",
        model="model",
        api_key="key",
        allow_external_services=False,
    )

    assert captured["text"] == "First Second"
    assert captured["kwargs"] == {
        "base_url": "http://127.0.0.1:9/v1",
        "model": "model",
        "api_key": "key",
        "allow_external_services": False,
        "allowed_external_hosts": (),
    }
    edit = captured["edit"]
    assert edit["source"] == tmp_path / "source.mp4"
    assert edit["index"] == 0
    assert edit["result"] is result
    assert edit["options"].caption_style == {
        "emoji_enabled": True,
        "emoji_map": {"First": "🔥"},
    }
    assert updated == {
        "emoji_map": {"First": "🔥"},
        "short": {"index": 0, "path": "/tmp/short.mp4", "emoji_map": {"First": "🔥"}},
    }


def test_apply_llm_emoji_handles_empty_pieces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "output"
    _write_project(output, [(0, 100, "First")])
    (output / "shorts.json").write_text(json.dumps({"clips": [{}]}), encoding="utf-8")
    seen: dict[str, str] = {}

    def fake_emoji_map(text: str, **kwargs: object) -> dict[str, str]:
        seen["text"] = text
        return {"x": "✨"}

    monkeypatch.setattr(caption_ai, "generate_emoji_map", fake_emoji_map)
    monkeypatch.setattr(
        caption_ai, "edit_short", lambda **kwargs: {"index": 0, "path": "/tmp/short.mp4"}
    )

    updated = apply_llm_emoji(
        source=tmp_path / "source.mp4",
        output=output,
        index=0,
        result={},
        base_url="http://127.0.0.1:9/v1",
        model="model",
        api_key=None,
        allow_external_services=False,
    )

    assert seen["text"] == ""
    assert updated["emoji_map"] == {"x": "✨"}


def test_apply_llm_emoji_requires_a_completed_project(tmp_path: Path) -> None:
    with pytest.raises(StateNotReadyError, match="Cannot read the completed Shorts project"):
        apply_llm_emoji(
            source=tmp_path / "source.mp4",
            output=tmp_path / "output",
            index=0,
            result={},
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )


@pytest.mark.parametrize(
    "clips",
    [None, "not-a-list", [{"pieces": []}, {"pieces": []}]],
)
def test_apply_llm_emoji_validates_the_short_index(tmp_path: Path, clips: object) -> None:
    output = tmp_path / "output"
    _write_project(output, [(0, 100, "First")])
    report = {"clips": clips} if clips is not None else {}
    (output / "shorts.json").write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ShortEditError, match="out of range"):
        apply_llm_emoji(
            source=tmp_path / "source.mp4",
            output=output,
            index=2,
            result={},
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )


def test_apply_llm_emoji_rejects_an_invalid_short_entry(tmp_path: Path) -> None:
    output = tmp_path / "output"
    _write_project(output, [(0, 100, "First")])
    (output / "shorts.json").write_text(json.dumps({"clips": ["bad"]}), encoding="utf-8")

    with pytest.raises(ShortEditError, match="index 0 is invalid"):
        apply_llm_emoji(
            source=tmp_path / "source.mp4",
            output=output,
            index=0,
            result={},
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )


@pytest.mark.parametrize("pieces", [[[1]], [[1, "x"]], "bad"])
def test_apply_llm_emoji_rejects_invalid_pieces(tmp_path: Path, pieces: object) -> None:
    output = tmp_path / "output"
    _write_project(output, [(0, 100, "First")])
    (output / "shorts.json").write_text(
        json.dumps({"clips": [{"pieces": pieces}]}), encoding="utf-8"
    )

    with pytest.raises(ShortEditError, match="pieces are invalid"):
        apply_llm_emoji(
            source=tmp_path / "source.mp4",
            output=output,
            index=0,
            result={},
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )


# --------------------------------------------------------------------------- multimodal LLM


@pytest.mark.parametrize(
    ("binary", "ffprobe"),
    [(None, "/usr/bin/ffprobe"), ("/usr/bin/ffmpeg", None), (None, None)],
)
def test_sample_frames_requires_ffmpeg_and_ffprobe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    binary: str | None,
    ffprobe: str | None,
) -> None:
    monkeypatch.setattr(
        mm_module,
        "find_binary",
        lambda name: binary if name == "ffmpeg" else ffprobe,
    )

    with pytest.raises(IngestError, match="FFmpeg/FFprobe are not available"):
        sample_frames(tmp_path / "short.mp4")


def test_sample_frames_uses_duration_and_keeps_successful_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[0] == "/usr/bin/ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout="30.0\n", stderr="")
        timestamp = command[command.index("-ss") + 1]
        if timestamp == "15.000":
            return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"bad")
        return subprocess.CompletedProcess(command, 0, stdout=b"jpeg", stderr="")

    monkeypatch.setattr(
        mm_module,
        "find_binary",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(mm_module.subprocess, "run", fake_run)

    frames = sample_frames(tmp_path / "short.mp4", count=3, width=320)

    assert frames == [b"jpeg", b"jpeg"]
    assert len(commands) == 4
    assert commands[0][0] == "/usr/bin/ffprobe"
    timestamps = [
        command[command.index("-ss") + 1] for command in commands if command[0] == "/usr/bin/ffmpeg"
    ]
    assert timestamps == ["7.500", "15.000", "22.500"]
    assert "scale=320:-1" in commands[1]


def test_sample_frames_rejects_an_unreadable_duration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        mm_module,
        "find_binary",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(
        mm_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="not-a-number\n", stderr=""
        ),
    )

    with pytest.raises(IngestError, match="Cannot read Short duration"):
        sample_frames(tmp_path / "short.mp4")


def test_sample_frames_requires_at_least_one_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        mm_module,
        "find_binary",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else "/usr/bin/ffprobe",
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "/usr/bin/ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout="10\n", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"bad")

    monkeypatch.setattr(mm_module.subprocess, "run", fake_run)

    with pytest.raises(IngestError, match="No frames could be sampled"):
        sample_frames(tmp_path / "short.mp4")


def test_analyze_short_llm_entry_validates_the_index_and_asset() -> None:
    with pytest.raises(ShortEditError, match="out of range"):
        analyze_short_llm_entry(
            output=Path("."),
            index=0,
            result={"shorts": []},
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )

    with pytest.raises(ShortEditError, match="asset is missing"):
        analyze_short_llm_entry(
            output=Path("."),
            index=0,
            result={"shorts": [{"path": ""}]},
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )

    with pytest.raises(ShortEditError, match="asset is missing"):
        analyze_short_llm_entry(
            output=Path("."),
            index=0,
            result={"shorts": ["bad"]},
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )


def test_analyze_short_llm_entry_updates_the_in_memory_and_written_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "shorts.json").write_text(
        json.dumps({"clips": [{"path": "old"}], "extra": True}), encoding="utf-8"
    )
    seen: dict[str, object] = {}

    def fake_analyze(path: Path, **kwargs: object) -> dict[str, object]:
        seen["path"] = path
        seen["kwargs"] = kwargs
        return {"scene": "office"}

    monkeypatch.setattr(mm_module, "analyze_short_llm", fake_analyze)
    result: dict[str, object] = {"shorts": [{"path": str(tmp_path / "short.mp4"), "index": 0}]}

    analysis = analyze_short_llm_entry(
        output=output,
        index=0,
        result=result,
        base_url="http://127.0.0.1:9/v1",
        model="vision-model",
        api_key="key",
        allow_external_services=False,
        allowed_external_hosts=("127.0.0.1",),
        max_frames=3,
    )

    assert analysis == {"scene": "office"}
    assert seen["path"] == tmp_path / "short.mp4"
    assert seen["kwargs"] == {
        "base_url": "http://127.0.0.1:9/v1",
        "model": "vision-model",
        "api_key": "key",
        "allow_external_services": False,
        "allowed_external_hosts": ("127.0.0.1",),
        "max_frames": 3,
    }
    entry = result["shorts"][0]  # type: ignore[index]
    assert entry["analysis_llm"] == {"scene": "office"}
    written = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    assert written == {"ok": True, "clips": [entry]}
    assert "extra" not in written


def test_analyze_short_llm_entry_falls_back_to_the_result_shorts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "shorts.json").write_text(json.dumps({"clips": "invalid"}), encoding="utf-8")
    monkeypatch.setattr(mm_module, "analyze_short_llm", lambda path, **kwargs: {"scene": "x"})
    result: dict[str, object] = {"shorts": [{"path": "/tmp/short.mp4"}]}

    analyze_short_llm_entry(
        output=output,
        index=0,
        result=result,
        base_url="http://127.0.0.1:9/v1",
        model="model",
        api_key=None,
        allow_external_services=False,
    )

    written = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    assert written["clips"] == result["shorts"]
    assert written["clips"][0]["analysis_llm"] == {"scene": "x"}


def test_analyze_short_llm_entry_requires_a_readable_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(mm_module, "analyze_short_llm", lambda path, **kwargs: {"scene": "x"})

    with pytest.raises(StateNotReadyError, match="Cannot read Shorts report"):
        analyze_short_llm_entry(
            output=tmp_path / "output",
            index=0,
            result={"shorts": [{"path": "/tmp/short.mp4"}]},
            base_url="http://127.0.0.1:9/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )


def test_analyze_short_llm_enforces_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDEOWFLOW_ALLOW_EXTERNAL", raising=False)

    with pytest.raises(CapabilityUnavailableError):
        analyze_short_llm(
            Path("short.mp4"),
            base_url="https://api.example.com/v1",
            model="model",
            api_key=None,
            allow_external_services=False,
        )

    with pytest.raises(CapabilityUnavailableError):
        analyze_short_llm(
            Path("short.mp4"),
            base_url="https://api.example.com/v1",
            model="model",
            api_key=None,
            allow_external_services=True,
            allowed_external_hosts=("other.example.com",),
        )


@pytest.mark.parametrize(("max_frames", "expected_count"), [(0, 1), (5, 5), (99, 12)])
def test_analyze_short_llm_clamps_frames_and_adds_provenance(
    monkeypatch: pytest.MonkeyPatch,
    max_frames: int,
    expected_count: int,
) -> None:
    calls: list[int] = []
    captured: dict[str, object] = {}

    def fake_sample_frames(path: Path, count: int, width: int = 640) -> list[bytes]:
        calls.append(count)
        return [b"frame-a", b"frame-b"]

    class FakeVision:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def analyze(self, frames: list[bytes], prompt: str) -> dict[str, object]:
            captured["frames"] = frames
            captured["prompt"] = prompt
            return {"scene": "studio"}

    monkeypatch.setattr(mm_module, "sample_frames", fake_sample_frames)
    monkeypatch.setattr(mm_module, "OpenAIVisionClient", FakeVision)

    result = analyze_short_llm(
        Path("short.mp4"),
        base_url="http://127.0.0.1:9/v1",
        model="vision-model",
        api_key="key",
        allow_external_services=False,
        max_frames=max_frames,
    )

    assert calls == [expected_count]
    assert captured["base_url"] == "http://127.0.0.1:9/v1"
    assert captured["model"] == "vision-model"
    assert captured["api_key"] == "key"
    assert captured["frames"] == [b"frame-a", b"frame-b"]
    assert captured["prompt"] == mm_module.PROMPT
    assert result == {
        "scene": "studio",
        "frame_count": 2,
        "provider": "openai_compatible_vision",
        "model": "vision-model",
    }
