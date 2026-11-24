from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from videoflow.application.beatmap import Beatmap, apply_beatmap
from videoflow.application.beatmap_plan import build_beatmap_plan
from videoflow.application.decupage.deterministic import build_safe_speech_spans
from videoflow.application.decupage.snap import build_plan
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.domain.decupage import Asu, AsuWord
from videoflow.domain.errors import MissingPrerequisiteError
from videoflow.domain.state import MediaInfo, ProjectState, Sentence, WordTiming
from videoflow.domain.styles import StyleDefinition
from videoflow.steps.base import StepIO
from videoflow.steps.captions import CaptionsPlanParams, CaptionsPlanStep
from videoflow.steps.decupage_snap import DecupageSnapStep, SnapParams
from videoflow.steps.retakes import RetakesParams, RetakesStep

RATE = 48_000


def _media(duration_frames: int = 300) -> MediaInfo:
    return MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=duration_frames,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=RATE,
    )


def _word(text: str, start: int, end: int, probability: float = 0.9) -> WordTiming:
    return WordTiming(
        word=text,
        start_sample=start,
        end_sample=end,
        probability=probability,
    )


def _sentence(
    identifier: int,
    start: int,
    end: int,
    *,
    words: list[WordTiming] | None = None,
) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=start,
        end_sample=end,
        text="texto de teste.",
        words=words or [],
    )


def _context(tmp_path: Path, *, duration_frames: int = 300) -> PipelineContext:
    media = _media(duration_frames)
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=media,
        pcm_digest=uuid4().hex,
    )


def test_retakes_cull_requires_vad_before_running(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript = [_sentence(0, 0, 10_000)]
    with pytest.raises(MissingPrerequisiteError) as exc:
        RetakesStep().run(context, RetakesParams(), StepIO())
    assert exc.value.code == "missing_prerequisite"
    assert "audio.vad" in exc.value.to_dict()["fix_hint"]


def test_safe_speech_spans_protects_low_volume_transcribed_words() -> None:
    word_start = 30 * RATE
    word_end = 31 * RATE
    words = [_word("baixo", word_start, word_end)]
    spans, flagged = build_safe_speech_spans(
        [(0, RATE), (50 * RATE, 51 * RATE)],
        [_sentence(0, word_start, word_end, words=words)],
        set(),
        sample_rate=RATE,
        duration_samples=60 * RATE,
    )
    assert any(start <= word_start and end >= word_end for start, end in spans)
    assert any(item["start_sec"] >= 31 for item in flagged)
    assert all(item["requires_review"] is False for item in flagged)


def test_safe_speech_spans_flags_long_removed_gaps() -> None:
    profile = {"db": [-60.0] * 4000, "hop_samples": 480}
    _spans, quiet = build_safe_speech_spans(
        [(0, RATE), (30 * RATE, 31 * RATE)],
        [],
        set(),
        sample_rate=RATE,
        duration_samples=31 * RATE,
        rms_profile=profile,
    )
    assert any(item["duration_sec"] > 15 for item in quiet)
    assert all(item["requires_review"] is False for item in quiet)

    loud_profile = {"db": [-30.0] * 4000, "hop_samples": 480}
    _spans, loud = build_safe_speech_spans(
        [(0, RATE), (30 * RATE, 31 * RATE)],
        [],
        set(),
        sample_rate=RATE,
        duration_samples=31 * RATE,
        rms_profile=loud_profile,
    )
    assert any(item["requires_review"] is True for item in loud)


def test_snap_applies_hard_pad_floor() -> None:
    word = AsuWord(
        idx=0,
        w="palavra",
        start_sample=10_000,
        end_sample=11_000,
        start_sec=10_000 / RATE,
        end_sec=11_000 / RATE,
        p=0.9,
    )
    asu = Asu(
        asu_id="ASU_1",
        start_sample=10_000,
        end_sample=11_000,
        start_sec=10_000 / RATE,
        end_sec=11_000 / RATE,
        text="palavra",
        words=[word],
        avg_word_prob=0.9,
    )
    plan = build_plan(
        _media(),
        [asu],
        [],
        profile={"db": [-60.0] * 4000, "hop_samples": 480},
        noise_events=[],
        review_flags=[],
        min_clip_ms=0,
        pre_roll_ms=0,
        post_roll_ms=0,
        pre_roll_floor_ms=90,
        post_roll_floor_ms=150,
    )
    span = plan.active_spans[0]
    assert span.start_sample <= 10_000 - round(0.09 * RATE)
    assert span.end_sample >= 11_000 + round(0.15 * RATE)


def test_beatmap_plan_round_trips_through_apply_model(tmp_path: Path) -> None:
    state = ProjectState(
        media_info=_media(),
        transcript=[_sentence(0, 0, 10_000, words=[_word("texto", 0, 10_000)])],
    )
    plan = build_beatmap_plan(state, StyleDefinition(style_id="s", name="S"))
    assert plan["schema_version"] == 2
    assert plan["keep_ranges"] == []
    assert plan["remove_ranges"] == []
    assert plan["time_basis"] == "edited"
    Beatmap.model_validate(plan)
    updated, report, _sidecar = apply_beatmap(state, tmp_path, plan)
    assert report.ok is True
    assert updated.media_info is not None


def test_captions_plan_uses_words_for_karaoke(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript = [
        _sentence(
            0,
            0,
            10_000,
            words=[
                _word("primeira", 0, 2_000),
                _word("palavra", 2_000, 5_000),
                _word("final", 5_000, 10_000),
            ],
        )
    ]
    CaptionsPlanStep().run(
        context,
        CaptionsPlanParams(style=CaptionStyle(effect="karaoke_sweep")),
        StepIO(),
    )
    ass = Path(context.artifacts["captions"]).read_text(encoding="utf-8")
    assert r"\kf" in ass


def test_vf_decupage_reports_a_missing_project() -> None:
    from tests.unit.test_agent_mcp import call
    from videoflow.mcp_server.server import build_server

    server = build_server()
    result = call(server, "vf_decupage", {"action": "plan", "project_id": "missing"})
    assert result["ok"] is False


def test_beat_map_path_is_valid_json() -> None:
    # The full MCP path is covered by the project tests; this guards the
    # persisted document shape consumed by ``beat_map_path``.
    state = ProjectState(media_info=_media(), transcript=[])
    plan = build_beatmap_plan(state, StyleDefinition(style_id="s", name="S"))
    encoded = json.dumps(plan)
    assert json.loads(encoded)["schema_version"] == 2


def test_vf_timeline_accepts_beat_map_path(monkeypatch, tmp_path: Path) -> None:
    from tests.unit.test_agent_mcp import call
    from videoflow.application.beatmap_plan import write_beatmap_plan
    from videoflow.application.projects import (
        get_project,
        init_project,
        load_project_state,
        save_project_state,
    )
    from videoflow.mcp_server.server import build_server

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    record, _ = init_project(name="Beat map path", output=tmp_path / "out")
    state = ProjectState(
        media_info=_media(),
        transcript=[
            _sentence(0, 0, 10_000, words=[_word("texto", 0, 10_000)])
        ],
    )
    save_project_state(record, state, bump_revision=False)
    current = load_project_state(get_project(record.project_id))
    plan = build_beatmap_plan(current, StyleDefinition(style_id="s", name="S"))
    write_beatmap_plan(Path(record.output), plan)

    server = build_server()
    result = call(
        server,
        "vf_timeline",
        {
            "action": "apply_beatmap",
            "project_id": record.project_id,
            "beat_map_path": "beat_map.json",
            "dry_run": True,
        },
    )
    assert result["ok"] is True
    assert result["dry_run"] is True


def test_snap_step_persists_flagged_long_cuts(tmp_path: Path) -> None:
    context = _context(tmp_path, duration_frames=930)
    context.speech_intervals = [(0, RATE), (30 * RATE, 31 * RATE)]
    context.transcript = []
    asu = Asu(
        asu_id="ASU_1",
        start_sample=0,
        end_sample=RATE,
        start_sec=0.0,
        end_sec=1.0,
        text="uma",
        words=[
            AsuWord(
                idx=0,
                w="uma",
                start_sample=0,
                end_sample=RATE,
                start_sec=0.0,
                end_sec=1.0,
                p=0.9,
            )
        ],
    )
    context.metadata["asus"] = [asu.model_dump(mode="json")]
    DecupageSnapStep().run(context, SnapParams(min_clip_ms=1), StepIO())
    payload = json.loads(Path(context.artifacts["decupage_report_json"]).read_text())
    assert any(item["duration_sec"] > 15 for item in payload["flagged_long_cuts"])


def test_vf_decupage_run_full_uses_canonical_chain() -> None:
    from videoflow.mcp_server.core_tools.official import register_official_tools

    captured = {}
    calls: dict[str, object] = {}

    def register(fn):
        captured[fn.__name__] = fn
        return fn

    def fake_run(**kwargs):
        calls["steps"] = kwargs["steps"]
        return {"ok": True, "job": {"status": "succeeded"}}

    def noop(**kwargs):
        return {"ok": True}

    tools = {
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
    }
    register_official_tools(register, tools)
    result = captured["vf_decupage"](action="run_full", project_id="missing")
    assert calls["steps"] == [
        "ingest",
        "audio.vad",
        "transcribe",
        "speech.editorial_clean",
        "retakes.cull",
        "decupage.snap",
        "decupage.timeline",
    ]
    assert result["beat_map_path"] == "beat_map.json"
    assert result["flagged_long_cuts"] == []


def test_vf_decupage_can_confirm_no_semantic_discards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from videoflow.mcp_server.core_tools import official
    from videoflow.mcp_server.core_tools.official import register_official_tools

    captured = {}

    def register(fn):
        captured[fn.__name__] = fn
        return fn

    def noop(**kwargs):
        return {"ok": True}

    monkeypatch.setattr(
        official,
        "get_project",
        lambda _project_id: SimpleNamespace(output="/tmp/vf-missing-project"),
    )
    monkeypatch.setattr(
        official,
        "load_project_state",
        lambda _record: SimpleNamespace(
            pipeline=SimpleNamespace(
                metadata={
                    "editorial_clean": {
                        "semantic_status": "delegated",
                        "semantic_candidates": [{"earlier": 0, "later": 1}],
                    }
                }
            )
        ),
    )
    register_official_tools(
        register,
        {
            "vf_beatmap_plan": lambda **kwargs: {
                "ok": True,
                "path": "beat_map.json",
                "plan": {"schema_version": 2},
            },
            "vf_run": lambda **kwargs: {"ok": True, "job": {"status": "succeeded"}},
            "vf_transcript_query": noop,
            "vf_shorts_batch": noop,
            "vf_qa_final": noop,
            "vf_job": noop,
        },
    )
    result = captured["vf_decupage"](
        action="run_full",
        project_id="paula",
        confirm_no_semantic_discards=True,
    )
    assert result["semantic_discards_confirmed"] is True
    assert "pending_semantic_review" not in result


def test_vf_decupage_discard_sentences_delegates_to_the_timeline_tool() -> None:
    from videoflow.mcp_server.core_tools.official import register_official_tools

    captured = {}
    calls: dict[str, object] = {}

    def register(fn):
        captured[fn.__name__] = fn
        return fn

    def fake_timeline(**kwargs):
        calls.update(kwargs)
        return {"ok": True, "discarded_sentence_ids": kwargs["sentence_ids"]}

    def noop(**kwargs):
        return {"ok": True}

    register_official_tools(
        register,
        {
            "vf_timeline": fake_timeline,
            "vf_transcript_query": noop,
            "vf_shorts_batch": noop,
            "vf_qa_final": noop,
            "vf_job": noop,
        },
    )
    result = captured["vf_decupage"](
        action="discard_sentences",
        project_id="paula",
        sentence_ids=[2, 5],
    )
    assert result["ok"] is True
    assert calls == {
        "action": "discard_sentences",
        "project_id": "paula",
        "sentence_ids": [2, 5],
    }


def test_captions_load_words_from_transcript_clean(tmp_path: Path) -> None:
    context = _context(tmp_path)
    path = context.output / "transcript" / "transcript_clean.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = _sentence(
        0,
        0,
        10_000,
        words=[_word("palavra", 0, 10_000)],
    ).model_dump(mode="json")
    path.write_text(json.dumps([row]), encoding="utf-8")
    context.transcript = [_sentence(0, 0, 10_000)]
    CaptionsPlanStep().run(
        context,
        CaptionsPlanParams(style=CaptionStyle(effect="karaoke_sweep")),
        StepIO(),
    )
    ass = Path(context.artifacts["captions"]).read_text(encoding="utf-8")
    assert r"\kf" in ass
