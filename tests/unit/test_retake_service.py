from videoflow.application.retakes import (
    cull_intervals,
    cull_retakes,
    inactive_spans_for_discards,
    subtract_spans,
)
from videoflow.domain.state import Sentence


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete_json(self, prompt: str, schema_name: str) -> dict:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def sentence(item_id: int, text: str, start: int, end: int) -> Sentence:
    return Sentence(id=item_id, start_sample=start, end_sample=end, text=text)


def test_llm_discard_of_the_last_take_is_restored() -> None:
    sentences = [sentence(0, "Take one", 0, 1000), sentence(1, "Take one", 1000, 2000)]
    client = FakeClient([{"discard_sentence_ids": [0, 1], "reasoning": "all attempts"}])
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == (0,)
    assert result.restored_sentence_ids == (1,)


def test_unknown_llm_ids_are_ignored() -> None:
    sentences = [sentence(0, "one", 0, 1000)]
    client = FakeClient([{"discard_sentence_ids": [9], "reasoning": "bad"}])
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == ()
    assert "unknown retake ids" in result.reasoning


def test_without_a_client_exact_repeats_are_culled() -> None:
    sentences = [
        sentence(0, "Same line.", 0, 1000),
        sentence(1, "  same line ", 1000, 2000),
        sentence(2, "Different.", 2000, 3000),
    ]
    result = cull_retakes(sentences)
    assert result.discard_sentence_ids == (0,)
    assert result.windows == 0


def test_large_transcripts_use_overlapping_windows() -> None:
    sentences = [
        sentence(index, f"line {index}", index * 1000, (index + 1) * 1000) for index in range(10)
    ]
    client = FakeClient([{"discard_sentence_ids": [], "reasoning": "ok"} for _ in range(6)])
    result = cull_retakes(sentences, client=client, context_window=4, single_pass=False)
    assert result.windows >= 3
    assert len(client.prompts) == result.windows


def test_interval_subtraction() -> None:
    assert subtract_spans([(0, 100), (200, 300)], [(50, 250)]) == [(0, 50), (250, 300)]
    assert subtract_spans([(0, 100)], [(0, 100)]) == []
    assert cull_intervals([sentence(0, "a", 10, 20), sentence(1, "b", 30, 40)], [0]) == [(10, 20)]


def test_discards_map_to_typed_spans_with_manual_precedence() -> None:
    sentences = [sentence(0, "a", 10, 20), sentence(1, "b", 30, 40), sentence(2, "c", 50, 60)]
    spans = inactive_spans_for_discards(sentences, [2, 0], manual_ids=[0])
    assert [
        (span.start_sample, span.end_sample, span.reason) for span in spans
    ] == [(10, 20, "manual"), (50, 60, "retake")]


def test_group_output_keeps_the_model_keeper_and_reports_the_group() -> None:
    sentences = [
        sentence(0, "Ela pegou o modelo de inteligência artificial mais avançado", 0, 1000),
        sentence(1, "Ela pegou o modelo de IA mais avançado que já construiu.", 1000, 2000),
    ]
    client = FakeClient(
        [
            {
                "groups": [
                    {"keep": [1], "discard": [0], "reason": "restarted the sentence"}
                ],
                "reasoning": "paraphrased restart",
            }
        ]
    )
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == (0,)
    assert result.groups[0].keep == (1,)
    assert result.to_dict()["groups"][0]["reason"] == "restarted the sentence"
    assert "paraphrased restart" in result.reasoning


def test_keep_wins_when_groups_conflict() -> None:
    sentences = [
        sentence(0, "First complete attempt.", 0, 1000),
        sentence(1, "Second complete attempt.", 1000, 2000),
    ]
    client = FakeClient(
        [
            {
                "groups": [
                    {"keep": [1], "discard": [0], "reason": "first"},
                    {"keep": [0], "discard": [1], "reason": "second"},
                ]
            }
        ]
    )
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == ()


def test_group_spanning_too_much_time_is_rejected() -> None:
    sentences = [
        sentence(0, "First complete attempt.", 0, 1000),
        sentence(1, "Second complete attempt.", 400 * 48000, 401 * 48000),
    ]
    client = FakeClient(
        [{"groups": [{"keep": [1], "discard": [0], "reason": "too far"}]}]
    )
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == ()


def test_discard_budget_falls_back_to_fuzzy_groups() -> None:
    sentences = [
        sentence(index, f"unique sentence number {index}.", index * 1000, (index + 1) * 1000)
        for index in range(10)
    ]
    client = FakeClient(
        [
            {
                "groups": [
                    {
                        "keep": [9],
                        "discard": list(range(9)),
                        "reason": "over budget",
                    }
                ]
            }
        ]
    )
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == ()


def test_fuzzy_clustering_catches_small_word_swaps() -> None:
    sentences = [
        sentence(
            0,
            "Ela pegou o modelo de inteligência artificial mais avançado que já construiu.",
            0,
            2000,
        ),
        sentence(
            1,
            "Ela pegou o modelo de IA mais avançado que já construiu.",
            2000,
            4000,
        ),
        sentence(2, "O preço caiu bastante.", 4000, 6000),
    ]
    result = cull_retakes(sentences)
    assert result.discard_sentence_ids == (0,)
    assert result.groups[0].keep == (1,)


def test_fuzzy_clustering_does_not_group_short_generic_lines() -> None:
    sentences = [
        sentence(index, f"line {index}", index * 1000, (index + 1) * 1000)
        for index in range(10)
    ]
    result = cull_retakes(sentences)
    assert result.discard_sentence_ids == ()


def test_single_pass_sends_the_whole_transcript_once() -> None:
    sentences = [
        sentence(index, f"Unique sentence number {index}.", index * 1000, (index + 1) * 1000)
        for index in range(20)
    ]
    client = FakeClient([{"groups": [], "reasoning": "nothing"}])
    result = cull_retakes(sentences, client=client, single_pass=True)
    assert result.windows == 1
    assert len(client.prompts) == 1
    assert "Unique sentence number 19" in client.prompts[0]


def test_long_unique_sentence_is_restored_from_an_over_grouped_pair() -> None:
    sentences = [
        sentence(
            0,
            "E sufocar o laboratório acusando ele de espalhar armas digitais.",
            0,
            4000,
        ),
        sentence(
            1,
            "Liberar um modelo que automatiza ataques com 90% de sucesso e entregar "
            "aos Estados Unidos uma justificativa para novas restrições comerciais.",
            4000,
            9000,
        ),
    ]
    client = FakeClient(
        [
            {
                "groups": [
                    {
                        "keep": [0],
                        "discard": [1],
                        "reason": "shortened conclusion",
                    }
                ]
            }
        ]
    )
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == ()
    assert "unique-looking" in result.reasoning


def test_short_stumble_is_still_discarded() -> None:
    sentences = [
        sentence(0, "A primeira reação que eu tive foi duvidar, né?", 0, 4000),
        sentence(1, "Duvida!", 4000, 5000),
    ]
    client = FakeClient(
        [
            {
                "groups": [
                    {
                        "keep": [0],
                        "discard": [1],
                        "reason": "single-word false start",
                    }
                ]
            }
        ]
    )
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == (1,)


def test_legacy_flat_discard_is_paired_with_a_keeper() -> None:
    sentences = [
        sentence(0, "Take one complete sentence.", 0, 1000),
        sentence(1, "Take one complete sentence.", 1000, 2000),
    ]
    client = FakeClient([{"discard_sentence_ids": [0], "reasoning": "legacy"}])
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == (0,)
    assert result.groups[0].keep == (1,)
