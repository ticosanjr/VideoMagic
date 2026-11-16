"""Channel style cloning and rule learning used by ``vf_project``."""

# The two helpers below run the same steps used by the recipe engine so the
# MCP surface and the pipeline never diverge.

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.preset_rules import load_rulebook, save_rulebook
from videoflow.core.context import PipelineContext
from videoflow.runtime import find_binary
from videoflow.steps.base import StepIO
from videoflow.steps.preset_compile import CompileRuleParams, CompileRuleStep
from videoflow.steps.style_reverse import StyleReverseParams, StyleReverseStep


def _capture_reference(url: str, target: Path) -> str:
    browser = find_binary("google-chrome", "chromium", "chromium-browser", "chrome")
    if browser is None:
        return "chromium_not_found"
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--window-size=1440,900",
            "--virtual-time-budget=2500",
            f"--screenshot={target}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        return (completed.stderr.strip() or "capture_failed")[-300:]
    return ""


def _context(output: Path) -> PipelineContext:
    return PipelineContext(
        source=Path(output),
        output=Path(output),
        work=Path(output) / "style" / "work",
        exports=Path(output) / "exports",
    )


def clone_style(
    channel_id: str,
    output: Path,
    *,
    reference_url: str = "",
    reference_dir: str = "",
    images: list[str] | None = None,
    name: str = "",
) -> dict[str, Any]:
    """Extract palette, typography hints, rhythm, and safe zones into a kit."""

    output = Path(output).expanduser()
    files = [str(Path(item).expanduser()) for item in (images or [])]
    warnings: list[str] = []
    if reference_dir:
        directory = Path(reference_dir).expanduser()
        if directory.is_dir():
            files.extend(
                str(path)
                for path in sorted(directory.iterdir())
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            )
    if reference_url:
        target = output / "style" / "reference.png"
        error = _capture_reference(reference_url, target)
        if error:
            warnings.append(f"reference capture failed: {error}")
        else:
            files.append(str(target))
    context = _context(output)
    StyleReverseStep().run(
        context,
        StyleReverseParams(
            images=files,
            reference_path=reference_url,
            name=name or channel_id or "reference",
        ),
        StepIO(stage="style.reverse_engineer"),
    )
    preset = dict(context.metadata.get("style_preset") or {})
    book = load_rulebook(channel_id)
    book.channel_id = channel_id
    palette = [str(item) for item in preset.get("palette") or []]
    if palette:
        book.channel_kit.palette = palette
    typography = preset.get("typography") or {}
    family = str(typography.get("family") or "").strip()
    if family:
        book.channel_kit.fonts = [family]
    book.channel_kit.defaults.setdefault("style", {})
    book.channel_kit.defaults["style"] = {
        "preset": preset,
        "safe_zones": preset.get("safe_zones") or {},
    }
    path = save_rulebook(book)
    return {
        "ok": True,
        "channel_id": channel_id,
        "preset": preset,
        "rulebook": str(path),
        "resource": f"vf://presets/{channel_id}/kit",
        "warnings": warnings,
        "images": files,
    }


def learn_rule(
    channel_id: str,
    output: Path,
    *,
    notes: list[str] | None = None,
    mode: str = "merge",
    max_rules: int = 15,
) -> dict[str, Any]:
    """Compile human review notes into the channel rulebook."""

    context = _context(Path(output))
    CompileRuleStep().run(
        context,
        CompileRuleParams(
            channel_id=channel_id,
            review_notes=list(notes or []),
            mode=mode,  # type: ignore[arg-type]
            max_rules=max_rules,
        ),
        StepIO(stage="preset.compile_rule"),
    )
    book = context.metadata.get("preset_rulebook") or {}
    return {
        "ok": True,
        "channel_id": channel_id,
        "rulebook": context.artifacts.get("preset_rulebook", ""),
        "resource": f"vf://presets/{channel_id}/rulebook",
        "rules": book.get("learned_rules", []),
        "count": len(book.get("learned_rules", [])),
        "warnings": list(context.warnings),
    }


__all__ = ["clone_style", "learn_rule"]
