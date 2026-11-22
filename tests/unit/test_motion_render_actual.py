from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from videoflow.application.intro import compile_intro
from videoflow.application.motion import build_scenes, render_scene
from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo
from videoflow.domains.audio.synth import compose_music, synthesize_foley
from videoflow.steps.audio_synth import (
    AudioComposeStep,
    AudioMixStep,
    ComposeParams,
    MixParams,
    SfxSynthParams,
    SfxSynthStep,
)
from videoflow.steps.base import StepIO

FFMPEG = shutil.which("ffmpeg")


def _silent_wav(path: Path, seconds: float = 1.0, rate: int = 8000) -> Path:
    samples = np.zeros(int(seconds * rate), dtype="<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return path


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_motion_renderer_with_and_without_asset(tmp_path: Path) -> None:
    scene = build_scenes(
        [
            {
                "unit_id": "U1",
                "title": "Evidence",
                "layout": "lower_third",
                "duration_sec": 0.5,
            }
        ],
        style={"palette": ["#080B10", "#F8FAFC", "#FF3B30"]},
        assets={},
        width=320,
        height=180,
        fps=12,
    )[0]
    output = render_scene(scene, tmp_path / "plain")
    assert output.is_file() and output.stat().st_size > 0

    image = tmp_path / "reference.png"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180",
            "-frames:v",
            "1",
            str(image),
        ],
        check=True,
    )
    with_asset = build_scenes(
        [
            {
                "unit_id": "U2",
                "title": "With asset",
                "layout": "full_screen",
                "duration_sec": 0.5,
            }
        ],
        style={"palette": ["#080B10", "#F8FAFC", "#FF3B30"]},
        assets={"U2": [{"path": str(image), "kind": "image"}]},
        width=320,
        height=180,
        fps=12,
    )[0]
    second = render_scene(with_asset, tmp_path / "asset")
    assert second.is_file() and second.stat().st_size > 0


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_intro_title_card_and_montage(tmp_path: Path) -> None:
    card = compile_intro(
        tmp_path / "card", assets=[], duration_sec=1, width=320, height=180, fps=12
    )
    assert Path(card["path"]).is_file()
    images = []
    for index, color in enumerate(("red", "blue")):
        path = tmp_path / f"{index}.png"
        subprocess.run(
            [
                FFMPEG,
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x180",
                "-frames:v",
                "1",
                str(path),
            ],
            check=True,
        )
        images.append({"downloaded_path": str(path)})
    montage = compile_intro(
        tmp_path / "montage",
        assets=images,
        duration_sec=2,
        clip_seconds=1,
        width=320,
        height=180,
        fps=12,
    )
    assert Path(montage["path"]).is_file()
    assert montage["asset_count"] == 2


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_audio_compose_sfx_and_mix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    (output / "audio").mkdir(parents=True)
    _silent_wav(output / "audio" / "master.wav")
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=MediaInfo(
            source_path=str(tmp_path / "source.mp4"),
            duration_frames=25,
            fps_num=25,
            fps_den=1,
            width=320,
            height=180,
            audio_sample_rate=8000,
        ),
        artifacts={"audio_master": str(output / "audio" / "master.wav")},
    )
    AudioComposeStep().run(context, ComposeParams(duration_sec=1), StepIO())
    assert Path(context.artifacts["audio_music"]).is_file()
    SfxSynthStep().run(context, SfxSynthParams(max_cues=2), StepIO())
    assert context.metadata["sfx_cues"]
    AudioMixStep().run(context, MixParams(), StepIO())
    assert Path(context.artifacts["audio_mix"]).is_file()
    assert (output / "audio" / "master.wav").is_file()


def test_audio_loop_and_foley_fallback(tmp_path: Path) -> None:
    music = compose_music(
        tmp_path / "music", duration_sec=3, sample_rate=4000, max_loop_seconds=1
    )
    assert music["loop_seconds"] == 1.0
    assert music["requested_duration_sec"] == 3.0
    foley = synthesize_foley(
        tmp_path / "sfx",
        [
            {"kind": "paper_turn", "start_sec": 0},
            {"kind": "marker_underline", "start_sec": 1},
            {"kind": "riser", "start_sec": 2},
            {"kind": "impact", "start_sec": 3},
            {"kind": "whoosh", "start_sec": 4},
        ],
        sample_rate=4000,
    )
    assert foley["count"] == 5
    assert json.loads(json.dumps({"ok": True}))["ok"] is True
