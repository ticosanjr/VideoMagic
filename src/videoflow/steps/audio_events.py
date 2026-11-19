"""Acoustic non-speech events: cough, throat clear, sneeze, and transients."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.yamnet import YamnetAdapter
from videoflow.application.audio_events import detect_audio_events
from videoflow.application.non_speech import load_pcm_mono
from videoflow.core.context import PipelineContext
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class AudioEventsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    model_path: str = ""
    labels_path: str = ""
    threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    low_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    asr_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    min_event_ms: int = Field(default=150, ge=0, le=5000)
    merge_gap_ms: int = Field(default=120, ge=0, le=2000)
    use_ast_fallback: bool = True
    ast_threshold: float = Field(default=0.1, ge=0.0, le=1.0)


@register_step
class AudioEventsStep(BaseStep):
    type = "audio.events"
    title = "Acoustic events"
    description = "Tag coughs, throat clears, sneezes, and transients before the cut."
    requires = ("ingest",)
    produces = ("audio_events",)
    params_model = AudioEventsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AudioEventsParams.model_validate(params)
        if not options.enabled:
            context.metadata["audio_events"] = []
            context.metadata["audio_events_report"] = {
                "schema_version": 1,
                "available": False,
                "engine": "disabled",
                "events": 0,
            }
            io.report(100, "Acoustic event detection disabled")
            return
        media = require_media(context)
        pcm_path = context.pcm_path
        if pcm_path is None or not pcm_path.is_file():
            candidate = context.work / "source.wav"
            pcm_path = candidate if candidate.is_file() else None
        if pcm_path is None:
            io.emit(
                "warning",
                "No PCM available for acoustic event detection",
                module="audio.events",
            )
            context.metadata["audio_events"] = []
            context.metadata["audio_events_report"] = {
                "schema_version": 1,
                "available": False,
                "engine": "none",
                "reason": "pcm_missing",
                "events": 0,
            }
            return

        model_path = (
            str(resolve_allowed(Path(options.model_path), allowed_roots()))
            if options.model_path
            else ""
        )
        labels_path = (
            str(resolve_allowed(Path(options.labels_path), allowed_roots()))
            if options.labels_path
            else ""
        )
        pcm = load_pcm_mono(pcm_path, sample_rate=media.audio_sample_rate)
        word_spans = [
            (word.start_sample, word.end_sample, float(word.probability))
            for sentence in context.transcript
            for word in sentence.words
        ]
        adapter = YamnetAdapter(
            model_path or None,
            labels=labels_path or None,
        )
        status = adapter.status()
        events: list[dict[str, object]] = []
        engine = "yamnet"
        reason = ""
        available = bool(status["available"] and status["labels"])
        try:
            if available:
                detected = adapter.detect(
                    pcm,
                    sample_rate=media.audio_sample_rate,
                    word_spans=word_spans,
                    threshold=options.threshold,
                    low_threshold=options.low_threshold,
                    asr_confidence=options.asr_confidence,
                    min_event_ms=options.min_event_ms,
                    merge_gap_ms=options.merge_gap_ms,
                )
                events = [event.to_dict() for event in detected]
            else:
                engine = "heuristic"
                reason = str(status.get("reason") or "yamnet_unavailable")
                spans = detect_audio_events(
                    pcm,
                    [(start, end) for start, end, _probability in word_spans],
                    sample_rate=media.audio_sample_rate,
                    use_ast=options.use_ast_fallback,
                    ast_threshold=options.ast_threshold,
                )
                events = [
                    {
                        "label": "non_speech",
                        "start_sample": start,
                        "end_sample": end,
                        "score": 0.0,
                        "action": "remove",
                        "source": "heuristic",
                    }
                    for start, end in spans
                ]
        except Exception as exc:  # noqa: BLE001 - optional model must not kill a cut
            engine = "heuristic"
            reason = str(exc)
            available = False
            context.warnings.append(f"YAMNet unavailable; heuristic audio events used: {exc}")
            spans = detect_audio_events(
                pcm,
                [(start, end) for start, end, _probability in word_spans],
                sample_rate=media.audio_sample_rate,
                use_ast=options.use_ast_fallback,
                ast_threshold=options.ast_threshold,
            )
            events = [
                {
                    "label": "non_speech",
                    "start_sample": start,
                    "end_sample": end,
                    "score": 0.0,
                    "action": "remove",
                    "source": "heuristic",
                }
                for start, end in spans
            ]

        report = {
            "schema_version": 1,
            "available": available,
            "engine": engine,
            "reason": reason,
            "events": len(events),
            "model": str(status.get("model") or ""),
            "labels": str(status.get("labels") or ""),
            "remove": sum(1 for event in events if event.get("action") == "remove"),
            "informational": sum(
                1 for event in events if event.get("action") == "informational"
            ),
        }
        target = context.work / "audio_events.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"report": report, "events": events}, indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        context.metadata["audio_events"] = events
        context.metadata["audio_events_report"] = report
        context.artifacts["audio_events"] = str(target)
        context.hashes["audio.events"] = digest_payload(
            {"events": events, "engine": engine}
        )
        io.report(100, f"{len(events)} acoustic event(s) ({engine})")
