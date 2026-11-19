from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from videoflow.application.editorial_clean import (
    _clipped_word_count,
    _join_words,
    _Rms,
    _sentence_similarity,
    _snap_cuts_to_energy,
    clean_editorial,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, Sentence, WordTiming
from videoflow.steps.base import StepIO
from videoflow.steps.editorial_clean import (
    EditorialCleanParams,
    EditorialCleanStep,
    apply_editorial_clean,
)
from videoflow.steps.retakes import RetakesParams, RetakesStep

RATE = 48_000


def word(
    text: str,
    start_ms: int,
    end_ms: int,
    *,
    probability: float = 0.9,
) -> WordTiming:
    return WordTiming(
        word=text,
        start_sample=round(start_ms * RATE / 1000),
        end_sample=round(end_ms * RATE / 1000),
        probability=probability,
    )


def sentence(
    identifier: int,
    text: str,
    start_ms: int,
    end_ms: int,
    words: list[WordTiming] | None = None,
) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=round(start_ms * RATE / 1000),
        end_sample=round(end_ms * RATE / 1000),
        text=text,
        words=words or [],
    )


class FakeClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
        self.prompts.append(prompt)
        assert schema_name == "videoflow.editorial_clean"
        return self.response


def media(tmp_path: Path) -> MediaInfo:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    return MediaInfo(
        source_path=str(source),
        duration_frames=300,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=RATE,
    )


def context(tmp_path: Path, transcript: list[Sentence]) -> PipelineContext:
    result = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=media(tmp_path),
        transcript=transcript,
        metadata={"transcript_normalized": True, "alignment": {}},
    )
    result.output.mkdir(parents=True, exist_ok=True)
    result.work.mkdir(parents=True, exist_ok=True)
    return result


def test_immediate_word_repetition_keeps_only_the_last() -> None:
    item = sentence(
        0,
        "e o o o modelo",
        0,
        1000,
        [
            word("e", 0, 100),
            word("o", 200, 300),
            word("o", 400, 500),
            word("o", 600, 700),
            word("modelo", 800, 1000),
        ],
    )
    result = clean_editorial([item], semantic=False)
    kept = result.transcript[0]
    assert [item.word for item in kept.words] == ["e", "o", "modelo"]
    assert kept.text == "e o modelo"
    assert result.report["stutters_removed"] == 2
    assert result.report["cut_count"] == 1
    assert result.report["clipped_words"] == 0


def test_phonetic_false_start_is_removed() -> None:
    item = sentence(
        0,
        "para con- configurar",
        0,
        1000,
        [
            word("para", 0, 200),
            word("con-", 300, 430, probability=0.8),
            word("configurar", 500, 900),
        ],
    )
    result = clean_editorial([item], semantic=False)
    kept = result.transcript[0]
    assert [item.word for item in kept.words] == ["para", "configurar"]
    assert kept.text == "para configurar"
    assert result.report["stutters_removed"] == 1


def test_fuzzy_sentence_retake_keeps_the_last_attempt() -> None:
    first = sentence(
        0,
        "Hoje eu vou mostrar como instalar o programa no computador.",
        0,
        4000,
    )
    second = sentence(
        1,
        "Hoje eu vou mostrar como instalar o programa no seu computador.",
        5000,
        9000,
    )
    result = clean_editorial([first, second], semantic=False)
    assert result.discarded_sentence_ids == (0,)
    assert [item.id for item in result.transcript] == [1]
    assert result.report["fuzzy_discards"][0]["keeper_id"] == 1


def test_fuzzy_pass_does_not_discard_changed_numbers_or_protected_content() -> None:
    price = sentence(0, "O preço é 100 reais no link da descrição.", 0, 3000)
    new_price = sentence(1, "O preço é 200 reais no link da descrição.", 4000, 7000)
    result = clean_editorial([price, new_price], semantic=False)
    assert result.discarded_sentence_ids == ()
    assert [item.id for item in result.transcript] == [0, 1]


def test_max_discard_ratio_caps_fuzzy_removals() -> None:
    sentences = [
        sentence(
            index,
            "Hoje eu vou mostrar como instalar o programa no computador.",
            index * 5000,
            index * 5000 + 4000,
        )
        for index in range(10)
    ]
    result = clean_editorial(
        sentences,
        semantic=False,
        max_discard_ratio=0.3,
    )
    assert len(result.discarded_sentence_ids) <= 3


def test_semantic_pass_discards_an_earlier_retake() -> None:
    first = sentence(
        0,
        "Hoje eu vou mostrar como instalar o programa no computador.",
        0,
        4000,
    )
    second = sentence(
        1,
        "Agora eu vou mostrar como configurar o programa no computador.",
        5000,
        9000,
    )
    client = FakeClient(
        {"discard_sentence_ids": [0], "reasoning": "the second attempt replaces the first"}
    )
    result = clean_editorial(
        [first, second],
        client=client,
        fuzzy_similarity=0.99,
        semantic=True,
    )
    assert result.discarded_sentence_ids == (0,)
    assert result.report["semantic_status"] == "applied"
    assert result.report["semantic_windows"] == 1
    assert result.report["semantic_discards"][0]["sentence_id"] == 0
    assert "discard_sentence_ids" in client.prompts[0]


def test_semantic_pass_without_client_is_a_warning() -> None:
    items = [
        sentence(0, "Primeira tentativa do texto.", 0, 2000),
        sentence(1, "Segunda tentativa do texto.", 3000, 5000),
    ]
    result = clean_editorial(items, client=None, semantic=True)
    assert result.report["semantic_status"] == "delegated"
    assert "semantic_candidates" in result.report
    assert any("delegated to OpenCode" in warning for warning in result.report["warnings"])


def test_unknown_semantic_ids_are_ignored() -> None:
    first = sentence(0, "Primeira tentativa do texto.", 0, 2000)
    second = sentence(1, "Segunda tentativa do texto.", 3000, 5000)
    client = FakeClient({"discard_sentence_ids": [99], "reasoning": "bad"})
    result = clean_editorial(
        [first, second],
        client=client,
        fuzzy_similarity=0.99,
        semantic=True,
    )
    assert result.discarded_sentence_ids == ()


def test_energy_snap_does_not_clip_kept_words(tmp_path: Path) -> None:
    pcm = tmp_path / "source.wav"
    with wave.open(str(pcm), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        frames = bytearray()
        for index in range(RATE):
            value = 0
            if 20_000 <= index < 22_000:
                value = 12_000
            frames.extend(int(value).to_bytes(2, "little", signed=True))
        handle.writeframes(bytes(frames))
    item = sentence(
        0,
        "e o o o modelo",
        0,
        1000,
        [
            word("e", 0, 100),
            word("o", 400, 450),
            word("o", 500, 550),
            word("modelo", 800, 900),
        ],
    )
    result = clean_editorial(
        [item],
        semantic=False,
        pcm_path=pcm,
        snap_ms=60,
    )
    assert result.report["clipped_words"] == 0
    assert result.cuts


def test_step_writes_clean_transcript_and_report(tmp_path: Path) -> None:
    transcript = [
        sentence(
            0,
            "e o o o modelo",
            0,
            1000,
            [
                word("e", 0, 100),
                word("o", 200, 300),
                word("o", 400, 500),
                word("modelo", 800, 1000),
            ],
        )
    ]
    ctx = context(tmp_path, transcript)
    report = await_step(ctx)

    assert report["applied"] is True
    assert report["stutters_removed"] == 1
    assert ctx.metadata["editorial_clean"] == report
    assert ctx.metadata["editorial_cuts"]
    assert ctx.artifacts["transcript_clean"]
    assert ctx.artifacts["editorial_clean"]
    clean = json.loads(Path(ctx.artifacts["transcript_clean"]).read_text())
    assert clean[0]["text"] == "e o modelo"
    assert Path(ctx.artifacts["editorial_clean"]).is_file()


def test_step_is_idempotent(tmp_path: Path) -> None:
    transcript = [sentence(0, "texto normal sem repetição.", 0, 1000)]
    ctx = context(tmp_path, transcript)
    first = await_step(ctx)
    second = await_step(ctx)
    assert first == second


def await_step(ctx: PipelineContext) -> dict[str, object]:
    step = EditorialCleanStep()
    step.run(ctx, EditorialCleanParams(semantic=False), StepIO())
    return dict(ctx.metadata["editorial_clean"])


def test_empty_transcript_is_skipped() -> None:
    result = clean_editorial([], semantic=True)
    assert result.report["applied"] is False
    assert result.report["skipped"] == "no transcript"
    assert result.transcript == []


def test_semantic_client_failure_is_a_warning() -> None:
    class BrokenClient:
        def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
            raise RuntimeError("model offline")

    items = [
        sentence(0, "Primeira tentativa do texto.", 0, 2000),
        sentence(1, "Segunda tentativa do texto.", 3000, 5000),
    ]
    result = clean_editorial(items, client=BrokenClient(), semantic=True)
    assert result.report["semantic_status"] == "failed"
    assert any("model offline" in warning for warning in result.report["warnings"])


def test_step_skips_without_transcript(tmp_path: Path) -> None:
    ctx = context(tmp_path, [])
    EditorialCleanStep().run(ctx, EditorialCleanParams(semantic=False), StepIO())
    assert ctx.metadata["editorial_clean"]["applied"] is False
    assert ctx.metadata["editorial_clean"]["skipped"] == "no transcript"


def test_step_can_be_disabled(tmp_path: Path) -> None:
    ctx = context(tmp_path, [sentence(0, "texto normal.", 0, 1000)])
    EditorialCleanStep().run(
        ctx,
        EditorialCleanParams(enabled=False, semantic=False),
        StepIO(),
    )
    assert ctx.metadata["editorial_clean"]["skipped"] == "disabled"


def test_params_reject_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        EditorialCleanParams(semantic_overlap=99)


def test_apply_helper_returns_previous_report(tmp_path: Path) -> None:
    ctx = context(tmp_path, [sentence(0, "texto normal.", 0, 1000)])
    first = apply_editorial_clean(ctx, EditorialCleanParams(semantic=False), StepIO())
    second = apply_editorial_clean(ctx, EditorialCleanParams(semantic=False), StepIO())
    assert first == second


def test_retakes_preserves_editorial_discards_when_culling_is_disabled(
    tmp_path: Path,
) -> None:
    first = sentence(
        0,
        "Hoje eu vou mostrar como instalar o programa no computador.",
        0,
        4000,
    )
    second = sentence(
        1,
        "Hoje eu vou mostrar como instalar o programa no seu computador.",
        5000,
        9000,
    )
    ctx = context(tmp_path, [first, second])
    ctx.speech_intervals = [(0, 10 * RATE)]
    RetakesStep().run(
        ctx,
        RetakesParams(enabled=False, editorial_semantic=False),
        StepIO(),
    )
    assert ctx.discard_sentence_ids == [0]
    assert [item.id for item in ctx.transcript] == [0, 1]
    assert ctx.metadata["editorial_clean"]["applied"] is True


def test_join_words_handles_punctuation_tokens() -> None:
    assert _join_words(
        [
            word("", 0, 5),
            word("hello", 5, 10),
            word(",", 11, 12),
            word("world", 13, 20),
            word(")", 21, 22),
            word("!", 23, 24),
        ]
    ) == "hello, world)!"


def test_semantic_ignores_non_list_values() -> None:
    items = [
        sentence(0, "Primeira tentativa do texto.", 0, 2000),
        sentence(1, "Segunda tentativa do texto.", 3000, 5000),
    ]

    class Client:
        def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
            return {"discard_sentence_ids": "0"}

    result = clean_editorial(
        items,
        client=Client(),
        fuzzy_similarity=0.99,
        semantic=True,
    )
    assert result.discarded_sentence_ids == ()


def test_semantic_requires_a_replacement_sentence() -> None:
    items = [
        sentence(0, "Primeira tentativa do texto.", 0, 2000),
        sentence(1, "Assunto completamente diferente agora.", 3000, 5000),
    ]

    class Client:
        def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
            return {"discard_sentence_ids": [0]}

    result = clean_editorial(
        items,
        client=Client(),
        fuzzy_similarity=0.99,
        semantic=True,
    )
    assert result.discarded_sentence_ids == ()


def test_rms_handles_invalid_wave_file(tmp_path: Path) -> None:
    broken = tmp_path / "broken.wav"
    broken.write_text("not a wave file", encoding="utf-8")
    reader = _Rms(broken, RATE)
    assert reader(0, 10) == 0
    reader.close()


def test_sentence_similarity_handles_empty_text() -> None:
    assert _sentence_similarity(sentence(0, "", 0, 100), sentence(1, "texto", 100, 200)) == (
        0.0,
        0.0,
        0.0,
    )


def test_clipped_word_count_detects_an_overlap() -> None:
    item = sentence(0, "modelo", 0, 1000, [word("modelo", 100, 900)])
    assert _clipped_word_count([item], [(4_800, 5_000)]) == 1


def test_rms_handles_missing_and_non_16_bit_audio(tmp_path: Path) -> None:
    missing = _Rms(tmp_path / "missing.wav", RATE)
    assert missing(0, 100) == 0
    missing.close()

    mono8 = tmp_path / "mono8.wav"
    with wave.open(str(mono8), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(RATE)
        handle.writeframes(b"\x80" * 100)
    reader = _Rms(mono8, RATE)
    assert reader(0, 10) == 0
    reader.close()


def test_snap_with_zero_window_keeps_cuts(tmp_path: Path) -> None:
    pcm = tmp_path / "pcm.wav"
    with wave.open(str(pcm), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b"\x00\x00" * 2000)
    cuts, snapped = _snap_cuts_to_energy(
        [(1000, 1200)],
        pcm_path=pcm,
        sample_rate=RATE,
        snap_ms=0,
        sentences=[],
    )
    assert cuts == [(1000, 1200)]
    assert snapped == 0


def test_semantic_rejects_short_protected_and_unreplaced_candidates() -> None:
    first = sentence(0, "O preço é 100 reais e o link está na descrição.", 0, 2000)
    second = sentence(1, "Ok.", 3000, 3500)
    third = sentence(2, "Hoje eu vou mostrar como instalar o programa.", 4000, 7000)
    client = FakeClient(
        {"discard_sentence_ids": [0, 1, 2], "reasoning": "invalid candidates"}
    )
    result = clean_editorial(
        [first, second, third],
        client=client,
        fuzzy_similarity=0.99,
        semantic_block=3,
        semantic_overlap=0,
    )
    assert result.discarded_sentence_ids == ()
    assert result.report["semantic_discards"] == []


def test_semantic_ignores_malformed_responses() -> None:
    items = [
        sentence(0, "Primeira tentativa do texto.", 0, 2000),
        sentence(1, "Segunda tentativa do texto.", 3000, 5000),
    ]

    class ListClient:
        def complete_json(self, prompt: str, schema_name: str) -> list[object]:
            return []

    class BadValuesClient:
        def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
            return {"discard_sentence_ids": ["not-an-id"]}

    for client in (ListClient(), BadValuesClient()):
        result = clean_editorial(
            items,
            client=client,
            fuzzy_similarity=0.99,
            semantic=True,
        )
        assert result.discarded_sentence_ids == ()


def test_step_cache_outputs_lists_both_artifacts(tmp_path: Path) -> None:
    ctx = context(tmp_path, [sentence(0, "texto normal.", 0, 1000)])
    step = EditorialCleanStep()
    step.run(ctx, EditorialCleanParams(semantic=False), StepIO())
    paths = step.cache_outputs(ctx)
    assert len(paths) == 2
    assert all(path.is_file() for path in paths)


def test_apply_normalizes_before_cleaning(tmp_path: Path) -> None:
    transcript = [
        sentence(
            0,
            "Hoje eu vou mostrar como instalar o programa no computador.",
            0,
            4000,
        ),
        sentence(
            1,
            "Hoje eu vou mostrar como instalar o programa no computador.",
            4000,
            8000,
        ),
    ]
    ctx = context(tmp_path, transcript)
    ctx.metadata = {}
    report = apply_editorial_clean(
        ctx,
        EditorialCleanParams(semantic=False),
        StepIO(),
    )
    assert report["applied"] is True
    assert ctx.metadata["transcript_normalized"] is True


def test_timeline_receives_editorial_cuts_and_padding(tmp_path: Path) -> None:
    from videoflow.steps.timeline import TimelineParams, TimelineStep

    item = sentence(
        0,
        "e o o o modelo",
        0,
        1000,
        [
            word("e", 0, 100),
            word("o", 200, 300),
            word("o", 400, 500),
            word("modelo", 800, 1000),
        ],
    )
    ctx = context(tmp_path, [item])
    ctx.speech_intervals = [(0, 3000 * RATE // 1000)]
    EditorialCleanStep().run(ctx, EditorialCleanParams(semantic=False), StepIO())
    TimelineStep().run(
        ctx,
        TimelineParams(
            cut_mode="hard",
            use_transcript_spans=True,
            noise_filter="off",
            remove_impulsive_noise=False,
            keep_untranscribed=False,
            detect_repeats=False,
        ),
        StepIO(),
    )
    assert ctx.metadata["editorial_cuts"]
    assert ctx.metadata["speech_pad_before_ms"] == 110
    assert ctx.metadata["speech_pad_after_ms"] == 190
    assert ctx.state is not None
    assert ctx.state.video_segments
