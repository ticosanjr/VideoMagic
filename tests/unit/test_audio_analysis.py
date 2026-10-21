import numpy as np

from videoflow.application.audio_analysis import energy_peaks


def test_energy_peaks_finds_a_loud_region() -> None:
    sample_rate = 16000
    samples = np.zeros(sample_rate * 2, dtype=np.int16)
    samples[sample_rate : sample_rate + sample_rate // 2] = 12000
    peaks = energy_peaks(samples, sample_rate)
    assert len(peaks) == 1
    start, end = peaks[0]
    assert start <= sample_rate <= end
    assert end >= sample_rate + sample_rate // 2


def test_energy_peaks_returns_empty_for_silence() -> None:
    assert energy_peaks(np.zeros(16000, dtype=np.int16), 16000) == []
