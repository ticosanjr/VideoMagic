"""Presenter voice profiling."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from videoflow.core.context import PipelineContext
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step
from videoflow.steps.research.params import PresenterParams
from videoflow.steps.research.support import _write_json, _write_text


@register_step
class PresenterProfileStep(BaseStep):
    type = "presenter.profile"
    title = "Presenter profile"
    description = (
        "Derive vocabulary, sentence length, and cadence from past transcripts "
        "so the script can match the presenter's voice."
    )
    status = "available"
    icon = "◍"
    color = "#a78bfa"
    params_model = PresenterParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = PresenterParams.model_validate(params)
        texts: list[str] = []
        roots = allowed_roots()
        for raw in options.paths:
            try:
                path = resolve_allowed(Path(raw), roots)
                if path.is_file():
                    texts.append(path.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:  # noqa: BLE001 - list the unreadable path
                context.warnings.append(f"Presenter sample unavailable: {raw}: {exc}")
        if context.transcript:
            texts.append(" ".join(sentence.text for sentence in context.transcript))
        text = "\n".join(texts)[: options.max_chars]
        sentences = [item for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]
        words = re.findall(r"[0-9A-Za-zÀ-ÿ']+", text.casefold())
        unique = sorted(set(words))
        stop = {
            "a",
            "o",
            "e",
            "de",
            "da",
            "do",
            "que",
            "em",
            "um",
            "uma",
            "para",
            "com",
            "não",
            "os",
            "as",
            "é",
            "ao",
            "dos",
            "das",
            "se",
            "na",
            "no",
            "por",
        }
        frequency: dict[str, int] = {}
        for word in words:
            if len(word) > 3 and word not in stop:
                frequency[word] = frequency.get(word, 0) + 1
        top = sorted(frequency.items(), key=lambda item: item[1], reverse=True)[:60]
        profile = {
            "sample_chars": len(text),
            "sentence_count": len(sentences),
            "word_count": len(words),
            "unique_words": len(unique),
            "avg_sentence_words": round(len(words) / max(1, len(sentences)), 2),
            "vocabulary": [word for word, _ in top],
            "cadence": "short" if len(words) / max(1, len(sentences)) < 14 else "long",
        }
        _write_json(context.output / "research" / "presenter-profile.json", profile)
        vocabulary = profile.get("vocabulary")
        vocabulary_text = ", ".join(
            str(item) for item in (vocabulary if isinstance(vocabulary, list) else [])[:40]
        )
        _write_text(
            context.output / "research" / "presenter-profile.md",
            "# Presenter profile\n\n"
            f"- Sample characters: {profile['sample_chars']}\n"
            f"- Words: {profile['word_count']}\n"
            f"- Average sentence: {profile['avg_sentence_words']} words\n"
            f"- Cadence: {profile['cadence']}\n"
            f"- Vocabulary: {vocabulary_text}\n",
        )
        context.metadata["presenter_profile"] = profile
        context.artifacts["presenter_profile"] = str(
            context.output / "research" / "presenter-profile.md"
        )
        context.hashes["presenter.profile"] = digest_payload(profile)
        io.report(100, f"Presenter profile from {profile['word_count']} words")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("presenter_profile")
        return (Path(path),) if path else ()

