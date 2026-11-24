"""Retake text normalization, similarity, and keeper scoring."""

from __future__ import annotations

import re
import statistics
from collections.abc import Sequence
from difflib import SequenceMatcher

from videoflow.application.text import (
    STANDALONE_WORDS,
    content_tokens,
    normalize_text,
    token_set,
)
from videoflow.core.media_contract.constants import AUDIO_MASTER_RATE
from videoflow.domain.retakes import Strategy
from videoflow.domain.state import Sentence

_STRICTNESS_RULES = {
    "conservative": (
        "Only discard attempts that clearly repeat the same passage. "
        "When in doubt, keep the sentence."
    ),
    "balanced": (
        "Discard clear retakes and aborted starts. Keep new information and ambiguous sentences."
    ),
    "aggressive": (
        "Also discard incomplete or stumbled sentences when the next sentence "
        "restates them. Still never discard unique content."
    ),
}


_ELLIPSIS = re.compile(r"^[\s.…!?;:,-]*$")


_WATERMARK = re.compile(
    r"legendas?\s+pela\s+comunidade|amara\.org|subtitles?\s+by|"
    r"legendado\s+por|transcri(?:ção|cao)\s+por",
    re.IGNORECASE,
)


_PROTECTED = re.compile(
    r"https?://|www\.|r\$|\$|€|£|\bpre[çc]o\b|\bpatrocin|\bapoia\s+esse\s+v[íi]deo|"
    r"\blink\b|\bcupom\b|\bdesconto\b|\bpromo[çc]|\boferta\b|\bblack\s+friday|"
    r"\bassinatura\b|\bplano\b|\bgr[áa]tis\b|\bsite\b|\bloja\b|\bcomprar\b|"
    r"\bclique\b|\binscreve\b|\bcanal\b|\blike\b|\bsininho\b|\bmembro\b",
    re.IGNORECASE,
)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


_PROPER = re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b")


_COMMON_NAMES = {
    "mas",
    "então",
    "entao",
    "aí",
    "ai",
    "aqui",
    "quando",
    "porque",
    "isso",
    "isto",
    "ele",
    "ela",
    "eles",
    "elas",
    "você",
    "voce",
    "agora",
    "depois",
    "antes",
    "também",
    "tambem",
    "só",
    "so",
    "não",
    "nao",
    "sim",
}


def _normalized(text: str) -> str:
    return normalize_text(text)


_CONTENT_STOPWORDS = {
    "para",
    "porque",
    "quando",
    "entao",
    "então",
    "tambem",
    "também",
    "ainda",
    "sobre",
    "entre",
    "depois",
    "antes",
    "agora",
    "aqui",
    "isso",
    "este",
    "esta",
    "esse",
    "essa",
    "como",
    "mais",
    "menos",
    "muito",
    "pouco",
    "todo",
    "toda",
    "todos",
    "todas",
    "fazer",
    "fazia",
    "coisa",
    "gente",
    "pode",
    "podem",
    "vamos",
    "você",
    "voce",
    "eles",
    "elas",
    "com",
    "sem",
    "uma",
    "uns",
    "umas",
}


def _tokens(text: str) -> set[str]:
    return token_set(text)


def _content_tokens(text: str) -> set[str]:
    return content_tokens(text, _CONTENT_STOPWORDS)


def _watermark_only(text: str) -> bool:
    """True when the text is only a subtitle credit or watermark.

    ASR often appends "Legendas pela comunidade de Amara.org" to silence. The
    phrase is not content; a sentence that also carries real words is kept.
    """

    if not _WATERMARK.search(text):
        return False
    remainder = _WATERMARK.sub(" ", text)
    return len(_tokens(remainder)) < 3


def _hallucination_loop(
    cluster: Sequence[int],
    order: dict[int, Sentence],
    *,
    sample_rate: int = AUDIO_MASTER_RATE,
) -> bool:
    """Detect an identical ASR loop rather than real repeated speech.

    Whisper loops on music or silence and emits the same line at a regular
    interval. A real repeated line is kept once; a loop is removed entirely,
    which is also what the human edit does.
    """

    identifiers = [item for item in cluster if item in order]
    if len(identifiers) < 4:
        return False
    if len(identifiers) >= 6:
        return True
    starts = sorted(order[item].start_sample / sample_rate for item in identifiers)
    gaps = [end - start for start, end in zip(starts, starts[1:], strict=False)]
    if not gaps:
        return False
    return 25.0 <= statistics.median(gaps) <= 35.0


def _similarity(left: Sentence, right: Sentence) -> float:
    a = _normalized(left.text)
    b = _normalized(right.text)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    left_tokens = _tokens(left.text)
    right_tokens = _tokens(right.text)
    if not left_tokens or not right_tokens:
        return ratio
    different = left_tokens ^ right_tokens
    if different and all(token.isdigit() for token in different):
        # "Chapter 1" / "Chapter 2" are list items, not retakes.
        return 0.0
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    shorter = min(len(left_tokens), len(right_tokens))
    longer = max(len(left_tokens), len(right_tokens))
    length_ratio = shorter / longer
    return max(ratio, overlap) if length_ratio >= 0.45 else ratio * length_ratio


def _has_content(sentence: Sentence) -> bool:
    return len(_tokens(sentence.text)) >= 3 and len(sentence.text.split()) >= 4


def _complete(sentence: Sentence) -> bool:
    text = sentence.text.strip()
    if not text or _ELLIPSIS.match(text) or _WATERMARK.search(text):
        return False
    tokens = _tokens(text)
    if len(tokens) <= 1:
        return text.strip(" .!?,;:").casefold() in STANDALONE_WORDS
    return text.endswith((".", "!", "?")) or len(tokens) >= 4


def _completeness(sentence: Sentence) -> float:
    text = sentence.text.strip()
    score = 0.0
    if text.endswith((".", "!", "?")):
        score += 0.35
    score += min(len(_tokens(text)) / 12.0, 0.35)
    if sentence.words:
        probabilities = [word.probability for word in sentence.words]
        score += min(sum(probabilities) / len(probabilities), 1.0) * 0.3
    return round(score, 6)


def _clean_candidate(sentence: Sentence) -> bool:
    text = sentence.text.strip()
    if not text or _ELLIPSIS.match(text) or _WATERMARK.search(text):
        return False
    tokens = _tokens(text)
    if len(tokens) <= 1:
        return text.strip(" .!?,;:").casefold() in STANDALONE_WORDS
    if text.endswith((".", "!", "?")) and len(tokens) >= 3:
        # A sentence that repeats a three-word block inside itself is corrupted
        # by overlapping ASR windows; prefer the cleaner take.
        words = text.casefold().split()
        grams = [" ".join(words[i : i + 3]) for i in range(max(0, len(words) - 2))]
        return len(grams) == len(set(grams))
    return len(tokens) >= 4


def _tail_candidate(candidate: Sentence, other: Sentence) -> bool:
    left = _normalized(candidate.text)
    right = _normalized(other.text)
    if not left or not right or left == right:
        return False
    if len(candidate.text.split()) >= len(other.text.split()) * 0.75:
        return False
    return right.endswith(left) or left in right


def _proper_names(text: str) -> set[str]:
    """Capitalized names, ignoring the ambiguous first word of a sentence."""

    words = text.split()
    body = " ".join(words[1:]) if len(words) > 1 else ""
    return {
        item
        for item in _PROPER.findall(body)
        if item.casefold() not in _COMMON_NAMES
    }


def _unique_facts(candidate: Sentence, keeper: Sentence) -> bool:
    text = candidate.text.strip()
    if _PROTECTED.search(text):
        return True
    left = {value.replace(",", ".") for value in _NUMBER.findall(text)}
    right = {value.replace(",", ".") for value in _NUMBER.findall(keeper.text)}
    if len(candidate.text.split()) >= 4 and left - right:
        return True
    names = {
        item
        for item in _proper_names(text)
        if item.casefold() not in keeper.text.casefold()
    }
    return len(candidate.text.split()) >= 4 and bool(names)


def _keeper_score(
    identifier: int,
    ordered: Sequence[int],
    sentences: dict[int, Sentence],
) -> float:
    sentence = sentences[identifier]
    text = sentence.text.strip()
    score = float(len(text.split()))
    if text.endswith((".", "!", "?")):
        score += 2.0
    if _clean_candidate(sentence):
        score += 3.0
    else:
        score -= 8.0
    words = text.casefold().split()
    grams = [" ".join(words[i : i + 3]) for i in range(max(0, len(words) - 2))]
    if len(grams) != len(set(grams)):
        score -= 12.0
    if any(
        other != identifier and _tail_candidate(sentence, sentences[other])
        for other in ordered
    ):
        score -= 10.0
    if _PROTECTED.search(text):
        score += 8.0
    return score


def _choose_keeper(
    ordered: Sequence[int],
    sentences: dict[int, Sentence],
    strategy: Strategy,
) -> int:
    # Prefer the most complete, clean candidate. The old rule kept the last
    # sentence even when it was only the tail of a full restatement; that lost
    # unique content. Ties go to the later occurrence for keep_last and to the
    # higher completeness for keep_best.
    return max(
        ordered,
        key=lambda item: (
            _keeper_score(item, ordered, sentences),
            (
                sentences[item].start_sample
                if strategy == "keep_last"
                else _completeness(sentences[item])
            ),
            item,
        ),
    )


def _keeper(group: Sequence[int], sentences: dict[int, Sentence], strategy: Strategy) -> int:
    ordered = [item for item in group if item in sentences]
    if not ordered:
        raise ValueError("retake group has no valid sentences")
    if strategy == "keep_best":
        return max(ordered, key=lambda item: (_completeness(sentences[item]), item))
    last = max(ordered, key=lambda item: (sentences[item].start_sample, item))
    if _complete(sentences[last]):
        return last
    complete = [item for item in ordered if _complete(sentences[item])]
    if complete:
        return max(complete, key=lambda item: (sentences[item].start_sample, item))
    return last

