"""Conservative context cleanup for clear out-of-context asides."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step

PROMPT_HEADER = """\
You are cleaning a talking-head transcript before the final cut.
Remove ONLY sentences that are clearly outside the subject and the surrounding
conversation, such as remarks about the room, recording, microphone, a fly, or
an accidental interruption with no follow-up.

Keep, without exception:
- sponsor segments, product names, prices, links, coupons, discounts, offers,
  plans, CTAs, and calls to subscribe/like;
- examples, explanations, and any sentence that introduces new information;
- sign-offs or outros that belong to the video;
- anything related to the before/after context.

When in doubt, keep the sentence. Only remove sentences with at most {max_words}
words. Return only one JSON object:
{"discard_sentence_ids": [ints], "reasoning": "short explanation"}
Sentences (id | before | text | after):
"""

_PROTECTED = re.compile(
    r"https?://|www\.|r\$|\$|€|£|\bpre[çc]o\b|\bpatrocin|\bapoia\s+esse\s+v[íi]deo|"
    r"\blink\b|\bcupom\b|\bdesconto\b|\bpromo[çc]|\boferta\b|\bblack\s+friday|"
    r"\bassinatura\b|\bplano\b|\bgr[áa]tis\b|\bsite\b|\bloja\b|\bcomprar\b|"
    r"\bclique\b|\binscreve\b|\bcanal\b|\blike\b|\bsininho\b|\bmembro\b",
    re.IGNORECASE,
)


class CleanupParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    prompt: str = Field(
        default=(
            "Remove only clear out-of-context interruptions; "
            "preserve sponsor and unique content."
        ),
        max_length=4000,
    )
    max_words: int = Field(default=10, ge=1, le=40)
    max_cuts: int = Field(default=12, ge=1, le=50)


@register_step
class LlmCleanupStep(BaseStep):
    type = "llm.cleanup"
    version = "1"
    title = "Context cleanup"
    description = (
        "Use the transcript context to remove only clear out-of-context asides "
        "while protecting sponsor and unique content."
    )
    requires = ("retakes.cull",)
    produces = ("cleanup_report", "discarded_sentence_ids")
    params_model = CleanupParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = CleanupParams.model_validate(params)
        if not context.transcript:
            context.metadata["cleanup_report"] = {
                "discarded_sentence_ids": [],
                "reasoning": "no transcript",
            }
            return
        if io.llm_client is None:
            context.metadata["cleanup_report"] = {
                "discarded_sentence_ids": [],
                "reasoning": "skipped: no configured LLM provider",
            }
            return
        discarded = set(context.discard_sentence_ids)
        kept = [
            sentence
            for sentence in context.transcript
            if sentence.id not in discarded and sentence.text.strip()
        ]
        if not kept:
            context.metadata["cleanup_report"] = {
                "discarded_sentence_ids": [],
                "reasoning": "no kept sentences",
            }
            return
        payload = []
        for index, sentence in enumerate(kept):
            before = kept[index - 1].text if index > 0 else ""
            after = kept[index + 1].text if index + 1 < len(kept) else ""
            payload.append(
                {
                    "id": sentence.id,
                    "before": before[-160:],
                    "text": sentence.text,
                    "after": after[:160],
                    "words": len(sentence.text.split()),
                }
            )
        raw = io.llm_client.complete_json(
            PROMPT_HEADER.replace("{max_words}", str(options.max_words))
            + "\n"
            + options.prompt.strip()
            + "\n\n"
            + json.dumps(payload, ensure_ascii=False),
            "videoflow.cleanup",
        )
        proposed = raw.get("discard_sentence_ids") if isinstance(raw, dict) else None
        if not isinstance(proposed, list):
            proposed = []
        by_id = {sentence.id: sentence for sentence in kept}
        rejected: list[dict[str, Any]] = []
        accepted: list[int] = []
        for value in proposed[: options.max_cuts]:
            try:
                identifier = int(value)
            except (TypeError, ValueError):
                continue
            sentence = by_id.get(identifier)
            if sentence is None:
                rejected.append({"sentence_id": identifier, "error": "not a kept sentence"})
                continue
            if len(sentence.text.split()) > options.max_words:
                rejected.append({"sentence_id": identifier, "error": "too long for cleanup"})
                continue
            if _PROTECTED.search(sentence.text):
                rejected.append(
                    {"sentence_id": identifier, "error": "protected sponsor/CTA content"}
                )
                continue
            accepted.append(identifier)
        if accepted and len(accepted) >= len(kept):
            rejected.extend(
                {"sentence_id": item, "error": "would remove every sentence"} for item in accepted
            )
            accepted = []
        context.discard_sentence_ids = sorted(set(context.discard_sentence_ids) | set(accepted))
        context.metadata["cleanup_report"] = {
            "discarded_sentence_ids": accepted,
            "rejected": rejected,
            "reasoning": str(raw.get("reasoning") or "") if isinstance(raw, dict) else "",
            "kept_sentences": len(kept) - len(accepted),
        }
        if accepted:
            context.warnings.append(
                f"Context cleanup removed {len(accepted)} out-of-context sentence(s)."
            )
        io.report(100, f"cleanup removed {len(accepted)}, rejected {len(rejected)}")
