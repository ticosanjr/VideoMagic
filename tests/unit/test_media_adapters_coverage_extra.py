"""Hermetic coverage for the media adapters.

Every subprocess, HTTP transport, and optional native module is faked. The
tests assert the exact FFmpeg commands where they are the contract and the
parsed results or typed errors everywhere else.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import httpx
import pytest

from videoflow.adapters import ffmpeg as ffmpeg_module
from videoflow.adapters import tts as tts_module
from videoflow.adapters import whisper as whisper_module
from videoflow.adapters.asr import WhisperHttpAdapter
from videoflow.adapters.diarization import (
    PyannoteDiarizer,
    SpeakerTurn,
    assign_speakers,
)
from videoflow.adapters.ffmpeg import (
    FFmpegAdapter,
    _complement,
    _filter_path,
    parse_silence,
)
from videoflow.adapters.tts import OpenAITtsAdapter, PiperTtsAdapter
from videoflow.adapters.whisper import WhisperCliAdapter
from videoflow.domain.errors import (
    CapabilityUnavailableError,
    IngestError,
    JobCancelledError,
    TranscriptionError,
    TtsError,
)
from videoflow.domain.state import Sentence

# --------------------------------------------------------------------------- #
# Shared fakes
# --------------------------------------------------------------------------- #


class _FakeProcess:
    """Stand-in for ``subprocess.Popen`` used by ``_capture`` and ``render``."""

    def __init__(
        self,
        *,
        returncode: int | None = 0,
        stdout: str = "",
        stderr: str = "",
        communicate_error: Exception | None = None,
        wait_timeouts: int = 0,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.pid = 424242
        self.terminated = False
        self.killed = False
        self.wait_timeouts = wait_timeouts
        self.communicate_error = communicate_error

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        if self.communicate_error is not None:
            raise self.communicate_error
        return self.stdout, self.stderr

    def wait(self, timeout: float | None = None) -> int:
        if self.wait_timeouts > 0:
            self.wait_timeouts -= 1
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout or 0)
        return self.returncode or 0

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class _ProgressProcess:
    """Process double that yields progress lines and poll results in order."""

    def __init__(
        self,
        lines: list[str],
        polls: list[int | None],
        *,
        returncode: int = 0,
    ) -> None:
        self.stdout = iter(lines)
        self.stderr = None
        self.pid = 5150
        self.returncode = returncode
        self._polls = list(polls)
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        if self._polls:
            return self._polls.pop(0)
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def _patch_process_group(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    seen: list[tuple[str, int]] = []

    def fake_getpgid(_pid: int) -> int:
        return 999

    def fake_killpg(_pgid: int, signal_number: int) -> None:
        seen.append(("killpg", signal_number))

    monkeypatch.setattr(ffmpeg_module.os, "getpgid", fake_getpgid)
    monkeypatch.setattr(ffmpeg_module.os, "killpg", fake_killpg)
    return seen


def _record_capture(
    commands: list[list[str]],
) -> Any:
    """Return a ``_capture`` replacement that creates each output file."""

    def fake(args: list[str], *, timeout: int = 0) -> tuple[str, str]:
        commands.append(list(args))
        output = Path(args[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"rendered")
        return "", ""

    return fake


def _probe_streams(
    *,
    video: bool = True,
    audio: bool = True,
    fps: str = "30000/1001",
    nb_frames: str | None = "100",
    duration: str = "10.0",
) -> dict[str, Any]:
    streams: list[dict[str, Any]] = [
        {
            "codec_type": "video",
            "disposition": {"attached_pic": 1},
            "width": 32,
            "height": 32,
        }
    ]
    if video:
        streams.append(
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": fps,
                "avg_frame_rate": fps,
                "nb_frames": nb_frames,
                "duration": duration,
                "disposition": {"attached_pic": 0},
            }
        )
    if audio:
        streams.append({"codec_type": "audio", "sample_rate": "48000"})
    return {"streams": streams, "format": {"duration": duration}}


def _probe(monkeypatch: pytest.MonkeyPatch, payload: object) -> FFmpegAdapter:
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_run", lambda _args: json.dumps(payload))
    return adapter


def _wav16k(path: Path) -> Path:
    return _wav_at(path, 16000)


def _wav_at(path: Path, rate: int) -> Path:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\0\0" * 16)
    return path


# --------------------------------------------------------------------------- #
# ffmpeg: probe and JSON handling
# --------------------------------------------------------------------------- #


def test_probe_parses_video_skipping_attached_pictures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    adapter = _probe(monkeypatch, _probe_streams())
    info = adapter.probe(source)
    assert (info.fps_num, info.fps_den) == (30000, 1001)
    assert info.duration_frames == 100
    assert (info.width, info.height, info.audio_sample_rate) == (1920, 1080, 48000)
    assert info.source_path == str(source.resolve())


def test_probe_falls_back_to_avg_frame_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    payload = _probe_streams(nb_frames=None, duration="10.0")
    video = payload["streams"][1]
    video["r_frame_rate"] = 30
    video["avg_frame_rate"] = "24/1"
    assert _probe(monkeypatch, payload).probe(source).duration_frames == 240


def test_probe_uses_format_duration_when_stream_duration_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    payload = _probe_streams(nb_frames="0", duration="10.0")
    payload["streams"][1]["duration"] = None
    assert _probe(monkeypatch, payload).probe(source).duration_frames == 300


def test_probe_rejects_a_missing_video_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    with pytest.raises(IngestError, match="no video stream"):
        _probe(monkeypatch, _probe_streams(video=False)).probe(source)


def test_probe_rejects_a_missing_audio_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    with pytest.raises(IngestError, match="no audio stream"):
        _probe(monkeypatch, _probe_streams(audio=False)).probe(source)


def test_probe_rejects_unusable_frame_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    payload = _probe_streams()
    payload["streams"][1]["r_frame_rate"] = "30000"
    payload["streams"][1]["avg_frame_rate"] = "bad/rate"
    with pytest.raises(IngestError, match="frame rate"):
        _probe(monkeypatch, payload).probe(source)


def test_probe_rejects_non_numeric_and_zero_dimensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    payload = _probe_streams()
    payload["streams"][1]["width"] = "wide"
    with pytest.raises(IngestError, match="did not report width"):
        _probe(monkeypatch, payload).probe(source)

    payload = _probe_streams()
    payload["streams"][1]["height"] = "0"
    with pytest.raises(IngestError, match="invalid height"):
        _probe(monkeypatch, payload).probe(source)

    payload = _probe_streams()
    payload["streams"][2]["sample_rate"] = None
    with pytest.raises(IngestError, match="did not report sample_rate"):
        _probe(monkeypatch, payload).probe(source)


def test_probe_rejects_an_invalid_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    payload = _probe_streams(nb_frames=None, duration="not-a-duration")
    with pytest.raises(IngestError, match="invalid duration"):
        _probe(monkeypatch, payload).probe(source)


def test_probe_rejects_a_missing_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    payload = _probe_streams(nb_frames=None, duration="N/A")
    payload["format"] = {}
    with pytest.raises(IngestError, match="did not report a duration"):
        _probe(monkeypatch, payload).probe(source)


def test_probe_skips_a_zero_rate_and_uses_the_next_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    payload = _probe_streams(nb_frames=None, duration="10.0")
    payload["streams"][1]["r_frame_rate"] = "0/1"
    payload["streams"][1]["avg_frame_rate"] = "24/1"
    assert _probe(monkeypatch, payload).probe(source).duration_frames == 240


def test_probe_rejects_a_missing_source(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="does not exist"):
        FFmpegAdapter().probe(tmp_path / "missing.mp4")


def test_probe_rejects_non_object_and_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    with pytest.raises(IngestError, match="unexpected payload"):
        _probe(monkeypatch, [1, 2]).probe(source)

    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_run", lambda _args: "not json")
    with pytest.raises(IngestError, match="invalid JSON"):
        adapter.probe(source)


# --------------------------------------------------------------------------- #
# ffmpeg: audio helpers
# --------------------------------------------------------------------------- #


def test_extract_pcm_builds_the_exact_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    target = tmp_path / "work" / "source.wav"
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))

    assert adapter.extract_pcm(source, target) == target
    assert commands[0] == [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        str(tmp_path / "work" / "source.part.wav"),
    ]
    assert target.read_bytes() == b"rendered"


def test_extract_pcm_rejects_a_missing_source(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="does not exist"):
        FFmpegAdapter().extract_pcm(tmp_path / "missing.mp4", tmp_path / "out.wav")


def test_pcm_digest_is_sha256(tmp_path: Path) -> None:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"abcdef")
    digest = FFmpegAdapter().pcm_digest(path)
    assert digest == "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721"


def test_measure_loudness_reads_the_last_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"x")
    stderr = "I: -20.0 LUFS\nPeak: -3.0 dBFS\nI: -14.5 LUFS\nPeak: -1.2 dBFS\n"
    adapter = FFmpegAdapter()
    seen: list[list[str]] = []

    def fake_capture(args: list[str], *, timeout: int = 0) -> tuple[str, str]:
        seen.append(args)
        return "", stderr

    monkeypatch.setattr(adapter, "_capture", fake_capture)
    result = adapter.measure_loudness(source)
    assert result == {"integrated_lufs": -14.5, "true_peak_dbfs": -1.2}
    assert seen[0][:4] == ["ffmpeg", "-hide_banner", "-nostats", "-i"]
    assert "ebur128=peak=true" in seen[0]


def test_measure_loudness_without_peak_and_without_integrated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"x")
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", lambda _args, **_kw: ("", "I: -12.0 LUFS"))
    assert adapter.measure_loudness(source) == {
        "integrated_lufs": -12.0,
        "true_peak_dbfs": 0.0,
    }

    monkeypatch.setattr(adapter, "_capture", lambda _args, **_kw: ("", "no summary"))
    with pytest.raises(IngestError, match="Could not measure loudness"):
        adapter.measure_loudness(source)

    with pytest.raises(IngestError, match="Media does not exist"):
        adapter.measure_loudness(tmp_path / "missing.wav")


def test_master_audio_with_and_without_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))

    filtered = adapter.master_audio(
        source, tmp_path / "out" / "dialogue.wav", filters=["", "loudnorm"], sample_rate=44100
    )
    assert filtered.read_bytes() == b"rendered"
    assert commands[0][commands[0].index("-af") + 1] == "loudnorm"
    assert "44100" in commands[0]

    adapter.master_audio(source, tmp_path / "out" / "plain.wav")
    assert "-af" not in commands[1]

    with pytest.raises(IngestError, match="does not exist"):
        adapter.master_audio(tmp_path / "missing.mp4", tmp_path / "out" / "x.wav")


def test_mix_voiceover_clamps_and_asserts_the_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))
    target = tmp_path / "out" / "mixed.mp4"
    result = adapter.mix_voiceover(
        tmp_path / "short.mp4",
        tmp_path / "voice.wav",
        target,
        duration_sec=0.0,
        voice_volume=-3.0,
        original_volume=9.0,
    )
    assert result == target
    graph = commands[0][commands[0].index("-filter_complex") + 1]
    assert "[0:a]volume=1.0[orig]" in graph
    assert "[1:a]atrim=0:0.010,volume=0.0[vo]" in graph
    assert "amix=inputs=2:duration=first" in graph
    assert commands[0][-1] == str(target)


def test_detect_speech_parses_silence_and_filters_blips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"x")
    stderr = "silence_start: 1.0\nsilence_end: 1.5\nsilence_start: 3.0\nsilence_end: 4.0"
    adapter = FFmpegAdapter()
    seen: list[list[str]] = []

    def fake_capture(args: list[str], *, timeout: int = 0) -> tuple[str, str]:
        seen.append(args)
        return "", stderr

    monkeypatch.setattr(adapter, "_capture", fake_capture)
    spans = adapter.detect_speech(
        wav, duration_samples=6 * 48000, sample_rate=48000, noise_db=-35, min_silence_ms=250
    )
    assert spans == [(0, 48000), (72000, 144000), (192000, 288000)]
    assert "silencedetect=noise=-35dB:d=0.25" in seen[0]

    with pytest.raises(IngestError, match="does not exist"):
        adapter.detect_speech(tmp_path / "missing.wav", duration_samples=1, sample_rate=1)
    with pytest.raises(IngestError, match="must be positive"):
        adapter.detect_speech(wav, duration_samples=0, sample_rate=48000)


# --------------------------------------------------------------------------- #
# ffmpeg: render helper commands
# --------------------------------------------------------------------------- #


def test_transcode_preview_command_and_missing_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))
    target = adapter.transcode_preview(source, tmp_path / "out" / "preview.mp4", width=0)
    assert target.exists()
    assert commands[0][commands[0].index("-vf") + 1] == "scale=2:-2"
    assert commands[0][commands[0].index("-crf") + 1] == "28"
    with pytest.raises(IngestError, match="Preview source does not exist"):
        adapter.transcode_preview(tmp_path / "missing.mp4", tmp_path / "x.mp4")


def test_render_thumbnail_burns_ass_and_clamps_height(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))

    target = adapter.render_thumbnail(
        source,
        tmp_path / "out" / "thumb.png",
        time_sec=1.25,
        ass_path=tmp_path / "subs.ass",
        fontsdir=str(tmp_path / "fonts"),
        height=10,
    )
    assert target.exists()
    assert commands[0][commands[0].index("-ss") + 1] == "1.250000"
    vf = commands[0][commands[0].index("-vf") + 1]
    assert vf.startswith("ass=")
    assert ":fontsdir=" in vf
    assert vf.endswith(",scale=-2:64")
    assert commands[0][-1] == str(target)

    adapter.render_thumbnail(source, tmp_path / "plain.png", time_sec=0)
    assert "-vf" not in commands[1]

    with pytest.raises(IngestError, match="non-negative"):
        adapter.render_thumbnail(source, tmp_path / "bad.png", time_sec=-1)


def test_render_thumbnail_burns_ass_without_fontsdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))
    adapter.render_thumbnail(
        source,
        tmp_path / "thumb.jpg",
        time_sec=0,
        ass_path=tmp_path / "subs.ass",
    )
    vf = commands[0][commands[0].index("-vf") + 1]
    assert vf.startswith("ass=")
    assert ":fontsdir=" not in vf


def test_filter_path_escapes_colons_and_quotes(tmp_path: Path) -> None:
    value = _filter_path(tmp_path / "a:b'c.ass")
    assert value.endswith("a\\:b\\'c.ass")
    assert "\\" in value


def test_parse_silence_skips_empty_spans_and_clips() -> None:
    stderr = "silence_start: 1.0\nsilence_end: 1.0\nsilence_start: 4.0\nsilence_end: 9.0"
    assert parse_silence(stderr, 5 * 48000, 48000) == [(192000, 240000)]


def test_parse_silence_merges_overlapping_spans() -> None:
    stderr = "silence_start: 1.0\nsilence_end: 2.0\nsilence_start: 1.3\nsilence_end: 3.0"
    assert parse_silence(stderr, 4 * 48000, 48000) == [(48000, 144000)]


def test_complement_handles_zero_start_and_full_coverage() -> None:
    assert _complement([(0, 100)], 100) == []
    assert _complement([(0, 10), (20, 30)], 40) == [(10, 20), (30, 40)]


def test_attach_cards_supports_a_single_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    intro = tmp_path / "intro.mp4"
    intro.write_bytes(b"x")
    outro = tmp_path / "outro.mp4"
    outro.write_bytes(b"x")
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))
    work = tmp_path / "work"
    work.mkdir()

    intro_only = adapter._attach_cards(
        source,
        width=1080,
        height=1920,
        intro_path=intro,
        outro_path=None,
        intro_duration=1.5,
        outro_duration=1.5,
        work=work,
    )
    assert intro_only.exists()
    outro_only = adapter._attach_cards(
        source,
        width=1080,
        height=1920,
        intro_path=None,
        outro_path=outro,
        intro_duration=1.5,
        outro_duration=1.5,
        work=work,
    )
    assert outro_only.exists()
    assert "concat=n=2:v=1:a=1[v][a]" in " ".join(commands[0])
    assert "concat=n=2:v=1:a=1[v][a]" in " ".join(commands[1])


# --------------------------------------------------------------------------- #
# ffmpeg: render_short graph construction
# --------------------------------------------------------------------------- #


def test_render_short_single_piece_with_broll_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    broll = tmp_path / "broll.mp4"
    broll.write_bytes(b"x")
    overlay = tmp_path / "logo.png"
    overlay.write_bytes(b"x")
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))

    target = adapter.render_short(
        source,
        [(0, 48000)],
        tmp_path / "out" / "short.mp4",
        sample_rate=48000,
        split_screen=True,
        broll_path=broll,
        broll_start_sec=-1.0,
        broll_duration_sec=0.5,
        overlay_path=overlay,
        overlay_position="somewhere",
    )
    assert target.read_bytes() == b"rendered"
    joined = [" ".join(command) for command in commands]
    split = next(item for item in joined if "[left][right]hstack=inputs=2" in item)
    assert "crop=trunc(iw/(2*1.0)/2)*2" in split
    assert "scale=540:1920" in split
    broll_command = next(item for item in joined if "overlay=0:0:enable='between" in item)
    assert "between(t,0.000000,0.500000)" in broll_command
    overlay_command = next(item for item in joined if "colorchannelmixer" in item)
    assert "W-w-32:H-h-32" in overlay_command


def test_render_short_full_chain_with_split_screen_and_sfx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    second = tmp_path / "second.mp4"
    second.write_bytes(b"x")
    overlay = tmp_path / "logo.png"
    overlay.write_bytes(b"x")
    music = tmp_path / "music.mp3"
    music.write_bytes(b"x")
    broll_one = tmp_path / "broll-one.mp4"
    broll_one.write_bytes(b"x")
    broll_two = tmp_path / "broll-two.mp4"
    broll_two.write_bytes(b"x")
    sfx = tmp_path / "ding.wav"
    sfx.write_bytes(b"x")
    intro = tmp_path / "intro.mp4"
    intro.write_bytes(b"x")
    outro = tmp_path / "outro.mp4"
    outro.write_bytes(b"x")
    commands: list[list[str]] = []
    logs: list[tuple[str, str]] = []
    adapter = FFmpegAdapter(log=lambda level, message: logs.append((level, message)))
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))

    target = adapter.render_short(
        source,
        [(0, 48000), (48000, 96000)],
        tmp_path / "out" / "short.mp4",
        sample_rate=48000,
        ass_path=tmp_path / "subs.ass",
        fontsdir=str(tmp_path / "fonts"),
        audio_filters=["loudnorm"],
        overlay_path=overlay,
        overlay_position="top_left",
        overlay_margin=-4,
        overlay_width_ratio=9.0,
        overlay_opacity=9.0,
        music_path=music,
        music_ducking=False,
        intro_path=intro,
        outro_path=outro,
        split_screen=True,
        split_screen_zoom=9.0,
        split_screen_focus_left=-1.0,
        split_screen_focus_right=2.0,
        second_source_path=second,
        mix_second_audio=True,
        broll_clips=[(broll_one, 0.0, 0.5), (broll_two, 1.0, 0.5)],
        sfx_clips=[(tmp_path / "missing.wav", 0.0, 1.0), (sfx, 0.25, 0.5)],
    )
    assert target.read_bytes() == b"rendered"
    joined = [" ".join(command) for command in commands]
    assert any(" -f concat -safe 0 " in item for item in joined)
    split = next(item for item in joined if "hstack=inputs=2[v]" in item)
    assert "crop=trunc(iw/(2*2.0)/2)*2" in split
    assert "(iw-ow)*0.0" in split
    assert "iw/2+(iw/2-ow)*1.0" in split
    assert "amix=inputs=2:duration=first:dropout_transition=0[a]" in split
    assert any(" -af loudnorm " in item for item in joined)
    broll = next(item for item in joined if "[b1]overlay=0:0" in item)
    assert "between(t,1.000000,1.500000)" in broll
    sfx_command = next(item for item in joined if "adelay=250|250" in item)
    assert "volume=0.500" in sfx_command
    assert "amix=inputs=2:duration=first" in sfx_command
    overlay_command = next(item for item in joined if "colorchannelmixer" in item)
    assert "overlay=0:0:format=auto" in overlay_command
    assert "scale=1080:-1" in overlay_command
    assert "aa=1.0" in overlay_command
    music_command = next(item for item in joined if "[1:a]volume=0.18" in item)
    assert "[0:a][music]amix=inputs=2" in music_command
    assert "concat=n=3:v=1:a=1[v][a]" in " ".join(commands[-1])


def test_render_short_requires_pieces_and_valid_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))
    target = tmp_path / "out" / "short.mp4"

    with pytest.raises(IngestError, match="No pieces"):
        adapter.render_short(source, [], target, sample_rate=48000)

    with pytest.raises(IngestError, match="B-roll asset does not exist"):
        adapter.render_short(
            source,
            [(0, 48000)],
            target,
            sample_rate=48000,
            broll_clips=[(tmp_path / "missing.mp4", 0.0, 1.0)],
        )

    with pytest.raises(IngestError, match="Overlay image does not exist"):
        adapter.render_short(
            source,
            [(0, 48000)],
            target,
            sample_rate=48000,
            overlay_path=tmp_path / "missing.png",
        )

    with pytest.raises(IngestError, match="Music file does not exist"):
        adapter.render_short(
            source,
            [(0, 48000)],
            target,
            sample_rate=48000,
            music_path=tmp_path / "missing.mp3",
        )

    with pytest.raises(IngestError, match="Second split-screen source"):
        adapter.render_short(
            source,
            [(0, 48000)],
            target,
            sample_rate=48000,
            split_screen=True,
            second_source_path=tmp_path / "missing.mp4",
        )


def test_render_short_skips_missing_sfx_and_plain_ass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    commands: list[list[str]] = []
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", _record_capture(commands))
    target = tmp_path / "out" / "short.mp4"

    adapter.render_short(
        source,
        [(0, 48000)],
        target,
        sample_rate=48000,
        sfx_clips=[(tmp_path / "missing.wav", 0.0, 0.5)],
        ass_path=tmp_path / "subs.ass",
    )
    joined = [" ".join(command) for command in commands]
    assert not any("adelay" in item for item in joined)
    ass_command = next(item for item in joined if " -vf ass=" in item)
    assert ":fontsdir=" not in ass_command
    assert "libx264" in ass_command


# --------------------------------------------------------------------------- #
# ffmpeg: render (progress) and subprocess plumbing
# --------------------------------------------------------------------------- #


def test_render_without_progress_uses_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    adapter = FFmpegAdapter()

    def fake_capture(args: list[str], *, timeout: int = 0) -> tuple[str, str]:
        seen.append(args)
        assert timeout == 42
        return "", ""

    monkeypatch.setattr(adapter, "_capture", fake_capture)
    adapter.render(["-i", "in.mp4"], timeout=42)
    assert seen[0] == ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", "in.mp4"]


def test_render_progress_reports_frames_and_ignores_bad_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _ProgressProcess(
        ["frame=12\n", "frame=not-a-number\n", "frame= 30 \n", "progress=end\n"],
        [None, None, None, None, 0],
    )
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    frames: list[int] = []
    FFmpegAdapter().render(["-i", "in.mp4"], progress=frames.append)
    assert frames == [12, 30]


def test_render_progress_drains_remaining_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _ProgressProcess(["frame=1\n", "frame=2\n"], [None, 0])
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    frames: list[int] = []
    FFmpegAdapter().render(["-i", "in.mp4"], progress=frames.append)
    assert frames == [1]


def test_render_progress_keeps_waiting_when_no_line_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _ProgressProcess([], [None, 0])
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    FFmpegAdapter().render(["-i", "in.mp4"], progress=lambda _n: None)


def test_render_progress_requires_ffmpeg_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: None)
    with pytest.raises(IngestError, match="ffmpeg is not available"):
        FFmpegAdapter().render(["-i", "in.mp4"], progress=lambda _n: None)

    process = _ProgressProcess([], [1], returncode=1)
    logs: list[tuple[str, str]] = []
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    adapter = FFmpegAdapter(log=lambda level, message: logs.append((level, message)))
    with pytest.raises(IngestError, match="unknown error") as caught:
        adapter.render(["-i", "in.mp4"], progress=lambda _n: None)
    assert "-progress pipe:1 -nostats" in (caught.value.command or "")
    assert logs == [("error", "ffmpeg failed")]


def test_render_progress_failure_uses_the_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _ProgressProcess(
        ["line one\n", "line two\n", "frame=5\n", "boom\n"],
        [None, None, None, None, 1],
        returncode=1,
    )
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    with pytest.raises(IngestError, match="ffmpeg failed") as caught:
        FFmpegAdapter().render(["-i", "in.mp4"], progress=lambda _n: None)
    assert "boom" in caught.value.stderr


def test_render_progress_timeout_and_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _ProgressProcess([], [None] * 20)
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    signals = _patch_process_group(monkeypatch)
    monkeypatch.setattr(ffmpeg_module.time, "monotonic", iter([0.0, 5000.0]).__next__)

    with pytest.raises(IngestError, match="timed out"):
        FFmpegAdapter().render(["-i", "in.mp4"], timeout=1, progress=lambda _n: None)
    assert signals == [("killpg", ffmpeg_module.signal.SIGTERM)]

    cancel = threading.Event()
    cancel.set()
    process = _ProgressProcess([], [None] * 20)
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(ffmpeg_module.time, "monotonic", iter([0.0]).__next__)
    with pytest.raises(JobCancelledError):
        FFmpegAdapter(cancel_event=cancel).render(
            ["-i", "in.mp4"], progress=lambda _n: None
        )


def test_capture_returns_output_and_emits_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess(stdout="payload", stderr="")
    seen: list[list[str]] = []
    logs: list[tuple[str, str]] = []

    def fake_popen(args: list[str], **kwargs: Any) -> _FakeProcess:
        seen.append(args)
        return process

    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffprobe")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", fake_popen)
    adapter = FFmpegAdapter(log=lambda level, message: logs.append((level, message)))
    assert adapter._capture(["ffprobe", "-version"]) == ("payload", "")
    assert seen[0] == ["/usr/bin/ffprobe", "-version"]
    assert logs == [("debug", "$ ffprobe -version")]


def test_capture_reports_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: None)
    with pytest.raises(IngestError, match="is not available"):
        FFmpegAdapter()._capture(["ffprobe", "-version"])


def test_capture_reports_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess(returncode=1, stderr="first\nsecond\nbad input\n")
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    logs: list[tuple[str, str]] = []
    adapter = FFmpegAdapter(log=lambda level, message: logs.append((level, message)))
    with pytest.raises(IngestError, match="bad input") as caught:
        adapter._capture(["ffmpeg", "-version"])
    assert caught.value.command == "ffmpeg -version"
    assert "bad input" in caught.value.stderr
    assert logs[-1] == ("error", "first\nsecond\nbad input")


def test_capture_timeout_terminates(monkeypatch: pytest.MonkeyPatch) -> None:
    error = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=0.15)
    process = _FakeProcess(returncode=None, communicate_error=error)
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    signals = _patch_process_group(monkeypatch)
    monkeypatch.setattr(ffmpeg_module.time, "monotonic", iter([0.0, 9000.0]).__next__)
    with pytest.raises(IngestError, match="timed out"):
        FFmpegAdapter()._capture(["ffmpeg", "-version"], timeout=1)
    assert signals == [("killpg", ffmpeg_module.signal.SIGTERM)]


def test_capture_short_circuits_when_already_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_popen(args: list[str], **kwargs: Any) -> _FakeProcess:
        calls.append(args)
        return _FakeProcess()

    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", fake_popen)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(JobCancelledError):
        FFmpegAdapter(cancel_event=cancel)._capture(["ffmpeg", "-version"])
    assert calls == []


def test_capture_cancels_during_communicate(monkeypatch: pytest.MonkeyPatch) -> None:
    cancel = threading.Event()
    process = _FakeProcess(returncode=None)
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    signals = _patch_process_group(monkeypatch)

    def communicate(timeout: float | None = None) -> tuple[str, str]:
        cancel.set()
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout or 0)

    monkeypatch.setattr(process, "communicate", communicate)
    with pytest.raises(JobCancelledError):
        FFmpegAdapter(cancel_event=cancel)._capture(["ffmpeg", "-version"])
    assert signals == [("killpg", ffmpeg_module.signal.SIGTERM)]


def test_capture_retries_after_a_spurious_communicate_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _FakeProcess()
    monkeypatch.setattr(ffmpeg_module, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(ffmpeg_module.time, "monotonic", iter([0.0, 0.0]).__next__)
    attempts = {"count": 0}

    def communicate(timeout: float | None = None) -> tuple[str, str]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout or 0)
        return "ok", ""

    monkeypatch.setattr(process, "communicate", communicate)
    assert FFmpegAdapter()._capture(["ffmpeg", "-version"]) == ("ok", "")
    assert attempts["count"] == 2


def test_terminate_falls_back_when_process_group_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _FakeProcess(wait_timeouts=1)
    monkeypatch.setattr(
        ffmpeg_module.os,
        "getpgid",
        lambda _pid: (_ for _ in ()).throw(OSError("gone")),
    )
    monkeypatch.setattr(
        ffmpeg_module.os,
        "killpg",
        lambda _pgid, _sig: (_ for _ in ()).throw(OSError("gone")),
    )
    FFmpegAdapter()._terminate(process)  # type: ignore[arg-type]
    assert process.terminated
    assert process.killed


# --------------------------------------------------------------------------- #
# ASR HTTP adapter
# --------------------------------------------------------------------------- #


def test_asr_builds_the_request_and_parses_words(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "segments": [
                    "junk",
                    {},
                    {"text": "   ", "start": 0, "end": 1},
                    {
                        "start": "0.5",
                        "end": "1.25",
                        "text": "  Hello  ",
                        "words": [
                            7,
                            {},
                            {"word": "   ", "start": 0, "end": 1},
                            {"word": "bad", "start": 2, "end": 1},
                            {
                                "word": "Hi",
                                "start": "0.5",
                                "end": "0.75",
                                "probability": 9,
                            },
                        ],
                    },
                ]
            },
        )

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1/audio/transcriptions",
        api_key="secret",
        language="auto",
        transport=httpx.MockTransport(handler),
    )
    sentences = adapter.transcribe(wav, 16000)
    assert seen["url"] == "http://asr.local/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer secret"
    assert b'name="language"' not in seen["body"]
    assert len(sentences) == 1
    assert sentences[0].start_sample == 8000
    assert sentences[0].end_sample == 20000
    assert sentences[0].text == "Hello"
    assert sentences[0].words[0].word == "Hi"
    assert sentences[0].words[0].probability == 1.0


def test_asr_rejects_missing_file_and_bad_sample_rate(tmp_path: Path) -> None:
    adapter = WhisperHttpAdapter(base_url="http://asr.local/v1")
    with pytest.raises(TranscriptionError, match="does not exist"):
        adapter.transcribe(tmp_path / "missing.wav", 16000)
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")
    with pytest.raises(TranscriptionError, match="sample rate"):
        adapter.transcribe(wav, 0)


def test_asr_maps_transport_and_http_errors(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(unreachable)
    )
    with pytest.raises(TranscriptionError, match="Cannot reach"):
        adapter.transcribe(wav, 16000)

    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="  overloaded  ")

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(failing)
    )
    with pytest.raises(TranscriptionError, match="HTTP 503") as caught:
        adapter.transcribe(wav, 16000)
    assert "overloaded" in str(caught.value)


def test_asr_rejects_invalid_json_and_payload_shapes(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")

    def not_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>")

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(not_json)
    )
    with pytest.raises(TranscriptionError, match="invalid JSON"):
        adapter.transcribe(wav, 16000)

    def list_payload(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2])

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(list_payload)
    )
    with pytest.raises(TranscriptionError, match="not an object"):
        adapter.transcribe(wav, 16000)


def test_asr_rejects_bad_timestamps_and_empty_results(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")

    def invalid_time(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"segments": [{"start": "nope", "end": 1, "text": "x"}]}
        )

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(invalid_time)
    )
    with pytest.raises(TranscriptionError, match="Invalid timestamp"):
        adapter.transcribe(wav, 16000)

    def backwards(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "segments": [
                    {"start": 2, "end": 1, "text": "skipped"},
                    {"start": 1, "end": 2, "text": "kept"},
                ]
            },
        )

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(backwards)
    )
    sentences = adapter.transcribe(wav, 16000)
    assert [item.text for item in sentences] == ["kept"]

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"segments": [{"text": " ", "start": 0, "end": 1}]})

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(empty)
    )
    with pytest.raises(TranscriptionError, match="no usable sentences"):
        adapter.transcribe(wav, 16000)


def test_asr_rejects_empty_segments_and_negative_timestamps(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"RIFF")

    def no_segments(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"segments": []})

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(no_segments)
    )
    with pytest.raises(TranscriptionError, match="no segments"):
        adapter.transcribe(wav, 16000)

    def negative(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"segments": [{"start": -1, "end": 1, "text": "bad"}]}
        )

    adapter = WhisperHttpAdapter(
        base_url="http://asr.local/v1", transport=httpx.MockTransport(negative)
    )
    with pytest.raises(TranscriptionError, match="negative"):
        adapter.transcribe(wav, 16000)


# --------------------------------------------------------------------------- #
# TTS adapters
# --------------------------------------------------------------------------- #


def test_openai_tts_sends_auth_and_clamps_speed(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, content=b"ID3audio")

    adapter = OpenAITtsAdapter(
        base_url="http://tts.local/v1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    target = tmp_path / "out" / "voice.mp3"
    assert adapter.synthesize("Hello", target, speed=10.0) == target
    assert target.read_bytes() == b"ID3audio"
    assert seen["url"] == "http://tts.local/v1/audio/speech"
    assert seen["auth"] == "Bearer secret"
    assert seen["json"]["speed"] == 4.0
    assert seen["json"]["response_format"] == "mp3"


def test_openai_tts_validation_and_failures(tmp_path: Path) -> None:
    adapter = OpenAITtsAdapter(base_url="http://tts.local/v1")
    with pytest.raises(TtsError, match="empty"):
        adapter.synthesize("   ", tmp_path / "voice.mp3")

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    adapter = OpenAITtsAdapter(
        base_url="http://tts.local/v1", transport=httpx.MockTransport(unreachable)
    )
    with pytest.raises(TtsError, match="Cannot reach"):
        adapter.synthesize("Hello", tmp_path / "voice.mp3")

    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="  rate limited  ")

    adapter = OpenAITtsAdapter(
        base_url="http://tts.local/v1", transport=httpx.MockTransport(failing)
    )
    with pytest.raises(TtsError, match="HTTP 429") as caught:
        adapter.synthesize("Hello", tmp_path / "voice.mp3")
    assert "rate limited" in str(caught.value)

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    adapter = OpenAITtsAdapter(
        base_url="http://tts.local/v1", transport=httpx.MockTransport(empty)
    )
    with pytest.raises(TtsError, match="empty audio"):
        adapter.synthesize("Hello", tmp_path / "voice.mp3")


def test_piper_builds_length_scale_and_writes_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        seen["command"] = command
        seen.update(kwargs)
        output = Path(command[command.index("--output_file") + 1])
        output.write_bytes(b"RIFF")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tts_module.subprocess, "run", fake_run)
    target = tmp_path / "out" / "voice.wav"
    adapter = PiperTtsAdapter(binary="piper", model_path="/model.onnx", timeout=7)
    assert adapter.synthesize("Hello", target, speed=1.5) == target
    assert seen["command"] == [
        "piper",
        "--model",
        "/model.onnx",
        "--output_file",
        str(target),
        "--length_scale",
        "0.6667",
    ]
    assert seen["input"] == "Hello"
    assert seen["timeout"] == 7

    adapter.synthesize("Hello", target, speed=1.0)
    assert "--length_scale" not in seen["command"]


def test_piper_validation_and_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(TtsError, match="empty"):
        PiperTtsAdapter(model_path="/model.onnx").synthesize(" ", tmp_path / "voice.wav")
    with pytest.raises(TtsError, match="voice model"):
        PiperTtsAdapter().synthesize("Hello", tmp_path / "voice.wav")

    def missing(command: list[str], **kwargs: Any) -> SimpleNamespace:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(tts_module.subprocess, "run", missing)
    with pytest.raises(TtsError, match="not found"):
        PiperTtsAdapter(model_path="/model.onnx").synthesize(
            "Hello", tmp_path / "voice.wav"
        )

    def timed_out(command: list[str], **kwargs: Any) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(cmd=command[0], timeout=1)

    monkeypatch.setattr(tts_module.subprocess, "run", timed_out)
    with pytest.raises(TtsError, match="timed out"):
        PiperTtsAdapter(model_path="/model.onnx", timeout=1).synthesize(
            "Hello", tmp_path / "voice.wav"
        )


def test_piper_nonzero_exit_and_missing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=2, stdout="", stderr="bad model\n")

    monkeypatch.setattr(tts_module.subprocess, "run", failed)
    with pytest.raises(TtsError, match="bad model"):
        PiperTtsAdapter(model_path="/model.onnx").synthesize(
            "Hello", tmp_path / "voice.wav"
        )

    def failed_on_stdout(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=2, stdout="stdout failure\n", stderr="")

    monkeypatch.setattr(tts_module.subprocess, "run", failed_on_stdout)
    with pytest.raises(TtsError, match="stdout failure"):
        PiperTtsAdapter(model_path="/model.onnx").synthesize(
            "Hello", tmp_path / "voice.wav"
        )

    def silent_success(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tts_module.subprocess, "run", silent_success)
    with pytest.raises(TtsError, match="did not write"):
        PiperTtsAdapter(model_path="/model.onnx").synthesize(
            "Hello", tmp_path / "voice.wav"
        )


# --------------------------------------------------------------------------- #
# whisper.cpp CLI adapter
# --------------------------------------------------------------------------- #


def test_whisper_success_builds_command_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = _wav16k(tmp_path / "source.wav")
    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"bin")
    model = tmp_path / "ggml.bin"
    model.write_bytes(b"model")
    seen: dict[str, Any] = {}
    logs: list[tuple[str, str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        seen["command"] = command
        seen.update(kwargs)
        prefix = command[command.index("-of") + 1]
        Path(prefix + ".srt").write_text(
            "1\n00:00:00,500 --> 00:00:01,250\nHello there.\n", encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(whisper_module.subprocess, "run", fake_run)
    adapter = WhisperCliAdapter(
        binary=binary,
        model=model,
        language="en",
        threads=3,
        timeout=12,
        log=lambda level, message: logs.append((level, message)),
    )
    sentences = adapter.transcribe(wav, 16000)
    assert sentences[0].start_sample == 8000
    assert sentences[0].end_sample == 20000
    assert seen["command"] == [
        str(binary),
        "-m",
        str(model),
        "-f",
        str(wav),
        "-osrt",
        "-of",
        seen["command"][7],
        "-l",
        "en",
        "-t",
        "3",
    ]
    assert seen["timeout"] == 12
    assert logs[0][0] == "debug"
    assert logs[0][1].startswith("$ ")


def test_whisper_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wav = _wav16k(tmp_path / "source.wav")
    adapter = WhisperCliAdapter(binary=tmp_path / "bin", model=tmp_path / "model")
    with pytest.raises(TranscriptionError, match="does not exist"):
        adapter.transcribe(tmp_path / "missing.wav", 16000)
    with pytest.raises(TranscriptionError, match="sample rate"):
        adapter.transcribe(wav, 0)

    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not a wave")
    with pytest.raises(TranscriptionError, match="Cannot read WAV header"):
        adapter.transcribe(bad, 16000)

    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"bin")
    model = tmp_path / "ggml.bin"
    model.write_bytes(b"model")
    with pytest.raises(TranscriptionError, match="VIDEOWFLOW_WHISPER_BIN"):
        WhisperCliAdapter(binary=tmp_path / "missing", model=model).transcribe(wav, 16000)
    with pytest.raises(TranscriptionError, match="VIDEOWFLOW_WHISPER_MODEL"):
        WhisperCliAdapter(binary=binary, model=tmp_path / "missing").transcribe(wav, 16000)

    wav48 = _wav_at(tmp_path / "source-48k.wav", 48000)
    with pytest.raises(TranscriptionError, match="16 kHz"):
        WhisperCliAdapter(binary=binary, model=model).transcribe(wav48, 48000)


def test_whisper_timeout_failure_and_missing_srt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = _wav16k(tmp_path / "source.wav")
    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"bin")
    model = tmp_path / "ggml.bin"
    model.write_bytes(b"model")
    adapter = WhisperCliAdapter(binary=binary, model=model, timeout=5)

    def timed_out(command: list[str], **kwargs: Any) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(cmd=command[0], timeout=5)

    monkeypatch.setattr(whisper_module.subprocess, "run", timed_out)
    with pytest.raises(TranscriptionError, match="timed out"):
        adapter.transcribe(wav, 16000)

    logs: list[tuple[str, str]] = []
    adapter = WhisperCliAdapter(
        binary=binary,
        model=model,
        log=lambda level, message: logs.append((level, message)),
    )

    def failed(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="", stderr="one\ntwo\nboom\n")

    monkeypatch.setattr(whisper_module.subprocess, "run", failed)
    with pytest.raises(TranscriptionError, match="boom"):
        adapter.transcribe(wav, 16000)
    assert logs[-1] == ("error", "one two boom")

    with pytest.raises(TranscriptionError, match="boom"):
        WhisperCliAdapter(binary=binary, model=model).transcribe(wav, 16000)

    def ok_without_srt(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(whisper_module.subprocess, "run", ok_without_srt)
    with pytest.raises(TranscriptionError, match="did not write an SRT"):
        adapter.transcribe(wav, 16000)


def test_whisper_invalid_and_empty_srt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = _wav16k(tmp_path / "source.wav")
    binary = tmp_path / "whisper-cli"
    binary.write_bytes(b"bin")
    model = tmp_path / "ggml.bin"
    model.write_bytes(b"model")
    adapter = WhisperCliAdapter(binary=binary, model=model)

    def invalid(command: list[str], **kwargs: Any) -> SimpleNamespace:
        prefix = command[command.index("-of") + 1]
        Path(prefix + ".srt").write_text("garbage", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(whisper_module.subprocess, "run", invalid)
    with pytest.raises(TranscriptionError, match="invalid SRT"):
        adapter.transcribe(wav, 16000)

    def success(command: list[str], **kwargs: Any) -> SimpleNamespace:
        prefix = command[command.index("-of") + 1]
        Path(prefix + ".srt").write_text("anything", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(whisper_module.subprocess, "run", success)
    monkeypatch.setattr(whisper_module, "parse_srt", lambda _text, _rate: [])
    with pytest.raises(TranscriptionError, match="empty transcript"):
        adapter.transcribe(wav, 16000)


def test_whisper_default_binary_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(whisper_module, "find_whisper_binary", lambda: None)
    monkeypatch.setattr(whisper_module, "find_whisper_model", lambda: None)
    adapter = WhisperCliAdapter()
    assert adapter.binary == Path("whisper-cli")
    assert adapter.model == Path("ggml-tiny.bin")

    monkeypatch.setattr(whisper_module, "find_whisper_binary", lambda: "/opt/whisper")
    monkeypatch.setattr(
        whisper_module, "find_whisper_model", lambda: Path("/opt/ggml-tiny.bin")
    )
    adapter = WhisperCliAdapter()
    assert adapter.binary == Path("/opt/whisper")
    assert adapter.model == Path("/opt/ggml-tiny.bin")


# --------------------------------------------------------------------------- #
# Diarization
# --------------------------------------------------------------------------- #


def test_assign_speakers_picks_the_largest_overlap() -> None:
    sentences = [
        Sentence(id=0, start_sample=0, end_sample=10, text="a"),
        Sentence(id=1, start_sample=40, end_sample=50, text="b"),
    ]
    turns = [
        SpeakerTurn(0, 5, "A"),
        SpeakerTurn(0, 10, "B"),
        SpeakerTurn(20, 30, "A"),
    ]
    updated = assign_speakers(sentences, turns)
    assert [item.speaker for item in updated] == [1, 0]
    assert [item.text for item in updated] == ["a", "b"]
    assert assign_speakers(sentences, [])[0].speaker == 0


def test_pyannote_reports_a_missing_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "pyannote.audio", None)
    diarizer = PyannoteDiarizer(model_path="model", device="cpu", hf_token="token")
    assert diarizer.model_path == "model"
    assert diarizer.device == "cpu"
    assert diarizer.hf_token == "token"
    with pytest.raises(CapabilityUnavailableError, match="pyannote"):
        diarizer.diarize(tmp_path / "audio.wav", sample_rate=16000)


def _install_fake_pyannote(
    monkeypatch: pytest.MonkeyPatch, pipeline: object
) -> dict[str, Any]:
    calls: dict[str, Any] = {}

    class FakePipeline:
        @staticmethod
        def from_pretrained(model_path: str, *, use_auth_token: str | None) -> object:
            calls["model_path"] = model_path
            calls["token"] = use_auth_token
            if isinstance(pipeline, Exception):
                raise pipeline
            return pipeline

    torch_module = ModuleType("torch")

    def fake_device(name: str) -> str:
        calls["device"] = name
        return "device:" + name

    torch_module.device = fake_device  # type: ignore[attr-defined]
    audio_module = ModuleType("pyannote.audio")
    audio_module.Pipeline = FakePipeline  # type: ignore[attr-defined]
    pyannote_module = ModuleType("pyannote")
    pyannote_module.audio = audio_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "pyannote", pyannote_module)
    monkeypatch.setitem(sys.modules, "pyannote.audio", audio_module)
    return calls


def test_pyannote_load_failure_is_a_capability_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_pyannote(monkeypatch, RuntimeError("gated model"))
    with pytest.raises(CapabilityUnavailableError, match="Could not load"):
        PyannoteDiarizer(model_path="gated", hf_token="bad").diarize(
            tmp_path / "audio.wav", sample_rate=16000
        )


def test_pyannote_success_moves_device_and_reads_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakePipeline:
        def __init__(self) -> None:
            self.moved_to: object = None

        def to(self, device: object) -> None:
            self.moved_to = device

        def __call__(self, path: str) -> Any:
            assert path.endswith("audio.wav")

            class Tracks:
                def itertracks(self, *, yield_label: bool) -> list[tuple[Any, Any, str]]:
                    assert yield_label is True
                    return [
                        (SimpleNamespace(start=0.5, end=1.25), None, "SPEAKER_00"),
                        (SimpleNamespace(start=2.0, end=3.0), None, "SPEAKER_01"),
                    ]

            return Tracks()

    pipeline = FakePipeline()
    calls = _install_fake_pyannote(monkeypatch, pipeline)
    audio = tmp_path / "audio.wav"
    diarizer = PyannoteDiarizer(model_path="model", device="cuda", hf_token="hf")
    turns = diarizer.diarize(audio, sample_rate=16000)
    assert calls == {"model_path": "model", "token": "hf", "device": "cuda"}
    assert pipeline.moved_to == "device:cuda"
    assert turns == [
        SpeakerTurn(8000, 20000, "SPEAKER_00"),
        SpeakerTurn(32000, 48000, "SPEAKER_01"),
    ]


def test_pyannote_without_device_skips_the_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class EmptyPipeline:
        def __call__(self, path: str) -> Any:
            class Tracks:
                def itertracks(self, *, yield_label: bool) -> list[Any]:
                    return []

            return Tracks()

    _install_fake_pyannote(monkeypatch, EmptyPipeline())
    assert PyannoteDiarizer().diarize(tmp_path / "audio.wav", sample_rate=8000) == []
