"""Language hints for transcripts when the ASR engine does not report one."""

from __future__ import annotations

import re
from collections import Counter

_STOPWORDS: dict[str, set[str]] = {
    "pt": {
        "a",
        "o",
        "que",
        "de",
        "do",
        "da",
        "em",
        "um",
        "uma",
        "para",
        "com",
        "não",
        "nao",
        "é",
        "eh",
        "os",
        "as",
        "se",
        "na",
        "no",
        "por",
        "mais",
        "como",
        "mas",
        "você",
        "voce",
        "isso",
        "aqui",
        "muito",
        "já",
        "ja",
    },
    "en": {
        "the",
        "a",
        "an",
        "and",
        "of",
        "to",
        "in",
        "is",
        "it",
        "that",
        "for",
        "with",
        "this",
        "you",
        "are",
        "we",
        "but",
        "not",
        "have",
        "so",
        "was",
        "on",
        "as",
        "at",
        "be",
        "from",
        "or",
        "they",
        "your",
    },
    "es": {
        "el",
        "la",
        "de",
        "que",
        "y",
        "en",
        "un",
        "una",
        "para",
        "con",
        "no",
        "es",
        "los",
        "las",
        "se",
        "por",
        "más",
        "mas",
        "como",
        "pero",
        "esto",
        "aquí",
        "muy",
        "ya",
        "usted",
        "vosotros",
    },
    "it": {
        "il",
        "la",
        "di",
        "che",
        "e",
        "in",
        "un",
        "una",
        "per",
        "con",
        "non",
        "è",
        "gli",
        "le",
        "si",
        "più",
        "ma",
        "come",
        "questo",
        "qui",
        "molto",
        "già",
        "tu",
        "voi",
    },
    "fr": {
        "le",
        "la",
        "de",
        "que",
        "et",
        "en",
        "un",
        "une",
        "pour",
        "avec",
        "non",
        "est",
        "les",
        "des",
        "se",
        "par",
        "plus",
        "mais",
        "comme",
        "ceci",
        "ici",
        "très",
        "déjà",
        "vous",
        "nous",
    },
    "de": {
        "der",
        "die",
        "das",
        "und",
        "von",
        "zu",
        "in",
        "ist",
        "es",
        "dass",
        "für",
        "mit",
        "nicht",
        "ein",
        "eine",
        "auf",
        "als",
        "auch",
        "aber",
        "wie",
        "hier",
        "sehr",
        "schon",
        "sie",
        "wir",
    },
}


def detect_text_language(text: str) -> tuple[str, float]:
    """Best-effort language from transcript text.

    Prefers ``langdetect`` when installed. The built-in fallback only decides
    between the languages with a clear stopword margin and never guesses when
    the sample is too small.
    """

    sample = " ".join(text.split())[:20_000]
    if len(sample) < 40:
        return "", 0.0
    try:
        from langdetect import detect_langs  # type: ignore[import-not-found]

        ranked = detect_langs(sample)
        if ranked:
            best = ranked[0]
            code = str(best.lang).lower()
            return code, max(0.0, min(1.0, float(best.prob)))
    except Exception:  # noqa: BLE001 - optional dependency or ambiguous text
        pass
    tokens = re.findall(r"[a-zà-ÿ]+", sample.casefold())
    if len(tokens) < 8:
        return "", 0.0
    counts: Counter[str] = Counter(tokens)
    scores = {
        language: sum(counts[word] for word in words) for language, words in _STOPWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_language, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if best_score < 4 or best_score <= second_score * 1.15:
        return "", 0.0
    confidence = best_score / max(1, best_score + second_score)
    return best_language, round(min(0.95, confidence), 3)


__all__ = ["detect_text_language"]
