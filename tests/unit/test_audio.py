from videoflow.application.audio import audio_filters, with_audio_filters
from videoflow.domain.config import AudioEnhanceConfig


def test_audio_filters_are_opt_in_and_configurable() -> None:
    assert audio_filters(AudioEnhanceConfig()) == []
    filters = audio_filters(
        AudioEnhanceConfig(
            enabled=True,
            highpass_hz=120,
            denoise=True,
            denoise_db=18,
            noise_floor_db=-35,
            loudnorm=True,
            target_lufs=-14,
            true_peak_db=-1,
        )
    )
    assert filters[0] == "highpass=f=120"
    assert "afftdn=nr=18:nf=-35" in filters
    assert "loudnorm=I=-14.0:TP=-1.0:LRA=11" in filters
    assert with_audio_filters(filters) == ",".join(filters)
    assert with_audio_filters([]) is None
