from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, ProjectState, Sentence, WordTiming
from videoflow.engine.recipes import builtin_recipe
from videoflow.steps import registry
from videoflow.steps.alignment import DriftCorrectionStep, DriftParams
from videoflow.steps.audio_duck import AudioDuckStep, DuckParams
from videoflow.steps.base import StepIO
from videoflow.steps.broll_master import BrollMasterParams, BrollMasterStep
from videoflow.steps.motion import MotionParams, MotionRenderStep
from videoflow.steps.narrative import NarrativeBeatsStep, NarrativeParams
from videoflow.steps.rules_memory import RulesMemoryParams, RulesMemoryStep
from videoflow.steps.vision_qa import VisionQaParams, VisionQaStep


def _context(tmp_path: Path) -> PipelineContext:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    return PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=MediaInfo(
            source_path=str(source),
            duration_frames=300,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48_000,
        ),
        state=ProjectState(
            media_info=MediaInfo(
                source_path=str(source),
                duration_frames=300,
                fps_num=30,
                fps_den=1,
                width=640,
                height=360,
                audio_sample_rate=48_000,
            )
        ),
    )


def _sentence(item_id: int, start: int, end: int) -> Sentence:
    return Sentence(
        id=item_id,
        start_sample=start,
        end_sample=end,
        text="O modelo novo chegou e mudou o jogo.",
        words=[
            WordTiming(
                word="modelo",
                start_sample=start,
                end_sample=end,
                probability=0.9,
            )
        ],
    )


def test_drift_correction_shifts_words_and_clamps(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript = [_sentence(0, 9600, 14400)]
    DriftCorrectionStep().run(context, DriftParams(offset_ms=200), StepIO())
    word = context.transcript[0].words[0]
    assert word.start_sample == 0
    assert word.end_sample == 4800
    assert context.artifacts["drift_report"]


def test_narrative_beats_builds_blocks_and_entities(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript = [
        _sentence(index, index * 10000, (index + 1) * 10000) for index in range(12)
    ]
    NarrativeBeatsStep().run(
        context,
        NarrativeParams(min_block_words=20, max_block_words=60),
        StepIO(),
    )
    blocks = context.metadata["narrative_beats"]
    assert blocks
    assert blocks[0]["narrative_beat"] == "hook"
    assert Path(context.artifacts["narrative_entities"]).is_file()


def test_broll_master_matches_local_assets(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "modelo-novo.mp4").write_bytes(b"fixture")
    context.metadata["narrative_beats"] = [
        {
            "context_block_id": "block_001",
            "start_sec": 0.0,
            "end_sec": 10.0,
            "text": "O modelo novo chegou.",
        }
    ]
    BrollMasterStep().run(
        context,
        BrollMasterParams(asset_dir=str(assets), max_per_block=1),
        StepIO(),
    )
    assert context.metadata["broll_plan"]["block_001"]
    assert Path(context.artifacts["broll_plan"]).is_file()


def test_audio_duck_is_a_safe_noop_without_music(tmp_path: Path) -> None:
    context = _context(tmp_path)
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"fixture")
    context.artifacts["audio_master"] = str(master)
    AudioDuckStep().run(context, DuckParams(), StepIO())
    assert context.metadata["audio_duck"]["applied"] is False
    assert context.artifacts["audio_master"] == str(master)


def test_rules_memory_dedupes_and_writes(tmp_path: Path) -> None:
    context = _context(tmp_path)
    RulesMemoryStep().run(
        context,
        RulesMemoryParams(
            paths=["agents.md"],
            rules=["music_ducking_level = -10dB", "music_ducking_level = -12dB"],
        ),
        StepIO(),
    )
    text = (context.output / "agents.md").read_text(encoding="utf-8")
    assert "music_ducking_level = -12dB" in text
    assert text.count("music_ducking_level") == 1


def test_motion_and_vision_shells_write_plans(tmp_path: Path) -> None:
    context = _context(tmp_path)
    MotionRenderStep().run(context, MotionParams(), StepIO())
    VisionQaStep().run(context, VisionQaParams(), StepIO())
    assert Path(context.artifacts["motion_plan"]).is_file()
    assert Path(context.artifacts["vision_qa"]).is_file()


def test_master_recipe_graph_and_params_are_valid() -> None:
    recipe = builtin_recipe("autonomous_studio_master").with_variables()
    recipe.validate_graph(
        known_types=registry.step_types(),
        requires_by_type=registry.requirements_by_type(),
    )
    types = {step.type for step in recipe.steps}
    assert {
        "edit.drift",
        "narrative.beats",
        "broll.plan_master",
        "audio.duck",
        "rules.memory",
        "motion.render",
        "qa.vision",
    } <= types
    for step in recipe.steps:
        registry.get_step(step.type).validate_params(step.params)


def test_broll_master_falls_back_to_transcript_blocks(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript = [
        _sentence(index, index * 10_000, (index + 1) * 10_000) for index in range(4)
    ]
    BrollMasterStep().run(context, BrollMasterParams(), StepIO())
    plan = context.metadata["broll_plan"]
    assert list(plan) == ["block_001"]
    assert plan["block_001"] == []


def test_narrative_model_merge_overrides_beats(tmp_path: Path) -> None:
    class Client:
        def complete_json(self, prompt: str, schema: str) -> dict:
            return {
                "blocks": [
                    {
                        "context_block_id": "block_001",
                        "narrative_beat": "proof",
                        "extracted_entities": {"people": [{"raw_mention": "Ana"}]},
                    }
                ]
            }

    context = _context(tmp_path)
    context.transcript = [
        _sentence(index, index * 10_000, (index + 1) * 10_000) for index in range(4)
    ]
    NarrativeBeatsStep().run(
        context,
        NarrativeParams(provider_id="fake", min_block_words=20, max_block_words=80),
        StepIO(llm_client=Client()),
    )
    block = context.metadata["narrative_beats"][0]
    assert block["narrative_beat"] == "proof"
    assert block["extracted_entities"]["people"] == [{"raw_mention": "Ana"}]


def test_audio_duck_applies_with_a_music_bed(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from videoflow.steps import audio_duck as module

    context = _context(tmp_path)
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"dialogue")
    music = tmp_path / "music.wav"
    music.write_bytes(b"music")
    context.artifacts["audio_master"] = str(master)

    def fake_run(command, capture_output=True, text=True):
        Path(command[-1]).write_bytes(b"mix")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "find_binary", lambda _name: "ffmpeg")
    AudioDuckStep().run(
        context,
        DuckParams(music_path=str(music)),
        StepIO(),
    )
    assert context.metadata["audio_duck"]["applied"] is True
    assert Path(context.artifacts["audio_mix"]).is_file()
