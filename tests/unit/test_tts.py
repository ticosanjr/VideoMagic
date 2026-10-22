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


def test_piper_adapter_writes_audio(tmp_path: Path) -> None:
    from videoflow.adapters.tts import PiperTtsAdapter

    binary = tmp_path / "piper"
    binary.write_text(
        "#!/bin/sh\n"
        'out=""\n'
        'while [ $# -gt 0 ]; do\n'
        '  if [ "$1" = "--output_file" ]; then out="$2"; shift 2; else shift; fi\n'
        "done\n"
        "cat >/dev/null\n"
        'printf "RIFF" > "$out"\n',
        encoding="utf-8",
    )
    binary.chmod(0o755)
    target = tmp_path / "voice.wav"
    PiperTtsAdapter(binary=str(binary), model_path=str(tmp_path / "voice.onnx")).synthesize(
        "Hello", target
    )
    assert target.read_bytes() == b"RIFF"
