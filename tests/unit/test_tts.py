from pathlib import Path

import httpx

from videoflow.adapters.tts import OpenAITtsAdapter


def test_tts_sends_text_and_writes_audio(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200, content=b"ID3audio")

    adapter = OpenAITtsAdapter(
        base_url="http://tts.local/v1",
        model="tts-1",
        voice="alloy",
        transport=httpx.MockTransport(handler),
    )
    target = tmp_path / "voice.mp3"
    result = adapter.synthesize("Hello world", target, speed=1.2)
    assert result == target
    assert target.read_bytes() == b"ID3audio"
    assert str(seen["url"]).endswith("/audio/speech")
    assert b"Hello world" in seen["body"]  # type: ignore[operator]
