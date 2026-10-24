"""Dubbing duration alignment and translation review output."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import dubbing
from videoflow.domain.config import DubbingConfig, TtsConfig
from videoflow.domain.state import MediaInfo, ProjectState, Sentence


def test_alignment_retries_and_writes_a_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "out"
    short_path = output / "shorts" / "01.mp4"
    short_path.parent.mkdir(parents=True)
    short_path.write_bytes(b"video")
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(tmp_path / "source.mp4"),
            duration_frames=100,
            fps_num=25,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=48000,
        ),
        transcript=[Sentence(id=0, start_sample=0, end_sample=48000, text="hello world")],
    )
    (output / "project_state.json").write_text(state.model_dump_json(), encoding="utf-8")
    entry = {
        "title": "One",
        "path": str(short_path),
        "pieces": [[0, 48000]],
        "duration_sec": 4.0,
    }
    (output / "shorts.json").write_text(
        json.dumps({"clips": [entry]}), encoding="utf-8"
    )
    speeds: list[float] = []

    def synth(self, text, destination, *, speed=1.0):
        speeds.append(speed)
        Path(destination).write_bytes(b"audio")

    monkeypatch.setattr(dubbing, "ensure_external_allowed", lambda *args, **kwargs: None)
    monkeypatch.setattr(dubbing, "translate_text", lambda *args: "hola mundo")
    monkeypatch.setattr(dubbing.OpenAITtsAdapter, "synthesize", synth)
    probes = iter(
        [
            SimpleNamespace(duration_frames=8, fps_num=1, fps_den=1),
            SimpleNamespace(duration_frames=4, fps_num=1, fps_den=1),
        ]
    )
    monkeypatch.setattr(dubbing.FFmpegAdapter, "probe", lambda self, path: next(probes))
    monkeypatch.setattr(
        dubbing.FFmpegAdapter, "mix_voiceover", lambda self, *a, **k: Path(a[2]).write_bytes(b"mix")
    )

    payload = dubbing.generate_short_dubbing(
        output=output,
        index=0,
        result={"shorts": [dict(entry)]},
        source_text=None,
        target_language="es",
        tts=TtsConfig(
            provider="openai_compatible",
            base_url="http://localhost:1/v1",
            model="tts",
            voice="alloy",
            speed=1.0,
        ),
        dubbing=DubbingConfig(target_language="es", original_volume=0.1),
        llm_base_url="http://localhost:1/v1",
        llm_model="llm",
    )

    assert payload["alignment"]["retried"] is True
    assert speeds[0] == 1.0
    assert speeds[1] > 1.0
    review = Path(payload["translation_review"])
    assert review.is_file()
    assert json.loads(review.read_text(encoding="utf-8"))["translated"] == "hola mundo"
