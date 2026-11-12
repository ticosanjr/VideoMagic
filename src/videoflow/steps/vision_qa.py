"""Visual and speech QA aggregation for the delivery gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.intelligence.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from videoflow.application.providers import resolve_chain
from videoflow.application.secrets import get_secret
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class VisionQaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_fps: float = Field(default=1.0, gt=0.0, le=10.0)
    max_flash_frames: int = Field(default=3, ge=1, le=30)
    max_text_latency_ms: int = Field(default=100, ge=0, le=2000)
    max_lip_sync_frames: int = Field(default=2, ge=0, le=30)
    face_obscuration: bool = True
    checks: list[str] = Field(
        default_factory=lambda: [
            "black_frames",
            "static_screens",
            "transcript_similarity",
            "audio_loudness",
            "storyboard_coverage",
        ]
    )
    min_score: float = Field(default=0.75, ge=0.0, le=1.0)


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _vision_client() -> OpenAICompatibleProvider | None:
    for item in resolve_chain("vision"):
        if str(item.get("kind") or "openai_compatible") != "openai_compatible":
            continue
        base_url = str(item.get("base_url") or "")
        if not base_url:
            continue
        return OpenAICompatibleProvider(
            provider_id=str(item.get("id") or "vision"),
            base_url=base_url,
            model=str(item.get("model") or "gpt-4o-mini"),
            api_key=get_secret(str(item.get("api_key_env") or "")),
        )
    return None


def _extract_issues(payload: object) -> list[dict[str, Any]]:
    raw = payload.get("issues") if isinstance(payload, dict) else []
    result: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "kind": str(item.get("kind") or "review"),
                "severity": str(item.get("severity") or "warning"),
                "message": str(item.get("message") or ""),
                "start_sec": float(item.get("start_sec") or 0.0),
            }
        )
    return result


@register_step
class VisionQaStep(BaseStep):
    type = "qa.vision"
    title = "Vision + speech QA"
    description = (
        "Aggregate frame checks, transcript fidelity, audio loudness, and "
        "storyboard coverage into one delivery report."
    )
    status = "available"
    icon = "◉"
    color = "#22c55e"
    params_model = VisionQaParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VisionQaParams.model_validate(params)
        frames = _load(context.output / "qa" / "frames.json", {})
        transcript = _load(context.output / "qa" / "transcript.json", {})
        audio = _load(context.output / "qa" / "audio.json", {})
        if not audio:
            audio = context.metadata.get("audio_qa", {})
        units_payload = _load(context.output / "storyboard" / "units.json", {})
        units = (
            units_payload.get("units", [])
            if isinstance(units_payload, dict)
            else []
        )
        issues: list[dict[str, Any]] = []
        for item in frames.get("issues", []) if isinstance(frames, dict) else []:
            if isinstance(item, dict):
                issues.append(item)
        if isinstance(transcript, dict) and transcript and not transcript.get("passed", True):
            issues.append(
                {
                    "kind": "transcript_mismatch",
                    "severity": "warning",
                    "message": "Spoken transcript differs from the script.",
                    "similarity": transcript.get("similarity"),
                    "start_sec": 0.0,
                }
            )
        if isinstance(audio, dict) and audio and not audio.get("passed", True):
            issues.append(
                {
                    "kind": "audio_loudness",
                    "severity": "warning",
                    "message": "Integrated loudness or true peak is out of spec.",
                    "integrated_lufs": audio.get("integrated_lufs"),
                    "true_peak_dbfs": audio.get("true_peak_dbfs"),
                    "start_sec": 0.0,
                }
            )
        if not units:
            issues.append(
                {
                    "kind": "storyboard_missing",
                    "severity": "warning",
                    "message": "No timed storyboard units were found.",
                    "start_sec": 0.0,
                }
            )
        prompt = (
            "Audit these rendered video frames and the deterministic QA issues. "
            "Return one JSON object: "
            '{"summary":"","issues":[{"kind":"","severity":"critical|warning",'
            '"message":"","start_sec":0}]}. Look for clipped text, overlapping '
            "callouts, empty layouts, and text covering a face. Do not invent "
            "content that is not visible.\n\n"
            + json.dumps(
                {
                    "issues": issues,
                    "units": [
                        {"unit_id": item.get("unit_id"), "title": item.get("title")}
                        for item in units[:40]
                        if isinstance(item, dict)
                    ],
                },
                ensure_ascii=False,
            )[:16000]
        )
        frames_for_review = [
            str(item)
            for item in (
                frames.get("frames", [])[:6] if isinstance(frames, dict) else []
            )
            if Path(str(item)).is_file()
        ]
        vision = _vision_client()
        if vision is not None and frames_for_review:
            try:
                reviewed = vision.complete_json_with_images(
                    prompt, frames_for_review, "videoflow.qa.vision"
                )
                issues.extend(_extract_issues(reviewed.data))
            except Exception as exc:  # noqa: BLE001 - deterministic QA still works
                context.warnings.append(f"Vision QA provider fallback: {exc}")
        elif io.llm_client is not None:
            try:
                payload = io.llm_client.complete_json(
                    prompt, "videoflow.qa.vision"
                )
                issues.extend(_extract_issues(payload))
            except Exception as exc:  # noqa: BLE001 - deterministic QA still works
                context.warnings.append(f"QA model fallback: {exc}")
        critical = [item for item in issues if item.get("severity") == "critical"]
        total_checks = max(1, len(options.checks))
        score = max(
            0.0,
            1.0
            - (len(critical) * 0.35 + (len(issues) - len(critical)) * 0.08)
            / total_checks,
        )
        report = {
            "ok": True,
            "checks": options.checks,
            "issues": issues,
            "critical_count": len(critical),
            "warning_count": len(issues) - len(critical),
            "score": round(score, 3),
            "passed": score >= options.min_score and not critical,
            "sample_fps": options.sample_fps,
            "max_flash_frames": options.max_flash_frames,
            "max_text_latency_ms": options.max_text_latency_ms,
            "max_lip_sync_frames": options.max_lip_sync_frames,
            "face_obscuration": options.face_obscuration,
        }
        target = context.output / "qa" / "vision-report.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        markdown = context.output / "qa" / "vision-report.md"
        lines = [
            "# Vision + speech QA",
            "",
            f"- Score: {score:.0%}",
            f"- Critical: {len(critical)}",
            f"- Warnings: {len(issues) - len(critical)}",
            "",
        ]
        for item in issues:
            lines.append(
                f"- **{item.get('severity', 'warning')}** "
                f"{item.get('kind', 'issue')}: {item.get('message', '')}"
            )
        markdown.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        context.artifacts["vision_qa"] = str(target)
        context.artifacts["vision_qa_md"] = str(markdown)
        context.metadata["vision_qa"] = report
        context.hashes["qa.vision"] = digest_payload(report)
        if not report["passed"]:
            context.warnings.append(
                f"QA score {score:.0%} is below the {options.min_score:.0%} gate."
            )
        io.report(
            100,
            f"QA score {score:.0%}; {len(issues)} issue(s)",
        )

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("vision_qa", "vision_qa_md")
            if context.artifacts.get(key)
        )


__all__ = ["VisionQaParams", "VisionQaStep"]
