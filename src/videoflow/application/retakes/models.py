"""Retake report models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetakeGroup:
    """One repeated passage: the keeper and the attempts to remove."""

    keep: tuple[int, ...]
    discard: tuple[int, ...]
    reason: str = ""
    keep_text: tuple[str, ...] = ()
    discard_text: tuple[str, ...] = ()
    start_sec: float = 0.0
    end_sec: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "keep": list(self.keep),
            "discard": list(self.discard),
            "reason": self.reason,
            "keep_text": list(self.keep_text),
            "discard_text": list(self.discard_text),
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
        }


@dataclass(frozen=True, slots=True)
class RetakeResult:
    discard_sentence_ids: tuple[int, ...]
    restored_sentence_ids: tuple[int, ...]
    reasoning: str
    windows: int
    groups: tuple[RetakeGroup, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "discard_sentence_ids": list(self.discard_sentence_ids),
            "restored_sentence_ids": list(self.restored_sentence_ids),
            "reasoning": self.reasoning,
            "windows": self.windows,
            "groups": [group.to_dict() for group in self.groups],
        }

