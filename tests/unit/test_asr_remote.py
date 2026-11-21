from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.asr_remote import RemoteAsrClient
from videoflow.domain.errors import TranscriptionError
from videoflow.steps.transcribe import TranscribeParams


class FakeRouter:
    def __init__(self, payload: dict | None = None, *, data: bytes | None = None) -> None:
        self.payload = payload
        self.data = data
        self.calls: list[tuple[str, dict]] = []

    def submit(self, capability: str, body: dict, *, timeout: float) -> dict:
        self.calls.append((capability, body))
        if self.data is not None:
            return {"data": self.data, "execution": {"execution_node": "remote_gpu"}}
        path = Path(body.get("_path", ""))
        if self.payload is not None:
            path = Path(body["_payload_path"])
            path.write_text(json.dumps(self.payload), encoding="utf-8")
        return {
            "path": str(path),
            "execution": {"execution_node": "remote_gpu", "degraded": False},
        }


def test_transcribe_defaults_lock_the_anti_hallucination_profile() -> None:
    options = TranscribeParams()
    assert options.anti_hallucination is True
    assert options.compute_policy == "auto"
    assert options.no_speech_threshold == 0.6
    assert options.compression_ratio_threshold == 2.2
    assert options.repetition_penalty == 1.1


def test_remote_asr_parses_words_and_execution(tmp_path: Path) -> None:
    payload = {
        "language": "pt",
        "language_probability": 0.99,
        "segments": [
            {
                "start": 1.0,
                "end": 2.5,
                "text": "Olá mundo",
                "words": [
                    {"word": "Olá", "start": 1.0, "end": 1.5, "probability": 0.9},
                    {"word": "mundo", "start": 1.6, "end": 2.5, "probability": 0.8},
                ],
            }
        ],
    }
    router = FakeRouter(payload)
    client = RemoteAsrClient(router, language="pt", model="large-v3-turbo")
    # The fake needs a payload path supplied through the body.
    original_submit = router.submit

    def submit(capability: str, body: dict, *, timeout: float) -> dict:
        body["_payload_path"] = str(tmp_path / "transcript.json")
        return original_submit(capability, body, timeout=timeout)

    router.submit = submit  # type: ignore[method-assign]
    sentences = client.transcribe(tmp_path / "audio.wav", 48_000)
    assert len(sentences) == 1
    assert sentences[0].start_sample == 48_000
    assert sentences[0].words[1].word == "mundo"
    assert sentences[0].words[1].end_sample == 120_000
    assert client.last_language == "pt"
    assert client.execution["execution_node"] == "remote_gpu"
    assert router.calls[0][0] == "asr"
    assert router.calls[0][1]["condition_on_previous_text"] is False


def test_remote_asr_rejects_empty_payload(tmp_path: Path) -> None:
    router = FakeRouter({"segments": []})
    original_submit = router.submit

    def submit(capability: str, body: dict, *, timeout: float) -> dict:
        body["_payload_path"] = str(tmp_path / "empty.json")
        return original_submit(capability, body, timeout=timeout)

    router.submit = submit  # type: ignore[method-assign]
    with pytest.raises(TranscriptionError, match="no sentences"):
        RemoteAsrClient(router).transcribe(tmp_path / "audio.wav", 48_000)


def test_remote_asr_retries_without_vad_on_onnx_failure(tmp_path: Path) -> None:
    payload = {
        "language": "pt",
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "ola",
                "words": [
                    {"word": "ola", "start": 0.0, "end": 1.0, "probability": 0.9}
                ],
            }
        ],
    }

    class RetryRouter(FakeRouter):
        def __init__(self) -> None:
            super().__init__(payload)
            self.failed = False

        def submit(self, capability: str, body: dict, *, timeout: float) -> dict:
            if not self.failed:
                self.calls.append((capability, dict(body)))
                self.failed = True
                raise RuntimeError(
                    "module 'onnxruntime' has no attribute 'SessionOptions'"
                )
            body["_payload_path"] = str(tmp_path / "transcript.json")
            return super().submit(capability, body, timeout=timeout)

    router = RetryRouter()
    client = RemoteAsrClient(router, language="pt", vad_filter=True)
    sentences = client.transcribe(tmp_path / "audio.wav", 48_000)
    assert sentences[0].words[0].word == "ola"
    assert router.calls[0][1]["vad_filter"] is True
    assert router.calls[1][1]["vad_filter"] is False
    assert client.execution["vad_fallback"] is True
