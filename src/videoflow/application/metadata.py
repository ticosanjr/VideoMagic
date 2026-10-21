"""Deterministic social metadata generation.

The output is intentionally local and explainable. An LLM can be layered on
top later without changing the response shape.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

PLATFORM_LIMITS: dict[str, tuple[int, int]] = {
    "youtube": (100, 5000),
    "tiktok": (150, 2200),
    "instagram": (150, 2200),
    "linkedin": (200, 3000),
}

PLATFORM_TAGS: dict[str, tuple[str, ...]] = {
    "youtube": ("#Shorts", "#Video"),
    "tiktok": ("#fyp", "#foryou"),
    "instagram": ("#Reels", "#Explore"),
    "linkedin": ("#Video", "#Insights"),
}

TONE_CTA = {
    "engaging": "Watch to the end.",
    "professional": "A practical takeaway for your next decision.",
    "educational": "Save this for later.",
    "bold": "This changes how you look at it.",
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "com", "da", "das", "de",
    "do", "dos", "e", "em", "for", "from", "in", "is", "it", "na", "nas", "no",
    "nos", "o", "of", "on", "or", "os", "para", "por", "que", "the", "to",
    "um", "uma", "with", "you", "your", "this", "that", "it's", "i",
}


@dataclass(frozen=True, slots=True)
class MetadataResult:
    title: str
    description: str
    hashtags: tuple[str, ...]
    platform: str
    tone: str
    title_limit: int
    description_limit: int

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "description": self.description,
            "hashtags": list(self.hashtags),
            "platform": self.platform,
            "tone": self.tone,
            "character_limits": {
                "title": self.title_limit,
                "description": self.description_limit,
            },
        }


def generate_metadata(
    text: str,
    *,
    title: str = "",
    platform: str = "youtube",
    tone: str = "engaging",
    extra_hashtags: tuple[str, ...] = (),
) -> MetadataResult:
    platform_key = platform.casefold()
    if platform_key not in PLATFORM_LIMITS:
        raise ValueError(f"Unsupported platform: {platform}")
    tone_key = tone.casefold()
    if tone_key not in TONE_CTA:
        raise ValueError(f"Unsupported tone: {tone}")
    title_limit, description_limit = PLATFORM_LIMITS[platform_key]
    cleaned = " ".join(text.split())
    base_title = (title.strip() or _first_sentence(cleaned) or "New clip").strip()
    generated_title = _truncate(base_title, title_limit)
    tags = _hashtags(cleaned, platform_key, extra_hashtags)
    description_text = _truncate(cleaned, max(60, description_limit - 160))
    description = f"{description_text}\n\n{TONE_CTA[tone_key]} {' '.join(tags)}".strip()
    description = _truncate(description, description_limit)
    return MetadataResult(
        title=generated_title,
        description=description,
        hashtags=tags,
        platform=platform_key,
        tone=tone_key,
        title_limit=title_limit,
        description_limit=description_limit,
    )


def _first_sentence(text: str) -> str:
    match = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    return match[0].strip() if match else text


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"


def _hashtags(text: str, platform: str, extra: tuple[str, ...]) -> tuple[str, ...]:
    words = [
        word
        for word in re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", text.casefold())
        if word not in STOPWORDS
    ]
    tags: list[str] = []
    for tag in (*PLATFORM_TAGS[platform], *extra):
        cleaned = _tag(tag)
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    for word, _count in Counter(words).most_common(6):
        cleaned = _tag(word)
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tuple(tags[:8])


def _tag(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-zÀ-ÿ0-9]+", "", value.strip())
    return f"#{cleaned}" if cleaned else ""
