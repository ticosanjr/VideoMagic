"""Build Atomic Speech Units (ASUs) from a word-aligned transcript."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.rms import build_rms_profile, rms_db_at, rms_mean_db
from videoflow.core.context import PipelineContext
from videoflow.domain.decupage import Asu, AsuReport, AsuWord
from videoflow.domain.state import Sentence, WordTiming
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step

_STRONG_END = re.compile(r"[.!?…]\s*$")
_TOKEN = re.compile(r"[^0-9a-zà-ÿ]+")


class SpeechAsuParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pause_ms: int = Field(default=250, ge=0, le=5000)
    punctuation_pause_ms: int = Field(default=120, ge=0, le=5000)
    max_asu_sec: float = Field(default=15.0, ge=1.0, le=120.0)
    min_words: int = Field(default=1, ge=1, le=100)
    include_noise_events: bool = True


def _normal(value: str) -> str:
    return _TOKEN.sub("", value.casefold())


def _join(words: list[WordTiming]) -> str:
    text = ""
    for word in words:
        token = word.word.strip()
        if not token:
            continue
        if not text:
            text = token
        elif token.startswith((",", ".", "!", "?", ";", ":", ")", "]", "}")):
            text += token
        else:
            text += " " + token
    return text.strip()


def _stutter_candidate(words: list[WordTiming], sample_rate: int) -> bool:
    for left, right in zip(words, words[1:], strict=False):
        a = _normal(left.word)
        b = _normal(right.word)
        if not a or not b:
            continue
        if a == b:
            return True
        if len(a) >= 2 and len(b) > len(a) and b.startswith(a):
            return True
        if (
            left.probability < 0.35
            and right.start_sample - left.end_sample >= round(0.18 * sample_rate)
        ):
            return True
    return False


def _split_at_valley(
    group: list[tuple[WordTiming, Sentence]],
    profile: dict[str, Any],
    sample_rate: int,
) -> tuple[list[tuple[WordTiming, Sentence]], list[tuple[WordTiming, Sentence]]]:
    """Split a long ASU at the quietest inter-word boundary."""

    if len(group) < 2 or not profile:
        middle = max(1, len(group) // 2)
        return group[:middle], group[middle:]
    candidates: list[tuple[float, int]] = []
    for index in range(1, len(group)):
        left = group[index - 1][0]
        right = group[index][0]
        point = (left.end_sample + right.start_sample) // 2
        candidates.append((rms_db_at(profile, point), index))
    _value, index = min(candidates, key=lambda item: (item[0], abs(item[1] - len(group) // 2)))
    return group[:index], group[index:]


def _rms_profile(context: PipelineContext, media: Any) -> dict[str, Any]:
    metadata = context.metadata.get("vad_rms")
    if isinstance(metadata, dict) and metadata.get("path"):
        try:
            return json.loads(Path(str(metadata["path"])).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    pcm = context.pcm_path
    if pcm is None or not Path(pcm).is_file():
        return {}
    try:
        return build_rms_profile(
            Path(pcm),
            sample_rate=int(media.audio_sample_rate),
            frame_ms=10,
            window_ms=25,
        )
    except (OSError, ValueError):
        return {}


@register_step
class SpeechAsuStep(BaseStep):
    type = "speech.asu"
    title = "Atomic Speech Units"
    description = (
        "Group word-aligned speech into ASUs with pauses, probability, RMS, and "
        "speech rate for the decupage LLM."
    )
    requires = ("transcribe", "audio.vad")
    produces = ("asus", "asu_report")
    params_model = SpeechAsuParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SpeechAsuParams.model_validate(params)
        media = require_media(context)
        sample_rate = int(media.audio_sample_rate)
        profile = _rms_profile(context, media)
        discard = set(context.discard_sentence_ids)
        forced = [
            *context.retake_overlap_cuts,
            *[
                (int(start), int(end))
                for start, end in context.metadata.get("editorial_cuts", [])
                if int(end) > int(start)
            ],
        ]

        entries: list[tuple[WordTiming, Sentence]] = []
        for sentence in context.transcript:
            if sentence.id in discard:
                continue
            for word in sorted(sentence.words, key=lambda item: item.start_sample):
                midpoint = (word.start_sample + word.end_sample) // 2
                if any(start <= midpoint <= end for start, end in forced):
                    continue
                entries.append((word, sentence))

        groups: list[list[tuple[WordTiming, Sentence]]] = []
        current: list[tuple[WordTiming, Sentence]] = []
        pause = round(options.pause_ms * sample_rate / 1000)
        punctuation_pause = round(options.punctuation_pause_ms * sample_rate / 1000)
        max_samples = round(options.max_asu_sec * sample_rate)
        for entry in entries:
            word, sentence = entry
            if not current:
                current = [entry]
                continue
            previous_word, previous_sentence = current[-1]
            gap = word.start_sample - previous_word.end_sample
            duration = word.end_sample - current[0][0].start_sample
            strong_end = bool(_STRONG_END.search(previous_sentence.text.rstrip()))
            if duration >= max_samples and len(current) >= max(2, options.min_words):
                left, right = _split_at_valley(current, profile, sample_rate)
                if left and right:
                    groups.append(left)
                    current = [*right, entry]
                    continue
            should_break = gap >= pause or (strong_end and gap >= punctuation_pause)
            if should_break and len(current) >= options.min_words:
                groups.append(current)
                current = [entry]
            else:
                current.append(entry)
        if current:
            groups.append(current)

        events = context.metadata.get("audio_events")
        events = events if isinstance(events, list) else []
        asus: list[Asu] = []
        for index, group in enumerate(groups, start=1):
            words = [word for word, _sentence in group]
            start = words[0].start_sample
            end = words[-1].end_sample
            if end <= start:
                continue
            data = [
                AsuWord(
                    idx=word_index,
                    w=word.word,
                    start_sample=word.start_sample,
                    end_sample=word.end_sample,
                    start_sec=round(word.start_sample / sample_rate, 3),
                    end_sec=round(word.end_sample / sample_rate, 3),
                    p=max(0.0, min(1.0, float(word.probability))),
                )
                for word_index, word in enumerate(words)
            ]
            noise = [
                dict(event)
                for event in events
                if isinstance(event, dict)
                and int(event.get("start_sample", 0)) < end
                and int(event.get("end_sample", 0)) > start
            ]
            previous_end = groups[index - 2][-1][0].end_sample if index > 1 else start
            next_start = (
                groups[index][0][0].start_sample if index < len(groups) else end
            )
            duration_sec = (end - start) / sample_rate
            asus.append(
                Asu(
                    asu_id=f"ASU_{index:04d}",
                    start_sample=start,
                    end_sample=end,
                    start_sec=round(start / sample_rate, 3),
                    end_sec=round(end / sample_rate, 3),
                    pause_before=round(max(0, start - previous_end) / sample_rate, 3)
                    if index > 1
                    else 0.0,
                    pause_after=round(max(0, next_start - end) / sample_rate, 3)
                    if index < len(groups)
                    else 0.0,
                    text=_join(words),
                    avg_word_prob=round(
                        sum(word.probability for word in words) / max(1, len(words)), 4
                    ),
                    rms_mean_db=rms_mean_db(profile, start, end) if profile else -120.0,
                    speech_rate_wps=round(len(words) / duration_sec, 3)
                    if duration_sec > 0
                    else 0.0,
                    has_stutter_candidate=_stutter_candidate(words, sample_rate),
                    noise_events=noise if options.include_noise_events else [],
                    words=data,
                )
            )

        report = AsuReport(
            sample_rate=sample_rate,
            count=len(asus),
            asus=asus,
            source="transcript",
        )
        target = context.work / "decupage" / "asus.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        context.metadata["asus"] = [item.model_dump(mode="json") for item in asus]
        context.metadata["asu_report"] = {
            "schema_version": 1,
            "count": len(asus),
            "sample_rate": sample_rate,
            "path": str(target),
        }
        context.artifacts["asus"] = str(target)
        context.hashes["speech.asu"] = digest_payload(report.model_dump(mode="json"))
        io.report(100, f"{len(asus)} ASU(s) ready")
