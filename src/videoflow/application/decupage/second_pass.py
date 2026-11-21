"""Second-pass decupage audit over the edited timeline.

After the first pass removes takes and repetitions, two identical words can
become adjacent across a removed span. This pass rebuilds the word stream from
the *kept* ASU words only and removes repetitions that survive at the joins,
without exporting an intermediate MP4.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from videoflow.application.repetition import RepeatWord, detect_words, normalise_token
from videoflow.domain.decupage import Asu


@dataclass
class SecondPassResult:
    cuts: list[dict[str, Any]] = field(default_factory=list)
    flags: list[dict[str, str]] = field(default_factory=list)
    repeats: int = 0
    ambiguous: int = 0


def _inside(sample: int, cuts: Sequence[tuple[int, int]]) -> bool:
    return any(start <= sample <= end for start, end in cuts)


def second_pass_cuts(
    asus: Sequence[Asu],
    existing_cuts: Sequence[tuple[int, int]],
    *,
    sample_rate: int = 48_000,
    max_gap_sec: float = 1.2,
) -> SecondPassResult:
    """Detect repetitions on the kept word stream after the first pass."""

    origin: list[tuple[str, int, Any]] = []
    tokens: list[RepeatWord] = []
    for asu in asus:
        for word in asu.words:
            if _inside((word.start_sample + word.end_sample) // 2, existing_cuts):
                continue
            norm = normalise_token(word.w)
            if not norm:
                continue
            tokens.append(
                RepeatWord(
                    index=len(tokens),
                    sentence_id=0,
                    text=word.w,
                    norm=norm,
                    start_sample=word.start_sample,
                    end_sample=word.end_sample,
                    probability=float(word.p),
                )
            )
            origin.append((asu.asu_id, word.idx, word))
    pairs = sorted(
        zip(tokens, origin, strict=False),
        key=lambda item: (item[0].start_sample, item[0].end_sample),
    )
    tokens = [
        RepeatWord(
            index=position,
            sentence_id=0,
            text=token.text,
            norm=token.norm,
            start_sample=token.start_sample,
            end_sample=token.end_sample,
            probability=token.probability,
        )
        for position, (token, _origin) in enumerate(pairs)
    ]
    origin = [item for _token, item in pairs]
    plan = detect_words(tokens, sample_rate=sample_rate, max_gap_sec=max_gap_sec)
    result = SecondPassResult(repeats=len(plan.cuts), ambiguous=len(plan.ambiguous))
    for cut in plan.cuts:
        for index in range(cut.first_index, cut.last_index + 1):
            asu_id, _word_index, word = origin[index]
            result.cuts.append(
                {
                    "asu_id": asu_id,
                    "start_sample": word.start_sample,
                    "end_sample": word.end_sample,
                    "reason": "second_pass",
                }
            )
    for cut in plan.ambiguous:
        asu_id, _word_index, _word = origin[cut.first_index]
        result.flags.append(
            {
                "asu_id": asu_id,
                "category": "REVIEW",
                "reason": f"second-pass ambiguous repetition: {cut.text}",
            }
        )
    return result


__all__ = ["SecondPassResult", "second_pass_cuts"]
