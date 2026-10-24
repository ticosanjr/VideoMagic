from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from videoflow.application.audio_analysis import detect_beats

pytestmark = pytest.mark.media


def test_beat_detection_finds_onsets(tmp_path: Path) -> None:
    wav = tmp_path / "clicks.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc='if(lt(mod(t,0.5),0.04),0.8*sin(2*PI*1000*t),0)':d=4:s=16000",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ],
        check=True,
    )
    beats = detect_beats(wav)
    assert len(beats) >= 4
    assert beats == sorted(beats)
