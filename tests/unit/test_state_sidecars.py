from __future__ import annotations

import hashlib
import json
from pathlib import Path

from videoflow.application.state_sidecars import (
    load_state_from_index,
    read_state_index,
    write_state_index,
)
from videoflow.domain.state import MediaInfo, ProjectState, Sentence, WordTiming


def _state() -> ProjectState:
    words = [
        WordTiming(
            word=f"palavra{index}",
            start_sample=index * 480,
            end_sample=index * 480 + 400,
            probability=0.9,
        )
        for index in range(400)
    ]
    sentence = Sentence(
        id=0,
        start_sample=0,
        end_sample=400 * 480,
        text=" ".join(word.word for word in words),
        words=words,
    )
    media = MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=1800,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48_000,
    )
    return ProjectState(
        media_info=media,
        transcript=[sentence],
        language="pt",
    )


def test_state_index_is_light_and_round_trips(tmp_path: Path) -> None:
    state = _state()
    write_state_index(tmp_path, state)
    index = read_state_index(tmp_path)
    assert index["pipeline_schema_version"] == "4.0"
    assert index["sidecars"]["transcript_raw"]["sentences"] == 1
    assert (tmp_path / "state.json").stat().st_size < 8192
    loaded = load_state_from_index(tmp_path)
    assert loaded is not None
    assert loaded.transcript[0].text == state.transcript[0].text
    assert loaded.media_info is not None
    assert loaded.media_info.source_path == "/tmp/source.mp4"


def test_sidecar_checksums_match_files(tmp_path: Path) -> None:
    write_state_index(tmp_path, _state())
    index = read_state_index(tmp_path)
    for pointer in index["sidecars"].values():
        path = tmp_path / pointer["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pointer["sha256"]


def test_transcript_clean_is_always_written(tmp_path: Path) -> None:
    write_state_index(tmp_path, _state())
    index = read_state_index(tmp_path)
    assert "transcript_raw" in index["sidecars"]
    assert "transcript_clean" in index["sidecars"]
    payload = json.loads(
        (tmp_path / index["sidecars"]["transcript_clean"]["path"]).read_text()
    )
    assert payload["pipeline_schema_version"] == "4.0"
    assert payload["sentences"]
