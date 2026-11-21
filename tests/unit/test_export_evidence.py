from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.export_evidence import preserve_failed_export


def test_failed_export_preserves_error_segments_and_probe(tmp_path: Path) -> None:
    segments = tmp_path / "render" / "segments"
    segments.mkdir(parents=True)
    (segments / "segment-01.mp4").write_bytes(b"segment")
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "voice.wav").write_bytes(b"wav")
    target = preserve_failed_export(
        tmp_path,
        error="audio_duration_mismatch",
        command="export_timeline",
    )
    assert (target / "failure.json").is_file()
    failure = json.loads((target / "failure.json").read_text())
    assert failure["error"] == "audio_duration_mismatch"
    assert (target / "segments" / "segment-01.mp4").is_file()
    assert (target / "audio" / "voice.wav").is_file()
    assert (target / "ffprobe.json").is_file()
