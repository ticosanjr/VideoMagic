"""Short selection refinements, hooks, fillers, reporting, and caption edges."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application import shorts
from videoflow.application.shorts import (
    CaptionLine,
    CaptionStyle,
    ShortClip,
    caption_lines,
    previous_shorts_from_report,
    select_shorts,
    sentence_events,
    slice_pieces,
)
from videoflow.domain.errors import InvalidRetakeIdsError
from videoflow.domain.state import Sentence, WordTiming

RATE = 48000


def sentence(
    item_id: int, start_sec: float = 0.0, end_sec: float = 4.0, text: str | None = None
) -> Sentence:
    return Sentence(
        id=item_id,
        start_sample=int(start_sec * RATE),
        end_sample=int(end_sec * RATE),
        text=text or f"line {item_id} here",
    )


def line_of_six() -> list[Sentence]:
    return [sentence(index, index * 4, index * 4 + 4) for index in range(6)]


class FakeLlm:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete_json(self, prompt: str, schema: str) -> dict[str, object]:
        self.prompts.append(prompt)
        return self.payload


def proposals(*ids: list[int], hook: int | None = None, title: str = "Short") -> dict:
    return {
        "clips": [
            {"title": title, "sentence_ids": ids, "hook_sentence_id": hook}
        ],
        "reasoning": "test",
    }


def test_unknown_modes_fall_back_with_warnings() -> None:
    warnings: list[str] = []

    clips = select_shorts(
        line_of_six(),
        min_samples=2 * RATE,
        max_samples=8 * RATE,
        count=1,
        prompt_mode="replace-ish",
        hook_mode="spin",
        warnings=warnings,
    )

    assert clips
    assert any("Unknown prompt_mode" in item for item in warnings)
    assert any("Unknown hook_mode" in item for item in warnings)


def test_refine_without_previous_falls_back() -> None:
    warnings: list[str] = []

    select_shorts(
        line_of_six(),
        min_samples=2 * RATE,
        max_samples=8 * RATE,
        count=1,
        prompt_mode="refine",
        warnings=warnings,
    )

    assert any("without a previous selection" in item for item in warnings)


def test_empty_input_and_zero_count_return_nothing() -> None:
    assert (
        select_shorts([], min_samples=1, max_samples=2, count=1) == []
    )
    assert (
        select_shorts(line_of_six(), min_samples=1, max_samples=2, count=0) == []
    )


def test_llm_without_a_client_warns_and_uses_heuristics() -> None:
    warnings: list[str] = []

    clips = select_shorts(
        line_of_six(),
        min_samples=2 * RATE,
        max_samples=8 * RATE,
        count=1,
        selection_mode="llm",
        warnings=warnings,
    )

    assert clips
    assert any("no client is configured" in item for item in warnings)


def test_llm_empty_selection_falls_back() -> None:
    warnings: list[str] = []
    client = FakeLlm({"clips": [], "reasoning": "none"})

    clips = select_shorts(
        line_of_six(),
        min_samples=2 * RATE,
        max_samples=8 * RATE,
        count=1,
        selection_mode="llm",
        client=client,
        warnings=warnings,
    )

    assert clips
    assert any("no usable shorts" in item for item in warnings)


def test_llm_clip_removed_by_culls_is_reported() -> None:
    warnings: list[str] = []
    client = FakeLlm(proposals(0, 1))

    clips = select_shorts(
        line_of_six(),
        min_samples=2 * RATE,
        max_samples=16 * RATE,
        count=1,
        selection_mode="llm",
        client=client,
        cuts=[(0, 7 * RATE)],
        warnings=warnings,
    )

    assert any("after culls" in item for item in warnings)
    assert all(clip.sentence_ids != (0, 1) for clip in clips)


def test_llm_scores_energy_scenes_and_hook() -> None:
    client = FakeLlm(proposals(0, 1, hook=5))

    clips = select_shorts(
        line_of_six(),
        min_samples=2 * RATE,
        max_samples=16 * RATE,
        count=1,
        selection_mode="llm",
        client=client,
        energy_intervals=[(0, 2 * RATE), (3 * RATE, 5 * RATE)],
        scene_intervals=[(0, RATE)],
    )
    clip = clips[0]

    assert clip.energy_peaks == 2
    assert clip.scene_changes == 1
    assert clip.hook_sentence_id in {0, 1}
    assert clip.virality_score > 0
    assert dict(clip.score_breakdown)["audio_energy"] == 3.0


def test_llm_respects_a_hook_inside_the_clip() -> None:
    client = FakeLlm(proposals(0, 1, hook=1))

    [clip] = select_shorts(
        line_of_six(),
        min_samples=2 * RATE,
        max_samples=16 * RATE,
        count=1,
        selection_mode="llm",
        client=client,
    )

    assert clip.hook_sentence_id == 1


def test_llm_rejects_unknown_sentence_ids() -> None:
    client = FakeLlm(proposals(99))

    with pytest.raises(InvalidRetakeIdsError):
        select_shorts(
            line_of_six(),
            min_samples=2 * RATE,
            max_samples=16 * RATE,
            count=1,
            selection_mode="llm",
            client=client,
        )


def test_llm_refine_prompt_contains_previous_context() -> None:
    previous = [
        ShortClip(
            title="Old",
            start_sample=0,
            end_sample=4 * RATE,
            sentence_ids=(0,),
            pieces=((0, 4 * RATE),),
        )
    ]
    client = FakeLlm(proposals(0, 1))

    select_shorts(
        line_of_six(),
        min_samples=2 * RATE,
        max_samples=16 * RATE,
        count=1,
        selection_mode="llm",
        client=client,
        prompt_mode="refine",
        previous=previous,
        reprompt="more energy",
    )

    assert "Old (sentences [0])" in client.prompts[0]
    assert "more energy" in client.prompts[0]


def test_merge_clips_skips_overlaps_and_duplicates() -> None:
    primary = [
        ShortClip("A", 0, 4 * RATE, (0,), ((0, 4 * RATE),)),
    ]
    fallback = [
        ShortClip("B", 2 * RATE, 6 * RATE, (1,), ((2 * RATE, 6 * RATE),)),
        ShortClip("C", 0, 4 * RATE, (0,), ((0, 4 * RATE),)),
        ShortClip("D", 8 * RATE, 12 * RATE, (2,), ((8 * RATE, 12 * RATE),)),
    ]

    merged = shorts._merge_clips(primary, fallback, 2)

    assert [clip.title for clip in merged] == ["A", "D"]


def test_previous_shorts_report_is_parsed_defensively(tmp_path: Path) -> None:
    assert previous_shorts_from_report(tmp_path / "missing.json") == []

    path = tmp_path / "shorts.json"
    path.write_text("not json", encoding="utf-8")
    assert previous_shorts_from_report(path) == []

    path.write_text(
        json.dumps(
            {
                "clips": [
                    {
                        "title": "Good",
                        "start_sample": 0,
                        "end_sample": 48000,
                        "sentence_ids": [0, 1],
                        "pieces": [[0, 48000]],
                        "score": 4.5,
                    },
                    "not a dict",
                    {"title": "No pieces", "sentence_ids": [0]},
                    {"title": "Empty", "sentence_ids": [], "pieces": []},
                    {"title": "Bad", "sentence_ids": ["x"], "pieces": [[0, 1]]},
                ]
            }
        ),
        encoding="utf-8",
    )

    clips = previous_shorts_from_report(path)

    assert len(clips) == 1
    assert clips[0].title == "Good"
    assert clips[0].pieces == ((0, 48000),)
    assert clips[0].score == 4.5


def test_fillers_are_removed_from_pieces() -> None:
    words = [
        WordTiming(word="eh", start_sample=0, end_sample=RATE, probability=0.9),
        WordTiming(word="real", start_sample=RATE, end_sample=2 * RATE, probability=0.9),
    ]
    item = sentence(0, 0, 2, "eh real")
    item.words = words
    clip = ShortClip("A", 0, 2 * RATE, (0,), ((0, 2 * RATE),))

    [updated] = shorts._apply_fillers([clip], [item], ["eh"])

    assert updated.filler_words_removed == ("eh",)
    assert updated.pieces == ((RATE, 2 * RATE),)

    [unchanged] = shorts._apply_fillers([clip], [item], [])
    assert unchanged.pieces == clip.pieces


def test_fillers_keep_the_clip_when_nothing_remains() -> None:
    item = sentence(0, 0, RATE, "eh")
    item.words = [WordTiming(word="eh", start_sample=0, end_sample=RATE, probability=0.9)]
    clip = ShortClip("A", 0, RATE, (0,), ((0, RATE),))

    [updated] = shorts._apply_fillers([clip], [item], ["eh"])

    assert updated.pieces == clip.pieces


def test_hooks_repeat_and_reorder() -> None:
    sentences = line_of_six()
    clip = ShortClip("A", 4 * RATE, 12 * RATE, (1, 2), ((4 * RATE, 12 * RATE),))
    clip = ShortClip(
        "A",
        clip.start_sample,
        clip.end_sample,
        clip.sentence_ids,
        clip.pieces,
        hook_sentence_id=1,
    )

    [repeated] = shorts._apply_hooks([clip], sentences, "repeat", 1, 8 * RATE)
    [reordered] = shorts._apply_hooks([clip], sentences, "reorder", 1, 8 * RATE)

    assert repeated.pieces[0] == (4 * RATE, 8 * RATE)
    assert repeated.hook_text == "line 1 here"
    assert reordered.pieces[0] == (4 * RATE, 8 * RATE)
    assert reordered.pieces[1:] == ((8 * RATE, 12 * RATE),)

    [unchanged] = shorts._apply_hooks([clip], sentences, "off", 1, 8 * RATE)
    assert unchanged is clip


def test_proportional_words_split_by_length() -> None:
    words = shorts._proportional_words("aa bbb", 0.0, 1.0)

    assert [word[2] for word in words] == ["aa", "bbb"]
    assert words[0][1] == pytest.approx(0.4)
    assert words[-1][1] == 1.0
    assert shorts._proportional_words("", 0.0, 1.0) == ()
    assert shorts._proportional_words("words", 1.0, 1.0) == ()


def test_brand_uppercase_and_censor_text() -> None:
    style = CaptionStyle(
        uppercase=True,
        brand_vocabulary={"videoflow": "VideoFlow"},
        censor_enabled=True,
        censor_words=["merda"],
    )

    value = shorts._display_text("videoflow é merda", style)

    assert value == "VIDEOFLOW É ***"


def test_censor_disabled_and_empty_terms() -> None:
    assert shorts._censor_text("merda", CaptionStyle()) == "merda"
    style = CaptionStyle(censor_enabled=True, censor_words=["", " "])
    assert shorts._censor_text("merda", style) == "merda"


def test_keyword_highlight_and_emoji_mapping() -> None:
    style = CaptionStyle(
        keyword_highlight_enabled=True,
        keyword_words=["Resultado"],
        emoji_enabled=True,
        emoji_map={"resultado": "🚀"},
    )

    value = shorts._sentence_text("resultado final", style)

    assert "\\c&H" in value
    assert "resultado 🚀" in value.casefold()
    auto = shorts._sentence_text("resultado resultado final", CaptionStyle(
        keyword_highlight_enabled=True
    ))
    assert "\\c&H" in auto


def test_karaoke_text_adds_lead_gap_and_sweep_tag() -> None:
    line = CaptionLine(
        start=1.0,
        end=3.0,
        text="hi there",
        words=((1.2, 2.0, "hi"), (2.0, 3.0, "there")),
    )
    default = shorts._karaoke_text(line, CaptionStyle())
    sweep = shorts._karaoke_text(line, CaptionStyle(animation="sweep"))

    assert default.startswith("{\\k20}")
    assert sweep.startswith("{\\kf20}")
    assert default.endswith("there")
    assert "hi " in default


def test_colour_helpers_clamp_opacity() -> None:
    assert shorts._ass_rgb("#112233") == "332211"
    assert shorts._ass_color("#FFFFFF", 1.0).startswith("&H00FFFFFF")
    assert shorts._ass_color("#FFFFFF", 0.0).startswith("&HFFFFFFFF")
    assert shorts._ass_color("#FFFFFF", 2.0).startswith("&H00FFFFFF")


def test_slice_pieces_trims_and_rejects_empty_ranges() -> None:
    pieces = [(0, 10), (20, 30), (40, 50)]

    assert slice_pieces(pieces, -1, 5) == []
    assert slice_pieces(pieces, 5, 5) == []
    assert slice_pieces(pieces, 5, 25) == [(5, 10), (20, 30), (40, 45)]
    assert slice_pieces(pieces, 0, 1000) == pieces


def test_caption_events_follow_the_concatenated_timeline() -> None:
    events = sentence_events([sentence(0, 0, 2)], [(0, RATE), (RATE, 2 * RATE)], sample_rate=RATE)

    assert [event[2] for event in events] == ["line 0 here", "line 0 here"]
    assert events[0][0] == 0.0
    assert events[1][0] == pytest.approx(1.0)


def test_caption_lines_support_sentence_word_mode() -> None:
    item = sentence(0, 0, 2, "hello world")
    item.words = [
        WordTiming(word="hello", start_sample=0, end_sample=RATE, probability=0.9),
        WordTiming(word="world", start_sample=RATE, end_sample=2 * RATE, probability=0.9),
    ]

    [line] = caption_lines(
        [item], [(0, 2 * RATE)], sample_rate=RATE, word_timing="sentence"
    )

    assert line.words == ()
    assert line.text == "hello world"
