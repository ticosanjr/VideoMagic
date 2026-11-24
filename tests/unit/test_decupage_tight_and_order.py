"""v4.6 decupage ordering, pacing params, and timeline protection."""

from __future__ import annotations

import wave
from pathlib import Path

from videoflow.application.beatmap_plan import build_beatmap_plan
from videoflow.core.context import PipelineContext
from videoflow.domain.state import (
    AudioSegment,
    InactiveSegment,
    MediaInfo,
    OverlayClip,
    ProjectState,
    VideoSegment,
)
from videoflow.domain.styles import StyleDefinition
from videoflow.mcp_server.core_tools.official import register_official_tools
from videoflow.steps.base import StepIO
from videoflow.steps.timeline import TimelineParams, TimelineStep

RATE = 48_000


def _source(tmp_path: Path, seconds: float = 1.0) -> Path:
    path = tmp_path / "source.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b"\x00\x00" * int(RATE * seconds))
    return path


def _state(tmp_path: Path) -> ProjectState:
    source = _source(tmp_path, 2.0)
    media = MediaInfo(
        source_path=str(source),
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=RATE,
    )
    return ProjectState(
        media_info=media,
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=RATE,
                timeline_in_sample=0,
                timeline_out_sample=RATE,
            )
        ],
        inactive_segments=[
            InactiveSegment(
                clip_id="i1",
                video=VideoSegment(
                    clip_id="i1",
                    source_in_frame=30,
                    source_out_frame=60,
                    timeline_in_frame=30,
                    timeline_out_frame=60,
                ),
                audio=AudioSegment(
                    clip_id="i1",
                    source_in_sample=RATE,
                    source_out_sample=RATE + 1000,
                    timeline_in_sample=RATE,
                    timeline_out_sample=RATE + 1000,
                ),
                reason="silence",
            )
        ],
    )


def test_timeline_params_accepts_pacing_fields() -> None:
    params = TimelineParams(
        pacing_profile="tight",
        min_silence_ms=180,
        max_pause_ms=200,
        qa_dead_air_ms=500,
        reset=True,
    )
    assert params.pacing_profile == "tight"
    assert params.max_pause_ms == 200


def test_run_full_orders_speech_asu_before_decupage_and_uses_timeline() -> None:
    captured = {}
    calls: dict[str, object] = {}

    def register(fn):
        captured[fn.__name__] = fn
        return fn

    def fake_run(**kwargs):
        calls.update(kwargs)
        return {"ok": True, "job": {"status": "succeeded"}}

    def noop(**kwargs):
        return {"ok": True}

    register_official_tools(
        register,
        {
            "vf_beatmap_plan": lambda **kwargs: {
                "ok": True,
                "path": "beat_map.json",
                "plan": {"schema_version": 2},
            },
            "vf_run": fake_run,
            "vf_transcript_query": noop,
            "vf_shorts_batch": noop,
            "vf_qa_final": noop,
            "vf_job": noop,
        },
    )
    captured["vf_decupage"](
        action="run_full",
        project_id="demo",
        pacing_profile="tight",
        wait=False,
    )
    assert calls["steps"] == [
        "ingest",
        "audio.vad",
        "transcribe",
        "speech.asu",
        "speech.editorial_clean",
        "retakes.cull",
        "decupage.snap",
        "edit.timeline",
    ]
    step_params = calls["step_params"]
    assert step_params["edit.timeline"]["reset"] is True
    assert step_params["edit.timeline"]["max_pause_ms"] == 200
    assert step_params["decupage.snap"]["min_cut_gap_ms"] == 200


def test_beatmap_plan_fills_keep_and_remove_ranges(tmp_path: Path) -> None:
    state = _state(tmp_path)
    plan = build_beatmap_plan(state, StyleDefinition(style_id="demo", name="Demo"))
    assert plan["keep_ranges"]
    assert plan["remove_ranges"]
    assert plan["time_basis"] == "source"


def test_timeline_preserves_existing_overlays(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.overlays = [
        OverlayClip(
            overlay_id="keep-me",
            path=str(tmp_path / "overlay.png"),
            start_frame=0,
            duration_frames=10,
        )
    ]
    source = Path(state.media_info.source_path)
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=state.media_info,
        state=state,
        speech_intervals=[(0, RATE)],
    )
    context.output.mkdir(parents=True, exist_ok=True)
    TimelineStep().run(
        context,
        TimelineParams(
            cut_mode="hard",
            reset=True,
            noise_filter="off",
            remove_impulsive_noise=False,
            keep_untranscribed=False,
            detect_repeats=False,
        ),
        StepIO(),
    )
    assert context.state is not None
    assert [item.overlay_id for item in context.state.overlays] == ["keep-me"]
