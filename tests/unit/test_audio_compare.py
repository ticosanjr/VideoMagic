from __future__ import annotations

import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from videoflow.application import audio_compare
from videoflow.application.audio_compare import (
    _median_filter,
    compare_audio,
    dtw_subsequence,
    dtw_symmetric,
    interval_duration,
    interval_f1,
    interval_overlap,
    interval_union,
    load_pcm,
    log_mel,
    loudness_stats,
    reconstruct,
    silence_spans,
    silence_stats,
    spectral_correlation,
    window_descriptors,
)
from videoflow.domain.errors import IngestError


def _tone(frequency: float, seconds: float, rate: int = 16_000) -> np.ndarray:
    time = np.arange(round(seconds * rate), dtype=np.float32) / rate
    signal = 0.3 * np.sin(2 * np.pi * frequency * time)
    signal += 0.005 * np.random.default_rng(0).normal(size=signal.size).astype(np.float32)
    return signal.astype(np.float32)


def test_log_mel_shape() -> None:
    signal = _tone(440.0, 1.0)
    features = log_mel(signal)
    assert features.shape[1] == 64
    assert features.shape[0] == 1 + (signal.size - 400) // 160
    assert np.isfinite(features).all()


def test_window_descriptors_are_normalised() -> None:
    rng = np.random.default_rng(1)
    features = rng.normal(size=(300, 64)).astype(np.float32)
    descriptor = window_descriptors(features)
    assert descriptor.shape == (5, 1024)
    norms = np.linalg.norm(descriptor, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)


def test_dtw_subsequence_recovers_known_segments() -> None:
    raw = np.eye(100, dtype=np.float32)
    source = np.concatenate([raw[10:30], raw[50:70]], axis=0)
    matches, _cost = dtw_subsequence(source, raw)
    assert len(matches) == 40
    for source_index, target_index in matches:
        expected = 10 + source_index if source_index < 20 else 30 + source_index
        assert target_index == expected


def test_dtw_symmetric_identical_audio_scores_one() -> None:
    signal = np.concatenate(
        [_tone(220.0, 1.0), _tone(440.0, 1.0), _tone(660.0, 1.0)]
    )
    result = compare_audio(signal, signal, tau=0.9)
    assert result.audio_f1 >= 0.999
    assert result.coverage_reference >= 0.999
    assert result.coverage_output >= 0.999


def test_compare_audio_penalises_removed_content() -> None:
    signal = np.concatenate(
        [_tone(220.0, 2.0), _tone(440.0, 2.0), _tone(660.0, 2.0)]
    )
    cut = np.concatenate([signal[: 2 * 16_000], signal[4 * 16_000 :]])
    result = compare_audio(signal, cut, tau=0.9)
    assert result.audio_f1 < 0.98
    assert result.output_seconds < result.reference_seconds


def test_dtw_symmetric_returns_diagonal_for_identical_features() -> None:
    features = np.eye(30, dtype=np.float32)
    matches = dtw_symmetric(features, features)
    assert matches == [(index, index) for index in range(30)]


def test_interval_f1_tolerates_small_boundary_shift() -> None:
    reference = [(0.0, 10.0), (20.0, 30.0)]
    output = [(0.1, 10.1), (20.1, 30.1)]
    result = interval_f1(reference, output, tolerance=0.15)
    assert result["f1"] >= 0.999
    assert interval_overlap(reference, output) == pytest.approx(19.8)
    assert interval_union(reference) == [(0.0, 10.0), (20.0, 30.0)]


def test_interval_f1_penalises_missing_content() -> None:
    result = interval_f1([(0.0, 10.0), (20.0, 30.0)], [(0.0, 5.0)], tolerance=0.15)
    assert result["f1"] < 0.5


def test_silence_spans_and_stats() -> None:
    signal = np.concatenate(
        [np.zeros(16_000, dtype=np.float32), _tone(440.0, 1.0), np.zeros(16_000, dtype=np.float32)]
    )
    spans = silence_spans(signal, min_ms=100)
    stats = silence_stats(spans)
    assert stats["events"] == 2
    assert stats["total_seconds"] >= 1.9


def test_spectral_correlation_identical() -> None:
    signal = _tone(330.0, 2.0)
    assert spectral_correlation(signal, signal) > 0.999


def _write_wav(path: Path, samples: np.ndarray, rate: int = 16_000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(
            b"".join(struct.pack("<h", int(value * 32767)) for value in samples)
        )


def test_load_pcm_decodes_a_wav(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _write_wav(path, _tone(440.0, 1.0))
    pcm = load_pcm(path)
    assert pcm.dtype == np.float32
    assert 15_000 <= pcm.size <= 16_100
    assert float(np.max(np.abs(pcm))) > 0.1


def test_load_pcm_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(IngestError):
        load_pcm(tmp_path / "missing.wav")


def test_interval_helpers_cover_empty_and_touching_ranges() -> None:
    assert interval_union([(0.0, 1.0), (1.0, 2.0), (3.0, 3.0)]) == [(0.0, 2.0)]
    assert interval_duration([(0.0, 1.0), (2.0, 3.0)]) == 2.0
    assert interval_overlap([], [(0.0, 1.0)]) == 0.0
    assert interval_f1([], [])["f1"] == 0.0
    assert interval_f1([(0.0, 1.0)], [(2.0, 3.0)])["f1"] == 0.0


def test_reconstruct_concatenates_source_intervals() -> None:
    pcm = np.arange(1000, dtype=np.float32)
    output = reconstruct(pcm, [(0.0, 0.1), (0.2, 0.3)], sample_rate=1000)
    assert output.size == 200
    assert output[0] == 0.0
    assert output[100] == 200.0


def test_loudness_stats_parses_loudnorm_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audio_compare, "find_binary", lambda _name: "ffmpeg")

    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            stderr=(
                b"noise\n"
                b'{"input_i":"-16.0","input_tp":"-1.5","input_lra":"7.0"}'
            )
        )

    monkeypatch.setattr(audio_compare.subprocess, "run", fake_run)
    result = loudness_stats(Path("video.mp4"))
    assert result == {"lufs": -16.0, "true_peak": -1.5, "lra": 7.0}


def test_loudness_stats_handles_unparseable_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audio_compare, "find_binary", lambda _name: "ffmpeg")
    monkeypatch.setattr(
        audio_compare.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stderr=b""),
    )
    assert loudness_stats(Path("video.mp4")) == {
        "lufs": None,
        "true_peak": None,
        "lra": None,
    }


def test_silence_spans_empty_signal() -> None:
    assert silence_spans(np.zeros(0, dtype=np.float32)) == []


def test_dtw_empty_inputs() -> None:
    assert dtw_subsequence(np.zeros((0, 4)), np.zeros((3, 4))) == ([], 0.0)
    assert dtw_symmetric(np.zeros((0, 4)), np.zeros((3, 4))) == []


def test_load_pcm_reports_ffmpeg_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.wav"
    path.write_bytes(b"not really audio")
    monkeypatch.setattr(audio_compare, "find_binary", lambda _name: None)
    with pytest.raises(IngestError):
        load_pcm(path)
    monkeypatch.setattr(audio_compare, "find_binary", lambda _name: "ffmpeg")
    monkeypatch.setattr(
        audio_compare.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stdout=b"", stderr=b"bad input"
        ),
    )
    with pytest.raises(IngestError):
        load_pcm(path)
    monkeypatch.setattr(
        audio_compare.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=b"", stderr=b""
        ),
    )
    with pytest.raises(IngestError):
        load_pcm(path)


def test_loudness_stats_reports_ffmpeg_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audio_compare, "find_binary", lambda _name: "ffmpeg")

    def fail(*_args: object, **_kwargs: object) -> SimpleNamespace:
        raise OSError("ffmpeg missing")

    monkeypatch.setattr(audio_compare.subprocess, "run", fail)
    assert loudness_stats(Path("video.mp4"))["lufs"] is None

    def timeout(*_args: object, **_kwargs: object) -> SimpleNamespace:
        raise audio_compare.subprocess.TimeoutExpired("ffmpeg", 1)

    monkeypatch.setattr(audio_compare.subprocess, "run", timeout)
    assert loudness_stats(Path("video.mp4"))["lufs"] is None

    monkeypatch.setattr(
        audio_compare.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stderr=b"no json here"),
    )
    assert loudness_stats(Path("video.mp4"))["lufs"] is None


def test_extract_features_pads_short_audio() -> None:
    features = audio_compare.extract_features(np.zeros(1000, dtype=np.float32))
    assert features.descriptors.shape[0] == 1
    assert features.speech.shape[0] == 1


def test_silence_stats_empty() -> None:
    assert silence_stats([]) == {
        "total_seconds": 0.0,
        "max_seconds": 0.0,
        "events": 0,
    }


def test_median_filter_smooths_a_short_series() -> None:
    values = np.asarray([0.0, 10.0, 0.0, 0.0, 10.0, 0.0])
    filtered = _median_filter(values, size=3)
    assert filtered.shape == values.shape
    assert float(filtered[1]) == 0.0


def test_audio_compare_error_and_edge_branches(monkeypatch, tmp_path: Path) -> None:
    import subprocess

    import numpy as np
    import pytest

    from videoflow.application import audio_compare as module
    from videoflow.domain.errors import IngestError

    monkeypatch.setattr(module, "find_binary", lambda name: None)
    with pytest.raises(IngestError, match="FFmpeg"):
        module.load_pcm(tmp_path / "missing.wav")
    monkeypatch.setattr(module, "find_binary", lambda name: "ffmpeg")
    with pytest.raises(IngestError, match="does not exist"):
        module.load_pcm(tmp_path / "missing.wav")
    source = tmp_path / "source.wav"
    source.write_bytes(b"wav")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no ffmpeg")),
    )
    with pytest.raises(IngestError, match="decode failed"):
        module.load_pcm(source)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, b"", b""),
    )
    with pytest.raises(IngestError, match="no PCM"):
        module.load_pcm(source)

    assert module.log_mel(np.zeros((2, 10), dtype=np.float32)).shape[1] == module.N_MELS
    assert module.log_mel(np.zeros(4, dtype=np.float32)).shape[0] >= 1
    assert module.frame_rms(np.zeros((2, 10), dtype=np.float32)).size >= 1
    monkeypatch.setattr(module, "frame_rms", lambda *args, **kwargs: np.zeros(0))
    assert module.speech_fraction(np.zeros(0, dtype=np.float32)).size == 0
    monkeypatch.undo()
    monkeypatch.setattr(module, "find_binary", lambda name: "ffmpeg")
    with pytest.raises(ValueError):
        module.window_descriptors(np.zeros(2, dtype=np.float32))
    with pytest.raises(ValueError):
        module.dtw_subsequence(np.zeros(2), np.zeros((2, 2)))
    with pytest.raises(ValueError):
        module.dtw_symmetric(np.zeros((2, 2)), np.zeros(2))
    assert module.dtw_subsequence(np.zeros((0, 2)), np.zeros((2, 2))) == ([], 0.0)
    assert module.dtw_symmetric(np.zeros((0, 2)), np.zeros((2, 2))) == []

    values = np.arange(3)
    assert module._median_filter(values, size=5) is not values
    assert module._median_filter(values, size=1) is not values

    assert module.silence_spans(np.zeros(0, dtype=np.float32)) == []
    assert module.silence_stats([]) == {
        "total_seconds": 0.0,
        "max_seconds": 0.0,
        "events": 0,
    }


def test_loudness_and_spectral_edge_branches(monkeypatch, tmp_path: Path) -> None:
    import subprocess

    import numpy as np

    from videoflow.application import audio_compare as module

    monkeypatch.setattr(module, "find_binary", lambda name: None)
    assert module.loudness_stats(tmp_path / "x.wav")["lufs"] is None

    monkeypatch.setattr(module, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, b"", b"no json"),
    )
    assert module.loudness_stats(tmp_path / "x.wav")["lufs"] is None
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, b"", b'{"input_i": "bad", "input_tp": 1.0}'
        ),
    )
    stats = module.loudness_stats(tmp_path / "x.wav")
    assert stats["lufs"] is None and stats["true_peak"] == 1.0
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, b"", b"{bad}"),
    )
    assert module.loudness_stats(tmp_path / "x.wav")["lra"] is None
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("down")),
    )
    assert module.loudness_stats(tmp_path / "x.wav")["lufs"] is None

    assert module.spectral_correlation(np.zeros(4), np.zeros(4)) == 0.0
    assert module.spectral_correlation(np.zeros(10), np.zeros(10)) == 0.0
    assert module.reconstruct(np.zeros(100, dtype=np.float32), []) .size == 0
