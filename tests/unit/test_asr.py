from pathlib import Path

import httpx
import pytest

from videoflow.adapters.asr import WhisperHttpAdapter
from videoflow.domain.errors import TranscriptionError


def test_transcribes_verbose_json_segments(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200,
            json={
                "segments": [
                    {
                        "start": 1.0,
                        "end": 2.5,
                        "text": " Hello there. ",
                        "words": [
                            {"word": "Hello", "start": 1.0, "end": 1.4, "probability": 0.9}
                        ],
                    }
                ]
            },
        )

    client = WhisperHttpAdapter(
        base_url="http://asr.local/v1",
        model="whisper-1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    sentences = client.transcribe(wav, 48000)
    assert seen["auth"] == "Bearer secret"
    assert sentences[0].start_sample == 48000
    assert sentences[0].end_sample == 120000
    assert sentences[0].text == "Hello there."
    assert sentences[0].words[0].word == "Hello"


def test_missing_segments_is_rejected(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "no timestamps"})

    client = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(TranscriptionError, match="segments"):
        client.transcribe(wav, 48000)


def test_http_error_does_not_echo_the_key(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = WhisperHttpAdapter(
        base_url="http://asr.local/v1",
        api_key="super-secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(TranscriptionError) as caught:
        client.transcribe(wav, 48000)
    assert "super-secret" not in str(caught.value)


def test_negative_timestamp_is_rejected(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"segments": [{"start": -1, "end": 1, "text": "bad"}]},
        )

    client = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(TranscriptionError, match="negative"):
        client.transcribe(wav, 48000)
