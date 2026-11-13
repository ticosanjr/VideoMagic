"""Recipe preflight: validate graph, inputs, and optional runtime dependencies."""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from videoflow.application.providers import list_providers
from videoflow.application.secrets import get_secret
from videoflow.core.recipe import Recipe
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import (
    allowed_roots,
    find_binary,
    find_whisper_binary,
    find_whisper_model,
    portable_home,
)
from videoflow.steps import get_step, requirements_by_type, step_types
from videoflow.steps.ports import validate_recipe_ports

CheckStatus = Literal["ok", "warning", "error"]

_MEDIA_PREFIXES = (
    "ingest",
    "audio.",
    "edit.",
    "transcribe",
    "shorts.",
    "export.",
    "scene.",
    "motion.",
    "captions.",
    "vision.",
    "qa.",
    "broll.",
    "thumbnail.",
    "localization.",
    "composite.",
    "face.",
    "alignment.",
    "voice.",
)

_PROVIDER_CAPABILITY = {
    "narration.synthesize": "tts",
    "voice.patch": "tts",
    "voice.clone": "tts",
    "localization.dub": "tts",
    "localization.translate": "translation",
    "factcheck.audit": "llm",
    "entities.extract": "llm",
    "assets.discover": "stock",
    "vision.qa": "vision",
}


@dataclass(frozen=True)
class PreflightCheck:
    id: str
    category: Literal["recipe", "input", "runtime", "provider", "optional"]
    status: CheckStatus
    label: str
    detail: str = ""
    fix: str = ""
    step_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "category": self.category,
            "status": self.status,
            "label": self.label,
            "detail": self.detail,
            "fix": self.fix,
            "step_id": self.step_id,
        }


@dataclass(frozen=True)
class PreflightReport:
    checks: list[PreflightCheck]

    @property
    def ready(self) -> bool:
        return not any(check.status == "error" for check in self.checks)

    @property
    def errors(self) -> int:
        return sum(check.status == "error" for check in self.checks)

    @property
    def warnings(self) -> int:
        return sum(check.status == "warning" for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "errors": self.errors,
            "warnings": self.warnings,
            "checks": [check.to_dict() for check in self.checks],
        }


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _provider_items() -> list[dict[str, object]]:
    try:
        return list_providers()
    except Exception:  # noqa: BLE001 - preflight must never fail the request
        return []


def _matches_media(step_type: str) -> bool:
    return any(
        step_type == prefix or step_type.startswith(prefix)
        for prefix in _MEDIA_PREFIXES
    )


def _writable_target(path: Path) -> tuple[bool, str]:
    candidate = path.expanduser()
    probe = candidate
    try:
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        if not probe.exists():
            return False, f"{candidate} does not have an existing parent directory"
        if not os.access(probe, os.W_OK):
            return False, f"{probe} is not writable"
    except OSError as exc:
        return False, str(exc)
    return True, ""


def _provider_ids(step: Any) -> str:
    params = step.params if isinstance(step.params, dict) else {}
    value = params.get("provider_id") or params.get("provider")
    return str(value).strip() if isinstance(value, str) else ""


def _has_secret(provider: dict[str, object]) -> bool:
    name = str(provider.get("api_key_env") or "").strip()
    return not name or bool(get_secret(name))


def preflight_recipe(
    recipe: Recipe,
    *,
    source: str = "",
    output: str = "",
    variables: dict[str, Any] | None = None,
    through: str | None = None,
) -> PreflightReport:
    """Return blocking errors and non-blocking warnings for one run."""

    checks: list[PreflightCheck] = []
    options = variables or {}
    roots = allowed_roots()

    try:
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        checks.append(
            PreflightCheck(
                "recipe.graph",
                "recipe",
                "ok",
                "Recipe graph is valid",
            )
        )
    except VideoFlowError as exc:
        checks.append(
            PreflightCheck(
                "recipe.graph",
                "recipe",
                "error",
                "Recipe graph is invalid",
                detail=str(exc),
                fix="Fix the step dependencies or cycle, then run preflight again.",
            )
        )

    try:
        validate_recipe_ports(recipe, through=through)
        checks.append(
            PreflightCheck(
                "recipe.ports",
                "recipe",
                "ok",
                "Step ports are wired correctly",
            )
        )
    except VideoFlowError as exc:
        checks.append(
            PreflightCheck(
                "recipe.ports",
                "recipe",
                "error",
                "Step ports are invalid",
                detail=str(exc),
                fix="Check the node wiring and output types.",
            )
        )

    resolved = recipe
    try:
        resolved = recipe.with_variables(options)
    except VideoFlowError as exc:
        checks.append(
            PreflightCheck(
                "recipe.variables",
                "recipe",
                "error",
                "Recipe variables are invalid",
                detail=str(exc),
                fix="Fill the required variables with valid values.",
            )
        )

    allowed = recipe.ids_through(through) if through is not None else None
    steps = [
        step
        for step in resolved.enabled_steps()
        if allowed is None or step.id in allowed
    ]
    step_types_used = {step.type for step in steps}

    for step in steps:
        try:
            get_step(step.type).validate_params(step.params)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            check = PreflightCheck(
                f"recipe.params.{step.id}",
                "recipe",
                "error",
                f"{step.id}: invalid parameters",
                detail=str(first.get("msg", "invalid parameters")),
                fix="Open the step inspector and correct the highlighted field.",
                step_id=step.id,
            )
        except VideoFlowError as exc:
            check = PreflightCheck(
                f"recipe.params.{step.id}",
                "recipe",
                "error",
                f"{step.id}: invalid parameters",
                detail=str(exc),
                fix="Open the step inspector and correct the highlighted field.",
                step_id=step.id,
            )
        else:
            check = PreflightCheck(
                f"recipe.params.{step.id}",
                "recipe",
                "ok",
                f"{step.id}: parameters are valid",
                step_id=step.id,
            )
        checks.append(check)

    required = [
        name
        for name, spec in recipe.variables.items()
        if spec.required
        and (
            options.get(name) is None
            or str(options.get(name, "")).strip() == ""
        )
    ]
    if required:
        checks.append(
            PreflightCheck(
                "input.variables",
                "input",
                "error",
                "Required variables are missing",
                detail=", ".join(sorted(required)),
                fix="Fill the required recipe variables in step 1.",
            )
        )
    elif recipe.variables:
        checks.append(
            PreflightCheck(
                "input.variables",
                "input",
                "ok",
                "Recipe variables are complete",
            )
        )

    if "ingest" in step_types_used:
        if not source.strip():
            checks.append(
                PreflightCheck(
                    "input.source",
                    "input",
                    "error",
                    "Source clip is required",
                    fix="Choose a source video in step 1.",
                )
            )
        else:
            try:
                resolved_source = resolve_allowed(
                    Path(source).expanduser(), roots
                )
            except VideoFlowError as exc:
                checks.append(
                    PreflightCheck(
                        "input.source",
                        "input",
                        "error",
                        "Source clip is outside the allowed roots",
                        detail=str(exc),
                        fix="Choose a source inside the configured allowed roots.",
                    )
                )
            else:
                if resolved_source.is_file():
                    checks.append(
                        PreflightCheck(
                            "input.source",
                            "input",
                            "ok",
                            "Source clip is available",
                            detail=str(resolved_source),
                        )
                    )
                else:
                    checks.append(
                        PreflightCheck(
                            "input.source",
                            "input",
                            "error",
                            "Source clip does not exist",
                            detail=str(resolved_source),
                            fix="Choose an existing video file.",
                        )
                    )

    output_target = Path(output).expanduser() if output.strip() else portable_home()
    try:
        output_target = (
            resolve_allowed(output_target, roots) if output.strip() else output_target
        )
    except VideoFlowError as exc:
        checks.append(
            PreflightCheck(
                "input.output",
                "input",
                "error",
                "Workspace folder is outside the allowed roots",
                detail=str(exc),
                fix="Choose a workspace inside the configured allowed roots.",
            )
        )
    else:
        writable, reason = _writable_target(output_target)
        checks.append(
            PreflightCheck(
                "input.output",
                "input",
                "ok" if writable else "error",
                "Workspace folder is writable"
                if writable
                else "Workspace folder is not writable",
                detail=str(output_target) if writable else reason,
                fix="" if writable else "Choose a writable workspace folder.",
            )
        )

    if any(_matches_media(step_type) for step_type in step_types_used):
        ffmpeg = find_binary("ffmpeg")
        checks.append(
            PreflightCheck(
                "runtime.ffmpeg",
                "runtime",
                "ok" if ffmpeg else "error",
                "FFmpeg is ready" if ffmpeg else "FFmpeg is missing",
                detail=ffmpeg or "",
                fix="" if ffmpeg else "Install FFmpeg or set its path in Settings.",
            )
        )
        if "ingest" in step_types_used:
            ffprobe = find_binary("ffprobe")
            checks.append(
                PreflightCheck(
                    "runtime.ffprobe",
                    "runtime",
                    "ok" if ffprobe else "error",
                    "ffprobe is ready" if ffprobe else "ffprobe is missing",
                    detail=ffprobe or "",
                    fix="" if ffprobe else "Install ffprobe or set its path in Settings.",
                )
            )

    if "transcribe" in step_types_used:
        step = next(step for step in steps if step.type == "transcribe")
        mode = str(step.params.get("mode") or "auto")
        local = _module_available("faster_whisper")
        whisper = find_whisper_binary()
        model = find_whisper_model()
        asr_ready = any(
            item.get("capability") == "asr" and item.get("configured")
            for item in _provider_items()
        )
        if mode in {"none", "srt", "project"}:
            ok, detail = True, f"Transcription mode is {mode}"
        elif mode == "whisper_cpp":
            ok = bool(whisper and model)
            detail = "" if ok else "whisper.cpp binary or model is missing"
        elif mode == "http":
            ok = asr_ready or bool(step.params.get("base_url"))
            detail = "" if ok else "No ASR provider or base URL is configured"
        else:
            ok = local or bool(whisper and model) or asr_ready
            detail = (
                ""
                if ok
                else "faster-whisper, whisper.cpp, and an ASR provider are unavailable"
            )
        checks.append(
            PreflightCheck(
                "runtime.transcribe",
                "runtime",
                "ok" if ok else "warning",
                "Speech recognition is available"
                if ok
                else "Speech recognition will fall back or fail",
                detail=detail,
                fix=(
                    ""
                    if ok
                    else "Install faster-whisper or whisper.cpp, or configure an ASR provider."
                ),
            )
        )

    if "vision.ocr" in step_types_used:
        ok = _module_available("pytesseract") and find_binary("tesseract") is not None
        checks.append(
            PreflightCheck(
                "optional.ocr",
                "optional",
                "ok" if ok else "warning",
                "OCR is available" if ok else "OCR will be skipped",
                detail="" if ok else "pytesseract and the tesseract binary are required",
                fix="" if ok else "Install pytesseract and tesseract, or remove the OCR step.",
            )
        )

    if "scene.render" in step_types_used:
        step = next(step for step in steps if step.type == "scene.render")
        engine = str(step.params.get("engine") or "auto")
        if engine in {"auto", "playwright"} and not _module_available("playwright"):
            checks.append(
                PreflightCheck(
                    "optional.playwright",
                    "optional",
                    "warning",
                    "HTML scenes will use the FFmpeg fallback",
                    detail="Playwright is not installed",
                    fix="Install Playwright/Chromium for HTML/Three.js scene rendering.",
                    step_id=step.id,
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    "optional.playwright",
                    "optional",
                    "ok",
                    "HTML scene renderer is available",
                    step_id=step.id,
                )
            )

    if "vision.face_contact" in step_types_used:
        ok = _module_available("cv2") or _module_available("mediapipe")
        checks.append(
            PreflightCheck(
                "optional.vision",
                "optional",
                "ok" if ok else "warning",
                "Vision backends are available" if ok else "Eye-contact analysis will be skipped",
                detail="" if ok else "OpenCV and MediaPipe are not installed",
                fix=""
                if ok
                else "Install the optional vision extras or review the decoupage manually.",
            )
        )

    if "audio.isolate" in step_types_used:
        ok = bool(find_binary("deepFilter") or find_binary("demucs"))
        checks.append(
            PreflightCheck(
                "optional.isolation",
                "optional",
                "ok" if ok else "warning",
                "Voice isolation backend is available"
                if ok
                else "Voice isolation will use the mastered audio",
                detail="" if ok else "DeepFilterNet and Demucs are not installed",
                fix="" if ok else "Install a separation backend for cleaner dialogue.",
            )
        )

    if "alignment.forced" in step_types_used:
        ok = _module_available("whisperx") or _module_available("faster_whisper")
        checks.append(
            PreflightCheck(
                "optional.alignment",
                "optional",
                "ok" if ok else "warning",
                "Forced alignment is available" if ok else "Forced alignment will be skipped",
                detail="" if ok else "WhisperX and faster-whisper are not installed",
            )
        )

    if "assets.harvest" in step_types_used:
        step = next(step for step in steps if step.type == "assets.harvest")
        providers = step.params.get("providers") or []
        if (
            isinstance(providers, list)
            and "youtube" in {str(item).casefold() for item in providers}
            and find_binary("yt-dlp") is None
        ):
            checks.append(
                PreflightCheck(
                    "optional.youtube",
                    "optional",
                    "warning",
                    "YouTube harvesting needs yt-dlp",
                    detail="yt-dlp is not installed",
                    fix="Install yt-dlp or remove YouTube from the provider list.",
                    step_id=step.id,
                )
            )

    if "broll.generate" in step_types_used:
        step = next(step for step in steps if step.type == "broll.generate")
        base_url = str(step.params.get("base_url") or "").strip()
        key_env = str(step.params.get("api_key_env") or "").strip()
        if step.params.get("provider", "openai_compatible") == "openai_compatible":
            ok = bool(base_url)
            detail = "" if ok else "No image endpoint base URL is configured"
        else:
            ok = True
            detail = ""
        secret_ok = not key_env or bool(get_secret(key_env))
        if not secret_ok:
            detail = f"Missing secret {key_env}"
        checks.append(
            PreflightCheck(
                "optional.image",
                "optional",
                "ok" if ok and secret_ok else "warning",
                "Image generation is configured"
                if ok and secret_ok
                else "B-roll generation may be skipped",
                detail=detail,
                fix="Set the image endpoint and API key in Settings."
                if not (ok and secret_ok)
                else "",
                step_id=step.id,
            )
        )

    providers = _provider_items()
    capabilities: dict[str, list[Any]] = {}
    for step in steps:
        capability = _PROVIDER_CAPABILITY.get(step.type)
        if capability is None and step.type.startswith("llm."):
            capability = "llm"
        if capability is None and step.type.startswith("localization."):
            capability = "translation"
        if capability is None:
            continue
        capabilities.setdefault(capability, []).append(step)

    for capability, using_steps in capabilities.items():
        matching = [
            item for item in providers if item.get("capability") == capability
        ]
        configured = [item for item in matching if item.get("configured")]
        explicit_missing: list[str] = []
        for step in using_steps:
            provider_id = _provider_ids(step)
            if not provider_id:
                continue
            explicit = next(
                (item for item in matching if item.get("id") == provider_id), None
            )
            if explicit is None or not explicit.get("configured"):
                explicit_missing.append(f"{step.id}: {provider_id}")
        if explicit_missing:
            checks.append(
                PreflightCheck(
                    f"provider.{capability}",
                    "provider",
                    "error",
                    f"Configured {capability} provider is not ready",
                    detail=", ".join(explicit_missing),
                    fix="Open Settings → Providers and complete the provider fields.",
                )
            )
        elif configured:
            missing_secret = [
                str(item.get("id"))
                for item in configured
                if not _has_secret(item)
            ]
            if missing_secret:
                checks.append(
                    PreflightCheck(
                        f"provider.{capability}",
                        "provider",
                        "warning",
                        f"{capability} provider secret is missing",
                        detail=", ".join(missing_secret),
                        fix="Store the provider API key in Settings → Providers.",
                    )
                )
            else:
                checks.append(
                    PreflightCheck(
                        f"provider.{capability}",
                        "provider",
                        "ok",
                        f"{capability} provider is ready",
                        detail=", ".join(
                            str(item.get("name") or item.get("id"))
                            for item in configured
                        ),
                    )
                )
        else:
            checks.append(
                PreflightCheck(
                    f"provider.{capability}",
                    "provider",
                    "warning",
                    f"No {capability} provider is configured",
                    detail="The step will use its deterministic fallback when available.",
                    fix="Configure a provider in Settings if the fallback is not enough.",
                )
            )

    try:
        usage = shutil.disk_usage(portable_home())
        free = usage.free
    except OSError:
        free = 0
    if free and free < 100 * 1024 * 1024:
        checks.append(
            PreflightCheck(
                "runtime.disk",
                "runtime",
                "error",
                "Disk space is critically low",
                detail=f"{free // (1024 * 1024)} MB free",
                fix="Free disk space before starting the run.",
            )
        )
    elif free and free < 1024 * 1024 * 1024:
        checks.append(
            PreflightCheck(
                "runtime.disk",
                "runtime",
                "warning",
                "Disk space is low",
                detail=f"{free // (1024 * 1024)} MB free",
                fix="Clear old renders or checkpoints before a long run.",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "runtime.disk",
                "runtime",
                "ok",
                "Disk space is available",
                detail=f"{free // (1024 * 1024)} MB free" if free else "",
            )
        )

    return PreflightReport(checks)
