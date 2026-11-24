"""Distant retakes: transitive Union-Find grouping and its guards."""

from __future__ import annotations

from videoflow.application.decupage.prefilter import prefilter
from videoflow.application.decupage.retake_cluster import (
    cluster_distant_retakes,
    is_retake_pair,
)
from videoflow.application.decupage.second_pass import second_pass_cuts
from videoflow.application.editorial_clean import clean_editorial
from videoflow.application.retakes import cull_retakes
from videoflow.domain.decupage import Asu, AsuWord
from videoflow.domain.state import Sentence

RATE = 48_000


def sentence(identifier: int, text: str, start_sec: float, end_sec: float) -> Sentence:
    return Sentence(
        id=identifier,
        text=text,
        start_sample=round(start_sec * RATE),
        end_sample=round(end_sec * RATE),
    )


def asu(identifier: int, text: str, start_sec: float) -> Asu:
    start = round(start_sec * RATE)
    words = text.split()
    step = 200
    return Asu(
        asu_id=f"ASU_{identifier:04d}",
        start_sample=start,
        end_sample=start + step * max(1, len(words)),
        start_sec=start_sec,
        end_sec=start_sec + (step * max(1, len(words))) / RATE,
        text=text,
        words=[
            AsuWord(
                idx=index,
                w=word,
                start_sample=start + index * step,
                end_sample=start + (index + 1) * step,
                start_sec=(start + index * step) / RATE,
                end_sec=(start + (index + 1) * step) / RATE,
                p=0.9,
            )
            for index, word in enumerate(words)
        ],
    )


def test_five_takes_over_260_seconds_keep_only_the_last() -> None:
    items = [
        sentence(0, "Então eu vou te mostrar como configurar o servidor", 0, 12),
        sentence(1, "Pessoal, anota aí", 45, 47),
        sentence(2, "Eu vou te mostrar como configurar o servidor web", 60, 73),
        sentence(
            3,
            "Nesse vídeo eu vou mostrar como configurar o servidor web completo",
            120,
            135,
        ),
        sentence(4, "Hmm, deixa eu ver", 150, 152),
        sentence(
            5,
            "Olha, eu vou te mostrar como configurar o servidor web completo agora",
            200,
            218,
        ),
        sentence(
            6,
            "Beleza, eu vou te mostrar como configurar o servidor web completo agora mesmo",
            250,
            268,
        ),
    ]
    clusters = cluster_distant_retakes(items)
    assert len(clusters) == 1
    assert clusters[0].keeper_id == 6
    assert clusters[0].discard_ids == (0, 2, 3, 5)
    assert clusters[0].span_sec == 268.0


def test_aborted_start_and_paraphrase_are_replaced_by_the_complete_take() -> None:
    items = [
        sentence(0, "Eu vou te mostrar como", 0, 2),
        sentence(1, "Nesse vídeo eu vou te mostrar como configurar o servidor", 30, 40),
        sentence(
            2,
            "Nesse vídeo eu vou te mostrar como configurar o servidor web completo.",
            60,
            75,
        ),
    ]
    clusters = cluster_distant_retakes(items)
    assert len(clusters) == 1
    assert clusters[0].keeper_id == 2
    assert clusters[0].discard_ids == (0, 1)


def test_a_truncated_last_take_keeps_the_previous_complete_take() -> None:
    items = [
        sentence(0, "eu vou te mostrar como configurar o servidor", 0, 8),
        sentence(1, "eu vou te mostrar como configurar o servidor web", 30, 40),
        sentence(2, "Pessoal, anota aí", 55, 57),
        sentence(3, "eu vou te mostrar como configurar o servidor web completo", 60, 75),
        sentence(
            5,
            "eu vou te mostrar como configurar o servidor web completo agora.",
            100,
            118,
        ),
        sentence(6, "Certo, continuando", 130, 132),
        sentence(4, "configurar o servidor", 140, 142),
    ]
    clusters = cluster_distant_retakes(items)
    assert len(clusters) == 1
    assert clusters[0].keeper_id == 5
    assert clusters[0].discard_ids == (0, 1, 3, 4)


def test_takes_four_hundred_seconds_apart_stay_in_the_window() -> None:
    items = [
        sentence(0, "eu vou te mostrar como configurar o servidor", 0, 8),
        sentence(1, "eu vou te mostrar como configurar o servidor web", 400, 410),
    ]
    clusters = cluster_distant_retakes(items)
    assert len(clusters) == 1
    assert clusters[0].keeper_id == 1
    assert clusters[0].discard_ids == (0,)


def test_a_sixty_five_percent_discard_rate_does_not_revert() -> None:
    takes = [
        sentence(
            index,
            "eu vou te mostrar como configurar o servidor",
            index * 10,
            index * 10 + 8,
        )
        for index in range(14)
    ]
    comments = [
        sentence(14, "Pessoal, anota aí", 5, 6),
        sentence(15, "Hmm, deixa eu ver", 95, 96),
        sentence(16, "Agora vamos continuar", 145, 146),
        sentence(17, "Beleza, próximo tópico", 155, 156),
        sentence(18, "Isso foi rápido", 165, 166),
        sentence(19, "Vamos para a parte dois", 175, 176),
    ]
    items = sorted([*takes, *comments], key=lambda item: item.start_sample)
    clusters = cluster_distant_retakes(items)
    discarded = {identifier for cluster in clusters for identifier in cluster.discard_ids}
    assert len(discarded) == 13
    assert len(discarded) / len(items) == 0.65


def test_numbered_list_is_not_a_retake() -> None:
    items = [
        sentence(0, "Passo 1: instale o Docker.", 0, 3),
        sentence(1, "Passo 2: instale o Docker.", 10, 13),
        sentence(2, "Agora vamos continuar o tutorial.", 20, 25),
    ]
    assert cluster_distant_retakes(items) == ()
    assert not is_retake_pair(items[0], items[1])


def test_unique_price_and_url_are_protected() -> None:
    items = [
        sentence(0, "O preço é R$ 99,90 no site oficial.", 0, 4),
        sentence(1, "O valor é R$ 99,90 no site oficial.", 10, 15),
        sentence(2, "Então o curso custa noventa e nove reais no site.", 20, 27),
    ]
    assert cluster_distant_retakes(items) == ()


def test_empty_and_single_sentence_transcripts_are_safe() -> None:
    assert cluster_distant_retakes([]) == ()
    assert cluster_distant_retakes([sentence(0, "Uma frase.", 0, 1)]) == ()


def test_editorial_clean_uses_the_transitive_cluster() -> None:
    items = [
        sentence(0, "Então eu vou te mostrar como configurar o servidor", 0, 12),
        sentence(1, "Pessoal, anota aí", 20, 22),
        sentence(2, "Isso aqui é importante", 30, 32),
        sentence(3, "Presta atenção no detalhe", 40, 42),
        sentence(4, "Agora vamos em frente", 50, 52),
        sentence(5, "Eu vou te mostrar como configurar o servidor web", 60, 73),
        sentence(6, "Beleza, continuando", 80, 82),
        sentence(7, "Olha só que interessante", 90, 92),
        sentence(
            8,
            "Nesse vídeo eu vou mostrar como configurar o servidor web completo",
            120,
            135,
        ),
        sentence(9, "Hmm, deixa eu ver", 150, 152),
        sentence(
            10,
            "Olha, eu vou te mostrar como configurar o servidor web completo agora",
            200,
            218,
        ),
        sentence(11, "Certo, quase lá", 230, 232),
        sentence(
            12,
            "Beleza, eu vou te mostrar como configurar o servidor web completo agora mesmo",
            250,
            268,
        ),
    ]
    result = clean_editorial(
        items, semantic=False, max_discard_ratio=0.75, second_pass=True
    )
    kept = [item.id for item in result.transcript]
    assert kept == [1, 2, 3, 4, 6, 7, 9, 11, 12]
    assert set(result.discarded_sentence_ids) == {0, 5, 8, 10}
    assert any(
        group["reason"] == "transitive distant retake"
        for group in result.report["fuzzy_discards"]
    )


def test_prefilter_gives_one_group_id_to_distant_takes() -> None:
    items = [
        asu(1, "Eu vou te mostrar como configurar o servidor", 0),
        asu(2, "Uma pausa para comentar o equipamento", 40),
        asu(3, "Eu vou te mostrar como configurar o servidor web", 200),
        asu(4, "Eu vou te mostrar como configurar o servidor web completo", 360),
    ]
    result = prefilter(items)
    groups = {item.asu_id: item.retake_group_id for item in result.asus}
    assert groups["ASU_0001"] == groups["ASU_0003"] == groups["ASU_0004"]
    assert groups["ASU_0001"] != ""
    assert groups["ASU_0002"] == ""


def test_second_pass_removes_a_distant_take_that_survived_the_first_pass() -> None:
    items = [
        asu(1, "Eu vou te mostrar como configurar o servidor", 0),
        asu(2, "Eu vou te mostrar como configurar o servidor web completo", 240),
    ]
    result = second_pass_cuts(items, [])
    assert result.repeats == 1
    assert [cut["reason"] for cut in result.cuts] == ["second_pass_retake"]
    assert result.cuts[0]["asu_id"] == "ASU_0001"


def test_retake_culling_delegates_to_the_transitive_cluster() -> None:
    items = [
        sentence(0, "eu vou te mostrar como configurar o servidor", 0, 8),
        sentence(1, "eu vou te mostrar como configurar o servidor web", 60, 70),
        sentence(2, "eu vou te mostrar como configurar o servidor web completo", 120, 135),
        sentence(3, "eu vou te mostrar como configurar o servidor web completo agora", 200, 218),
    ]
    result = cull_retakes(items)
    assert len(result.groups) == 1
    assert result.groups[0].keep == (3,)
    assert result.groups[0].discard == (0, 1, 2)

