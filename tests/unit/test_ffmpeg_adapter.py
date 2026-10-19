import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.domain.errors import IngestError


def probe_payload(
    *,
    fps: str = "30000/1001",
    nb_frames: str | None = "21614",
    duration: str = "720.72",
    audio: bool = True,
) -> dict[str, Any]:
    streams: list[dict[str, Any]] = [
        {
            "codec_type": "video",
            "width": 3840,
            "height": 2160,
            "r_frame_rate": fps,
            "avg_frame_rate": fps,
            "nb_frames": nb_frames,
            "duration": duration,
            "disposition": {"attached_pic": 0},
        }
    ]
    if audio:
        streams.append({"codec_type": "audio", "sample_rate": "48000"})
    return {"streams": streams, "format": {"duration": duration}}


def test_probe_uses_rational_ntsc_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"not a real video")
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_run", lambda _args: json.dumps(probe_payload()))
    info = adapter.probe(source)
    assert (info.fps_num, info.fps_den) == (30000, 1001)
    assert info.duration_frames == 21614
    assert info.audio_sample_rate == 48000
    assert info.source_path == str(source.resolve())


def test_probe_computes_frames_when_nb_frames_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")
    adapter = FFmpegAdapter()
    monkeypatch.setattr(
        adapter,
        "_run",
        lambda _args: json.dumps(probe_payload(fps="30/1", nb_frames=None, duration="10.0")),
    )
    assert adapter.probe(source).duration_frames == 300


def test_probe_rejects_missing_audio_and_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_run", lambda _args: json.dumps(probe_payload(audio=False)))
    with pytest.raises(IngestError, match="audio"):
        adapter.probe(source)


def test_probe_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="does not exist"):
        FFmpegAdapter().probe(tmp_path / "missing.mp4")


def test_probe_rejects_a_bad_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")
    adapter = FFmpegAdapter()
    payload = probe_payload(fps="0/0")
    monkeypatch.setattr(adapter, "_run", lambda _args: json.dumps(payload))
    with pytest.raises(IngestError, match="frame rate"):
        adapter.probe(source)


def test_extract_pcm_writes_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")
    target = tmp_path / "work" / "source.wav"
    seen: list[list[str]] = []

    def fake_run(args: list[str]) -> str:
        seen.append(args)
        Path(args[-1]).write_bytes(b"RIFF")
        return ""

    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_run", fake_run)
    result = adapter.extract_pcm(source, target)
    assert result == target
    assert target.read_bytes() == b"RIFF"
    assert "pcm_s16le" in seen[0]
    assert "16000" in seen[0]


def test_pcm_digest_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "source.wav"
    path.write_bytes(b"abc")
    adapter = FFmpegAdapter()
    assert adapter.pcm_digest(path) == adapter.pcm_digest(path)
    assert len(adapter.pcm_digest(path)) == 64


def test_run_reports_a_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("videoflow.adapters.ffmpeg.find_binary", lambda _name: None)
    with pytest.raises(IngestError, match="not available"):
        FFmpegAdapter()._run(["ffprobe", "-version"])


def test_run_reports_a_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="bad input\n"),
    )
    with pytest.raises(IngestError, match="bad input"):
        FFmpegAdapter()._run(["ffprobe", "-version"])


def test_run_rejects_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_run", lambda _args: "not-json")
    with pytest.raises(IngestError, match="invalid JSON"):
        adapter.probe(source)


def test_probe_requires_a_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")
    adapter = FFmpegAdapter()
    payload = probe_payload(nb_frames=None)
    payload["format"] = {}
    payload["streams"][0]["duration"] = "N/A"
    monkeypatch.setattr(adapter, "_run", lambda _args: json.dumps(payload))
    with pytest.raises(IngestError, match="duration"):
        adapter.probe(source)
