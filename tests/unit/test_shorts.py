import json

import pytest

from videoflow.application.shorts import (
    CaptionStyle,
    build_ass,
    build_ass_lines,
    caption_lines,
    select_shorts,
    sentence_events,
    slugify,
)
from videoflow.domain.errors import InvalidRetakeIdsError
from videoflow.domain.state import Sentence

RATE = 48000


def sentence(item_id: int, start_sec: int, end_sec: int, text: str | None = None) -> Sentence:
    return Sentence(
        id=item_id,
        start_sample=start_sec * RATE,
        end_sample=end_sec * RATE,
        text=text or f"line {item_id}",
    )


def test_deterministic_windows_are_non_overlapping_and_bounded() -> None:
    sentences = [sentence(index, index * 10, (index + 1) * 10) for index in range(4)]
    clips = select_shorts(
        sentences,
        min_samples=10 * RATE,
        max_samples=25 * RATE,
        count=2,
        sample_rate=RATE,
    )
    assert len(clips) == 2
    assert (clips[0].start_sample, clips[0].end_sample) == (0, 20 * RATE)
    assert (clips[1].start_sample, clips[1].end_sample) == (20 * RATE, 40 * RATE)
    assert clips[0].duration_samples == 20 * RATE


def test_cuts_can_drop_a_window_below_the_minimum() -> None:
    sentences = [sentence(0, 0, 30)]
    clips = select_shorts(
        sentences,
        min_samples=25 * RATE,
        max_samples=40 * RATE,
        count=1,
        sample_rate=RATE,
        cuts=[(5 * RATE, 15 * RATE)],
    )
    assert clips == []


def test_no_usable_window_reports_a_warning() -> None:
    warnings: list[str] = []
    clips = select_shorts(
        [sentence(0, 0, 5)],
        min_samples=10 * RATE,
        max_samples=30 * RATE,
        count=1,
        sample_rate=RATE,
        warnings=warnings,
    )
    assert clips == []
    assert warnings


def test_llm_window_is_validated_and_used() -> None:
    sentences = [sentence(0, 0, 10), sentence(1, 10, 20)]

    class Client:
        def complete_json(self, prompt: str, schema_name: str) -> dict:
            assert "sentence_ids" in prompt
            return {"clips": [{"title": "The hook", "sentence_ids": [0, 1]}], "reasoning": "ok"}

    clips = select_shorts(
        sentences,
        min_samples=10 * RATE,
        max_samples=30 * RATE,
        count=1,
        sample_rate=RATE,
        client=Client(),  # type: ignore[arg-type]
    )
    assert len(clips) == 1
    assert clips[0].title == "The hook"
    assert clips[0].pieces == ((0, 20 * RATE),)


def test_llm_unknown_id_is_rejected() -> None:
    class Client:
        def complete_json(self, prompt: str, schema_name: str) -> dict:
            return {"clips": [{"title": "bad", "sentence_ids": [9]}], "reasoning": "x"}

    with pytest.raises(InvalidRetakeIdsError):
        select_shorts(
            [sentence(0, 0, 10)],
            min_samples=1,
            max_samples=20 * RATE,
            count=1,
            sample_rate=RATE,
            client=Client(),  # type: ignore[arg-type]
        )


def test_ass_times_and_text_are_escaped() -> None:
    ass = build_ass([(0, 1.25, "hello {world}"), (3661.5, 3662, "line\\two")])
    assert "0:00:01.25" in ass
    assert "1:01:01.50" in ass
    assert "hello (world)" in ass
    assert "line\\\\two" in ass


def test_sentence_events_follow_concatenated_pieces() -> None:
    sentences = [sentence(0, 0, 2), sentence(1, 4, 6)]
    events = sentence_events(sentences, [(0, 1 * RATE), (1 * RATE, 2 * RATE)], sample_rate=RATE)
    # The first sentence is split across the two pieces; both events start at 0.
    assert events[0][0] == 0
    assert events[0][1] == 1
    assert events[1][0] == 1
    assert events[1][1] == 2


def test_slug_is_safe_and_indexed() -> None:
    assert slugify("The Hook: AI & You!", 1) == "01-the-hook-ai-you"
    assert slugify("", 2) == "02-short"


def test_karaoke_ass_uses_word_timings_and_style() -> None:
    from videoflow.domain.state import WordTiming

    sentence = Sentence(
        id=0,
        start_sample=0,
        end_sample=2 * RATE,
        text="Hello world.",
        words=[
            WordTiming(word="Hello", start_sample=0, end_sample=RATE, probability=1.0),
            WordTiming(word="world.", start_sample=RATE, end_sample=2 * RATE, probability=1.0),
        ],
    )
    lines = caption_lines([sentence], [(0, 2 * RATE)], sample_rate=RATE)
    ass = build_ass_lines(
        lines,
        style=CaptionStyle(
            font_family="DejaVu Sans",
            font_size=80,
            primary_color="#FFFFFF",
            highlight_color="#FFD400",
            background_color="#112233",
            background_opacity=0.5,
            animation="sweep",
            position_x=0.5,
            position_y=0.8,
        ),
    )
    assert "DejaVu Sans" in ass
    assert "&H80332211" in ass
    assert "{\\kf100}Hello" in ass
    assert "{\\kf100}world." in ass
    assert "\\pos(540,1536)" in ass


def test_caption_lines_support_proportional_fallback() -> None:
    line = caption_lines(
        [Sentence(id=0, start_sample=0, end_sample=RATE, text="one two")],
        [(0, RATE)],
        sample_rate=RATE,
        word_timing="proportional",
    )[0]
    assert line.words[0][2] == "one"
    assert line.words[1][2] == "two"
    assert line.words[0][0] == 0.0
    assert line.words[-1][1] == 1.0


def test_heuristic_selection_prefers_impactful_windows() -> None:
    sentences = [
        sentence(0, 0, 20, "Today we are here."),
        sentence(1, 20, 40, "This is the biggest mistake and the secret result!"),
        sentence(2, 40, 60, "And that is why this matters: 90% of people fail."),
        sentence(3, 60, 80, "Thanks for watching."),
    ]
    clips = select_shorts(
        sentences,
        min_samples=10 * RATE,
        max_samples=40 * RATE,
        count=3,
        min_clips=3,
        selection_mode="heuristic",
        sample_rate=RATE,
    )
    assert len(clips) >= 2
    assert any("mistake" in clip.title for clip in clips)


def test_ass_play_resolution_follows_the_aspect() -> None:
    ass = build_ass([(0, 1.0, "hello")], width=1080, height=1080)
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1080" in ass


def test_short_dimensions_cover_supported_aspects() -> None:
    from videoflow.application.shorts import short_dimensions

    assert short_dimensions("9:16") == (1080, 1920)
    assert short_dimensions("1:1") == (1080, 1080)
    assert short_dimensions("16:9") == (1920, 1080)
    assert short_dimensions("unknown") == (1080, 1920)


def test_slice_pieces_trims_an_assembled_short() -> None:
    from videoflow.application.shorts import slice_pieces

    pieces = [(0, 10), (20, 30)]
    assert slice_pieces(pieces, 0, 20) == [(0, 10), (20, 30)]
    assert slice_pieces(pieces, 5, 15) == [(5, 10), (20, 25)]
    assert slice_pieces(pieces, 5, 25) == [(5, 10), (20, 30)]
    assert slice_pieces(pieces, 10, 20) == [(20, 30)]
    assert slice_pieces(pieces, 10, 10) == []
    assert slice_pieces(pieces, 25, 25) == []


def test_prompt_biases_heuristic_selection() -> None:
    sentences = [
        sentence(0, 0, 10, "This cooking pasta recipe is simple."),
        sentence(1, 10, 20, "The finance market crashed today."),
        sentence(2, 20, 30, "Cooking with fresh basil changes everything."),
    ]
    clips = select_shorts(
        sentences,
        min_samples=5 * RATE,
        max_samples=10 * RATE,
        count=1,
        sample_rate=RATE,
        selection_mode="heuristic",
        prompt="cooking basil",
    )
    assert len(clips) == 1
    assert clips[0].sentence_ids in {(0,), (2,)}


def test_llm_prompt_receives_focus_and_previous_selection() -> None:
    from videoflow.application.shorts import ShortClip

    sentences = [sentence(0, 0, 10), sentence(1, 10, 20)]
    previous = [
        ShortClip(
            title="Old clip",
            start_sample=0,
            end_sample=10 * RATE,
            sentence_ids=(0,),
            pieces=((0, 10 * RATE),),
        )
    ]

    class Client:
        def complete_json(self, prompt: str, schema_name: str) -> dict:
            assert "cooking" in prompt
            assert "more energy" in prompt
            assert "Old clip" in prompt
            return {
                "clips": [{"title": "Refined", "sentence_ids": [1]}],
                "reasoning": "matches the focus",
            }

    clips = select_shorts(
        sentences,
        min_samples=5 * RATE,
        max_samples=20 * RATE,
        count=1,
        sample_rate=RATE,
        client=Client(),  # type: ignore[arg-type]
        prompt="cooking",
        reprompt="more energy",
        prompt_mode="refine",
        previous=previous,
    )
    assert clips[0].title == "Refined"


def test_previous_shorts_loader_reads_a_completed_report(tmp_path) -> None:
    from videoflow.application.shorts import ShortClip, previous_shorts_from_report

    original = ShortClip(
        title="Cooking",
        start_sample=0,
        end_sample=10 * RATE,
        sentence_ids=(0, 1),
        pieces=((0, 10 * RATE),),
        score=3.5,
    )
    report = tmp_path / "shorts.json"
    report.write_text(
        json.dumps({"ok": True, "clips": [original.to_dict(RATE)]}), encoding="utf-8"
    )
    loaded = previous_shorts_from_report(report)
    assert len(loaded) == 1
    assert loaded[0].title == "Cooking"
    assert loaded[0].sentence_ids == (0, 1)
    assert loaded[0].pieces == ((0, 10 * RATE),)


def test_reprompt_refine_can_change_the_topic() -> None:
    sentences = [
        sentence(0, 0, 10, "Cooking pasta with fresh basil."),
        sentence(1, 10, 20, "The finance market crashed after the bank decision."),
    ]
    first = select_shorts(
        sentences,
        min_samples=5 * RATE,
        max_samples=10 * RATE,
        count=1,
        sample_rate=RATE,
        selection_mode="heuristic",
        prompt="finance bank",
    )
    refined = select_shorts(
        sentences,
        min_samples=5 * RATE,
        max_samples=10 * RATE,
        count=1,
        sample_rate=RATE,
        selection_mode="heuristic",
        prompt="finance bank",
        prompt_mode="refine",
        reprompt="cooking basil",
        previous=first,
    )
    assert first[0].sentence_ids == (1,)
    assert refined[0].sentence_ids in {(0,), (1,)}
    assert refined[0].sentence_ids == (0,)


def test_auto_hook_metadata_and_repeat() -> None:
    sentences = [
        sentence(0, 0, 10, "A calm introduction."),
        sentence(1, 10, 20, "The biggest secret mistake changed everything!"),
    ]
    metadata = select_shorts(
        sentences,
        min_samples=5 * RATE,
        max_samples=10 * RATE,
        count=1,
        sample_rate=RATE,
        selection_mode="heuristic",
        hook_mode="metadata",
    )
    assert metadata[0].hook_sentence_id == 1
    assert "secret" in (metadata[0].hook_text or "")
    repeated = select_shorts(
        sentences,
        min_samples=5 * RATE,
        max_samples=10 * RATE,
        count=1,
        sample_rate=RATE,
        selection_mode="heuristic",
        hook_mode="repeat",
    )
    assert len(repeated[0].pieces) == 2
    assert repeated[0].pieces[0] == (10 * RATE, 20 * RATE)
    assert repeated[0].duration_samples > 10 * RATE


def test_virality_score_has_a_transparent_breakdown() -> None:
    sentences = [sentence(0, 0, 10, "Why does this secret result work? 42!")]
    clips = select_shorts(
        sentences,
        min_samples=5 * RATE,
        max_samples=10 * RATE,
        count=1,
        sample_rate=RATE,
        selection_mode="heuristic",
        prompt="secret result",
    )
    assert clips[0].virality_score > 0
    breakdown = dict(clips[0].score_breakdown)
    assert breakdown["question"] == 4.0
    assert breakdown["prompt"] > 0


def test_caption_censor_masks_words_without_changing_timing() -> None:
    from videoflow.application.shorts import CaptionLine, CaptionStyle, build_ass_lines

    style = CaptionStyle(censor_enabled=True, censor_words=["merda"], censor_replacement="***")
    ass = build_ass_lines(
        [CaptionLine(start=0, end=1, text="Que merda de dia")],
        style=style,
    )
    assert "***" in ass
    assert "merda" not in ass.lower()


def test_filler_removal_trims_word_intervals() -> None:
    from videoflow.domain.state import WordTiming

    words = [
        WordTiming(word="um", start_sample=0, end_sample=RATE, probability=1.0),
        WordTiming(word="hello", start_sample=RATE, end_sample=2 * RATE, probability=1.0),
        WordTiming(word="um", start_sample=2 * RATE, end_sample=3 * RATE, probability=1.0),
        WordTiming(word="world", start_sample=3 * RATE, end_sample=9 * RATE, probability=1.0),
    ]
    sentences = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=9 * RATE,
            text="um hello um world",
            words=words,
        )
    ]
    clips = select_shorts(
        sentences,
        min_samples=5 * RATE,
        max_samples=10 * RATE,
        count=1,
        sample_rate=RATE,
        selection_mode="heuristic",
        remove_fillers=True,
        filler_words=["um"],
    )
    assert clips[0].pieces == ((RATE, 2 * RATE), (3 * RATE, 9 * RATE))
    assert clips[0].filler_words_removed == ("um", "um")
