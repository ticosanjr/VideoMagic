from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

from videoflow.domain.errors import TranscriptionError
from videoflow.domains.asr.legacy_whisper import WhisperCliAdapter


def _wav(path: Path, rate: int = 16000) -> Path:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\0\0" * rate)
    return path


def _fake_cli(path: Path, *, exit_code: int = 0, body: str = "Hello there.") -> Path:
    path.write_text(
        f"""#!{sys.executable}
import pathlib, sys
args = sys.argv
prefix = pathlib.Path(args[args.index("-of") + 1])
pathlib.Path(str(prefix) + ".args").write_text(" ".join(args))
if {exit_code}:
    print("fake failure", file=sys.stderr)
    raise SystemExit({exit_code})
pathlib.Path(str(prefix) + ".srt").write_text(
    "1\\n00:00:00,500 --> 00:00:01,250\\n{body}\\n"
)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_parses_whisper_srt_and_cleans_up(tmp_path: Path) -> None:
    wav = _wav(tmp_path / "source.wav")
    binary = _fake_cli(tmp_path / "whisper-cli")
    model = tmp_path / "ggml-tiny.bin"
    model.write_bytes(b"model")
    adapter = WhisperCliAdapter(
        binary=binary, model=model, threads=2, word_timestamps=False
    )

    sentences = adapter.transcribe(wav, 48000)

    assert len(sentences) == 1
    assert sentences[0].start_sample == 24000
    assert sentences[0].end_sample == 60000
    assert sentences[0].text == "Hello there."
    assert not list(tmp_path.glob(".whisper-*.srt"))
    recorded = next(tmp_path.glob(".whisper-*.args")).read_text()
    assert "-m" in recorded and str(model) in recorded
    assert "-osrt" in recorded and "-t 2" in recorded


def test_reports_cli_failure_without_leaking_command(tmp_path: Path) -> None:
    wav = _wav(tmp_path / "source.wav")
    binary = _fake_cli(tmp_path / "whisper-cli", exit_code=3)
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")

    with pytest.raises(TranscriptionError, match="fake failure"):
        WhisperCliAdapter(binary=binary, model=model).transcribe(wav, 48000)


def test_requires_16k_audio(tmp_path: Path) -> None:
    wav = _wav(tmp_path / "source.wav", rate=48000)
    binary = _fake_cli(tmp_path / "whisper-cli")
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")

    with pytest.raises(TranscriptionError, match="16 kHz"):
        WhisperCliAdapter(binary=binary, model=model).transcribe(wav, 48000)


def test_missing_binary_and_model_are_explained(tmp_path: Path) -> None:
    wav = _wav(tmp_path / "source.wav")
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    with pytest.raises(TranscriptionError, match="VIDEOWFLOW_WHISPER_BIN"):
        WhisperCliAdapter(binary=tmp_path / "missing", model=model).transcribe(wav, 48000)

    binary = _fake_cli(tmp_path / "whisper-cli")
    with pytest.raises(TranscriptionError, match="VIDEOWFLOW_WHISPER_MODEL"):
        WhisperCliAdapter(binary=binary, model=tmp_path / "missing.bin").transcribe(wav, 48000)


def test_invalid_srt_is_a_transcription_error(tmp_path: Path) -> None:
    wav = _wav(tmp_path / "source.wav")
    binary = _fake_cli(tmp_path / "whisper-cli", body="")
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")

    with pytest.raises(TranscriptionError, match="invalid SRT"):
        WhisperCliAdapter(binary=binary, model=model).transcribe(wav, 48000)


def test_requires_word_json_and_parses_tokens(tmp_path: Path) -> None:
    from videoflow.domains.asr.legacy_whisper import _parse_json_words

    wav = _wav(tmp_path / "source.wav")
    binary = _fake_cli(tmp_path / "whisper-cli")
    model = tmp_path / "ggml-tiny.bin"
    model.write_bytes(b"model")
    adapter = WhisperCliAdapter(
        binary=binary, model=model, threads=6, beam_size=1, word_timestamps=True
    )
    adapter.transcribe(wav, 48000)
    recorded = next(tmp_path.glob(".whisper-*.args")).read_text()
    assert "-ojf" in recorded
    assert "-bs 1" in recorded
    assert "-ng" in recorded

    payload = {
        "transcription": [
            {
                "offsets": {"from": 0, "to": 1200},
                "tokens": [
                    {"text": " Hello", "offsets": {"from": 0, "to": 400}},
                    {"text": " there", "offsets": {"from": 400, "to": 800}},
                    {"text": ".", "offsets": {"from": 800, "to": 800}},
                    {"text": "<|endoftext|>", "offsets": {"from": 0, "to": 0}},
                    {"text": " Next", "offsets": {"from": 900, "to": 1200}},
                ],
            }
        ]
    }
    import json

    sentences = _parse_json_words(json.dumps(payload), 1000)
    assert sentences[0].text == "Hello there."
    assert sentences[0].words[0].word == "Hello"
    assert sentences[0].words[0].start_sample == 0
    assert sentences[1].text == "Next"


def test_json_word_parser_rejects_empty_payload() -> None:
    from videoflow.domains.asr.legacy_whisper import _parse_json_words

    with pytest.raises(ValueError, match="no usable words"):
        _parse_json_words('{"transcription": []}', 16000)
    with pytest.raises(ValueError, match="no usable words"):
        _parse_json_words(
            '{"transcription": [1, {"tokens": [2, {"text": "<|end|>"}]}]}',
            16000,
        )
