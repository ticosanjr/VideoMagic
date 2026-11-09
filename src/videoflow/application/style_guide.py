"""Art-direction helpers: palette extraction and a deterministic style guide."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.runtime import find_binary

LIGHT_PALETTE = ["#F8FAFC", "#111827", "#FF3B30", "#F59E0B", "#22C55E", "#2563EB"]
DARK_PALETTE = ["#080B10", "#F8FAFC", "#FF3B30", "#22C55E", "#F59E0B", "#38BDF8"]


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, value)):02X}" for value in rgb)


def palette_from_image(path: Path, *, colors: int = 6) -> list[str]:
    binary = find_binary("ffmpeg")
    if binary is None:
        return []
    command = [
        binary,
        "-v",
        "error",
        "-i",
        str(path),
        "-vf",
        "scale=64:64",
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    completed = subprocess.run(command, capture_output=True, check=False, timeout=30)
    if completed.returncode != 0 or len(completed.stdout) < 64 * 64 * 3:
        return []
    pixels = np.frombuffer(completed.stdout[: 64 * 64 * 3], dtype=np.uint8).reshape(-1, 3)
    quantized = (pixels // 16) * 16
    values, counts = np.unique(quantized, axis=0, return_counts=True)
    order = np.argsort(counts)[::-1]
    selected: list[str] = []
    for index in order:
        color = _hex(tuple(int(value) for value in values[index]))
        if color in selected:
            continue
        selected.append(color)
        if len(selected) >= colors:
            break
    return selected


def palette_from_images(paths: Iterable[Path], *, colors: int = 6) -> list[str]:
    counts: dict[str, int] = {}
    for path in paths:
        if not path.is_file():
            continue
        for color in palette_from_image(path, colors=colors):
            counts[color] = counts.get(color, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [color for color, _ in ordered[:colors]]


def default_style(theme: str = "dark", palette: list[str] | None = None) -> dict[str, Any]:
    chosen = palette or (DARK_PALETTE if theme == "dark" else LIGHT_PALETTE)
    return {
        "theme": theme,
        "palette": chosen,
        "typography": {
            "family": "Inter",
            "display": "Inter Tight",
            "mono": "JetBrains Mono",
            "body_size": 28,
            "caption_size": 64,
            "weights": [400, 600, 800],
        },
        "texture": {
            "paper_grain": 0.18 if theme == "light" else 0.08,
            "vignette": 0.35 if theme == "dark" else 0.12,
            "slate_overlay": theme == "dark",
            "document_framing": "high-contrast paper with 8% border",
        },
        "motion": {
            "default": "slow_push_in",
            "document": "highlight_underline",
            "transition": "cut",
            "zoom_range": [1.0, 1.12],
        },
        "audio": {
            "music_bed": "low drone with restrained pulse",
            "foley": ["paper_turn", "keyboard_click", "marker_underline"],
            "keyboard_notch_hz": 3500,
            "keyboard_notch_db": -4,
        },
        "rules": [
            "Use the approved palette only.",
            "Keep document framing readable at 1080p.",
            "Prefer hard cuts; reserve fades for chapter boundaries.",
            "Do not place captions over a face.",
        ],
    }


def render_markdown(style: dict[str, Any]) -> str:
    lines = [
        "# Project style guide",
        "",
        f"- Theme: {style.get('theme')}",
        f"- Palette: {', '.join(style.get('palette', []))}",
        f"- Typography: {style.get('typography', {}).get('family')}",
    ]
    for key in ("texture", "motion", "audio"):
        value = style.get(key) or {}
        lines.append(f"- {key.title()}: {json.dumps(value, ensure_ascii=False)}")
    rules = style.get("rules") or []
    if rules:
        lines.extend(["", "## Rules", *[f"- {rule}" for rule in rules]])
    return "\n".join(lines).rstrip() + "\n"


def merge_llm_style(base: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Merge a model suggestion without letting it remove required fields."""

    merged = json.loads(json.dumps(base))
    for key in ("theme", "palette", "typography", "texture", "motion", "audio", "rules"):
        value = payload.get(key)
        if value:
            merged[key] = value
    if not isinstance(merged.get("palette"), list) or not merged["palette"]:
        merged["palette"] = base["palette"]
    return merged


def color_name(value: str) -> str:
    text = re.sub(r"[^0-9A-Fa-f]", "", value)
    return f"#{text.upper()}" if len(text) == 6 else value
