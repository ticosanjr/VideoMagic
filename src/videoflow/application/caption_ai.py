"""LLM-assisted caption decoration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.adapters.llm import OpenAICompatibleLlm
from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.short_editor import ShortEditOptions, edit_short
from videoflow.domain.errors import ShortEditError, StateNotReadyError
from videoflow.domain.state import ProjectState

PROMPT = """\
Pick 3 to 8 concrete, visual words from this short transcript and map each to
one fitting emoji. Do not repeat a word. Return only JSON:
{{"emojis":{{"word":"🔥"}}}}

Transcript:
{text}
"""


def generate_emoji_map(
    text: str,
    *,
    base_url: str,
    model: str,
    api_key: str | None,
    allow_external_services: bool,
    allowed_external_hosts: tuple[str, ...] = (),
) -> dict[str, str]:
    ensure_external_allowed(
        base_url,
        capability="caption_emoji_llm",
        allow_external_services=allow_external_services,
        allowed_hosts=allowed_external_hosts,
    )
    if not text.strip():
        raise ShortEditError("The Short has no transcript text for emoji generation.")
    payload = OpenAICompatibleLlm(
        base_url=base_url,
        model=model,
        api_key=api_key,
    ).complete_json(PROMPT.format(text=text[:6000]), "emoji_map")
    raw = payload.get("emojis")
    if not isinstance(raw, dict):
        raise ShortEditError("The LLM did not return an emoji map.")
    result: dict[str, str] = {}
    for word, emoji in raw.items():
        if not isinstance(word, str) or not isinstance(emoji, str):
            continue
        cleaned_word = word.strip()
        cleaned_emoji = emoji.strip()
        if cleaned_word and cleaned_emoji and len(cleaned_emoji) <= 8:
            result[cleaned_word] = cleaned_emoji
        if len(result) >= 12:
            break
    if not result:
        raise ShortEditError("The LLM returned an empty emoji map.")
    return result


def apply_llm_emoji(
    *,
    source: Path,
    output: Path,
    index: int,
    result: dict[str, Any],
    base_url: str,
    model: str,
    api_key: str | None,
    allow_external_services: bool,
    allowed_external_hosts: tuple[str, ...] = (),
) -> dict[str, Any]:
    output = output.expanduser().resolve()
    try:
        state = ProjectState.model_validate_json(
            (output / "project_state.json").read_text(encoding="utf-8")
        )
        report = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateNotReadyError(f"Cannot read the completed Shorts project: {exc}") from exc
    clips = report.get("clips")
    if not isinstance(clips, list) or index < 0 or index >= len(clips):
        raise ShortEditError(f"Short index {index} is out of range.")
    entry = clips[index]
    if not isinstance(entry, dict):
        raise ShortEditError(f"Short index {index} is invalid.")
    raw_pieces = entry.get("pieces") or []
    try:
        pieces = [(int(piece[0]), int(piece[1])) for piece in raw_pieces]
    except (TypeError, ValueError, IndexError) as exc:
        raise ShortEditError("The Short pieces are invalid.") from exc
    text = " ".join(
        sentence.text
        for sentence in state.transcript
        if any(
            sentence.end_sample > start and sentence.start_sample < end
            for start, end in pieces
        )
    )
    emoji_map = generate_emoji_map(
        text,
        base_url=base_url,
        model=model,
        api_key=api_key,
        allow_external_services=allow_external_services,
        allowed_external_hosts=allowed_external_hosts,
    )
    updated = edit_short(
        source=source,
        output=output,
        index=index,
        result=result,
        options=ShortEditOptions(
            caption_style={"emoji_enabled": True, "emoji_map": emoji_map}
        ),
    )
    updated["emoji_map"] = emoji_map
    return {"emoji_map": emoji_map, "short": updated}
