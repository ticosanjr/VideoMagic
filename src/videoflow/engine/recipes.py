"""Built-in recipes and user-recipe discovery."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from videoflow.core.recipe import RECIPE_ID, Recipe, load_recipe, parse_recipe
from videoflow.domain.errors import RecipeError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import portable_home

_INGEST = {
    "id": "ingest",
    "type": "ingest",
    "params": {"extract_pcm": True},
}
_VAD = {
    "id": "vad",
    "type": "audio.vad",
    "needs": ["ingest"],
    "params": {},
}
_TRANSCRIBE = {
    "id": "transcribe",
    "type": "transcribe",
    "needs": ["ingest"],
    "params": {"mode": "auto", "language": "pt", "model_size": "small"},
}
_TRANSLATE = {
    "id": "translation",
    "type": "transcript.translate",
    "needs": ["transcribe"],
    "params": {"target_language": "en"},
}
_RETAKES = {
    "id": "retakes",
    "type": "retakes.cull",
    "needs": ["vad", "transcribe"],
    "params": {"enabled": True},
}
_TIMELINE = {
    "id": "timeline",
    "type": "edit.timeline",
    "needs": ["vad", "retakes"],
    "params": {},
}
_TIMELINE_NO_RETAKES = {**_TIMELINE, "needs": ["vad"]}
_EXPORT = {
    "id": "export",
    "type": "export.nle",
    "needs": ["timeline"],
    "params": {
        "targets": ["resolve", "premiere", "kdenlive"],
        "filename_mode": "source_timestamp",
    },
}
_EXPORT_WITH_SHORTS = {
    **_EXPORT,
    "needs": ["timeline", "render_shorts"],
}
BUILTIN_RECIPES: dict[str, dict[str, Any]] = {
    "youtube_talking_head": {
        "schema_version": 1,
        "id": "youtube_talking_head",
        "name": "YouTube talking head",
        "description": (
            "Clean speech, remove repeats, build the main timeline, and export an NLE project."
        ),
        "llm": {"provider": "none"},
        "steps": [_INGEST, _VAD, _TRANSCRIBE, _RETAKES, _TIMELINE, _EXPORT],
    },
    "viral_shorts_batch": {
        "schema_version": 1,
        "id": "viral_shorts_batch",
        "name": "Viral Shorts batch",
        "description": "Main timeline plus three vertical Shorts with burned captions.",
        "llm": {"provider": "none"},
        "steps": [
            _INGEST,
            _VAD,
            _TRANSCRIBE,
            {
                "id": "translation",
                "type": "transcript.translate",
                "needs": ["transcribe"],
                "params": {"target_language": "en"},
            },
            _RETAKES,
            _TIMELINE,
            {
                "id": "shorts",
                "type": "shorts.select",
                "needs": ["transcribe", "retakes"],
                "params": {
                    "target_duration_min_sec": 30,
                    "target_duration_max_sec": 60,
                    "min_clips": 1,
                    "max_clips_to_generate": 3,
                    "selection_mode": "auto",
                    "burn_subtitles": True,
                },
            },
            {
                "id": "score",
                "type": "shorts.score",
                "needs": ["shorts"],
                "params": {"profile": "default", "top_k": 3},
            },
            {
                "id": "reframe",
                "type": "shorts.reframe",
                "needs": ["score"],
                "params": {"mode": "center_crop_9_16"},
            },
            {
                "id": "captions",
                "type": "shorts.captions",
                "needs": ["score"],
                "params": {"enabled": True},
            },
            {
                "id": "render_shorts",
                "type": "shorts.render",
                "needs": ["reframe", "captions"],
                "params": {"burn_subtitles": True},
            },
            _EXPORT_WITH_SHORTS,
        ],
    },
    "content_cycle": {
        "schema_version": 1,
        "id": "content_cycle",
        "name": "Content cycle",
        "description": (
            "Full content lifecycle: idea, research, script, storyboard, production, "
            "audio, Shorts, titles, thumbnail, publishing, analytics, and review. "
            "Planned nodes are bypassed until implemented."
        ),
        "llm": {"provider": "none"},
        "steps": [
            {"id": "idea", "type": "content.idea", "params": {}},
            {"id": "research", "type": "content.research", "needs": ["idea"], "params": {}},
            {"id": "script", "type": "content.script", "needs": ["research"], "params": {}},
            _INGEST,
            _VAD,
            _TRANSCRIBE,
            _RETAKES,
            _TIMELINE,
            {
                "id": "storyboard",
                "type": "storyboard.plan",
                "needs": ["script", "timeline"],
                "params": {},
            },
            {
                "id": "assets",
                "type": "assets.index",
                "needs": ["ingest"],
                "params": {"asset_dir": ""},
            },
            {
                "id": "shorts",
                "type": "shorts.select",
                "needs": ["transcribe", "retakes"],
                "params": {
                    "target_duration_min_sec": 30,
                    "target_duration_max_sec": 60,
                    "min_clips": 1,
                    "max_clips_to_generate": 3,
                    "selection_mode": "auto",
                },
            },
            {
                "id": "score",
                "type": "shorts.score",
                "needs": ["shorts"],
                "params": {"profile": "default", "top_k": 3},
            },
            {
                "id": "reframe",
                "type": "shorts.reframe",
                "needs": ["score"],
                "params": {"mode": "center_crop_9_16"},
            },
            {
                "id": "captions",
                "type": "shorts.captions",
                "needs": ["score"],
                "params": {"enabled": True},
            },
            {
                "id": "render_shorts",
                "type": "shorts.render",
                "needs": ["reframe", "captions"],
                "params": {"burn_subtitles": True},
            },
            {
                "id": "color",
                "type": "color.grade",
                "needs": ["timeline"],
                "params": {},
            },
            {
                "id": "audio_master",
                "type": "audio.master",
                "needs": ["timeline"],
                "params": {},
            },
            {
                "id": "audio_qa",
                "type": "audio.qa",
                "needs": ["audio_master"],
                "params": {},
            },
            {
                "id": "titles",
                "type": "titles.plan",
                "needs": ["timeline"],
                "params": {},
            },
            {
                "id": "thumbnail",
                "type": "thumbnail.generate",
                "needs": ["render_shorts"],
                "params": {},
            },
            {
                "id": "publish",
                "type": "publish.webhook",
                "needs": ["render_shorts", "thumbnail"],
                "params": {},
            },
            {
                "id": "analytics",
                "type": "analytics.import",
                "needs": ["publish"],
                "params": {},
            },
            {
                "id": "review",
                "type": "review.queue",
                "needs": ["titles", "thumbnail"],
                "params": {},
            },
            _EXPORT_WITH_SHORTS,
        ],
    },
    "full_podcast_curation": {
        "schema_version": 1,
        "id": "full_podcast_curation",
        "name": "Full podcast curation",
        "description": (
            "Long-form cut, NLE exports, and five Shorts with audio-energy and scene boosts."
        ),
        "llm": {"provider": "none"},
        "steps": [
            _INGEST,
            _VAD,
            _TRANSCRIBE,
            _RETAKES,
            _TIMELINE,
            {
                "id": "shorts",
                "type": "shorts.select",
                "needs": ["transcribe", "retakes"],
                "params": {
                    "target_duration_min_sec": 25,
                    "target_duration_max_sec": 55,
                    "min_clips": 1,
                    "max_clips_to_generate": 5,
                    "selection_mode": "auto",
                    "audio_energy_boost": True,
                    "scene_change_boost": True,
                    "burn_subtitles": True,
                },
            },
            {
                "id": "score",
                "type": "shorts.score",
                "needs": ["shorts"],
                "params": {"profile": "podcast", "top_k": 5},
            },
            {
                "id": "reframe",
                "type": "shorts.reframe",
                "needs": ["score"],
                "params": {"mode": "center_crop_9_16"},
            },
            {
                "id": "captions",
                "type": "shorts.captions",
                "needs": ["score"],
                "params": {"enabled": True},
            },
            {
                "id": "render_shorts",
                "type": "shorts.render",
                "needs": ["reframe", "captions"],
                "params": {"burn_subtitles": True},
            },
            _EXPORT_WITH_SHORTS,
        ],
    },
}




def _add_recipe(
    recipe_id: str,
    name: str,
    steps: list[dict[str, Any]],
    *,
    description: str = "",
    variables: dict[str, Any] | None = None,
    variants: list[dict[str, Any]] | None = None,
) -> None:
    BUILTIN_RECIPES[recipe_id] = {
        "schema_version": 1,
        "id": recipe_id,
        "name": name,
        "description": description or name,
        "llm": {"provider": "none"},
        "variables": variables or {},
        "variants": variants or [],
        "steps": steps,
    }


def _shorts(
    *,
    minimum: int = 30,
    maximum: int = 60,
    count: int = 3,
    profile: str = "default",
    top_k: int = 0,
    hook_mode: str = "off",
    selection_mode: str = "auto",
    aspect: str = "9:16",
    caption_size: int = 72,
) -> list[dict[str, Any]]:
    return [
        {**_INGEST},
        {**_VAD},
        {**_TRANSCRIBE},
        {**_RETAKES},
        {
            "id": "shorts",
            "type": "shorts.select",
            "needs": ["transcribe", "retakes"],
            "params": {
                "target_duration_min_sec": minimum,
                "target_duration_max_sec": maximum,
                "min_clips": 1,
                "max_clips_to_generate": count,
                "selection_mode": selection_mode,
                "hook_mode": hook_mode,
                "aspect_ratio": aspect,
                "audio_energy_boost": True,
                "scene_change_boost": True,
            },
        },
        {
            "id": "score",
            "type": "shorts.score",
            "needs": ["shorts"],
            "params": {"profile": profile, "top_k": top_k},
        },
        {
            "id": "reframe",
            "type": "shorts.reframe",
            "needs": ["score"],
            "params": {"mode": "center_crop_9_16"},
        },
        {
            "id": "captions",
            "type": "shorts.captions",
            "needs": ["score"],
            "params": {
                "enabled": True,
                "caption_style": {"font_size": caption_size},
            },
        },
        {
            "id": "render",
            "type": "shorts.render",
            "needs": ["reframe", "captions"],
            "params": {
                "burn_subtitles": True,
                "caption_style": {"font_size": caption_size},
            },
        },
    ]


_add_recipe(
    "rough_cut_only",
    "Rough cut only",
    [_INGEST, _VAD, _TIMELINE_NO_RETAKES, _EXPORT],
    description="Remove silence, build the main timeline, and export NLE files.",
)
_add_recipe(
    "captions_only",
    "Captions only",
    [_INGEST, _VAD, _TRANSCRIBE, _TIMELINE_NO_RETAKES],
    description="Transcribe the source and build the main timeline for captions.",
)
_add_recipe(
    "nle_export_only",
    "NLE export only",
    [_INGEST, _VAD, _TRANSCRIBE, _TIMELINE_NO_RETAKES, _EXPORT],
    description="Build and export the main timeline without Shorts.",
)
_add_recipe(
    "clean_audio",
    "Clean audio",
    [
        _INGEST,
        {"id": "master", "type": "audio.master", "needs": ["ingest"], "params": {}},
        {"id": "qa", "type": "audio.qa", "needs": ["master"], "params": {}},
    ],
    description="Denoise, high-pass, and normalize the dialogue bed.",
)
_add_recipe(
    "chapter_markers",
    "Chapter markers",
    [
        _INGEST,
        _VAD,
        _TRANSCRIBE,
        {"id": "chapters", "type": "chapters.plan", "needs": ["transcribe"], "params": {}},
    ],
    description="Create chapter markers from the transcript.",
)

_add_recipe(
    "shorts_select_only",
    "Shorts select only",
    _shorts()[:6]
    + [
        {
            "id": "review",
            "type": "human.gate",
            "needs": ["score"],
            "params": {"gate_id": "shorts", "title": "Approve Shorts"},
        }
    ],
    description="Select, score, and approve Shorts without rendering.",
)
_add_recipe(
    "shorts_render_only",
    "Shorts render only",
    _shorts(minimum=20, maximum=60, count=5, top_k=5),
    description="Select, score, reframe, caption, and render Shorts.",
)
_add_recipe(
    "best_moments",
    "Best moments",
    _shorts(minimum=20, maximum=75, count=8, top_k=5, profile="hook"),
    description="Find the strongest moments and keep the five best.",
)
_add_recipe(
    "hook_first",
    "Hook first",
    _shorts(minimum=20, maximum=55, count=5, top_k=5, hook_mode="reorder"),
    description="Reorder each Short so the strongest hook comes first.",
)
_add_recipe(
    "trailer",
    "Trailer",
    _shorts(minimum=15, maximum=35, count=3, top_k=3, profile="hook"),
    description="Build a short highlight reel from the strongest moments.",
)
_add_recipe(
    "review_gate",
    "Review gate",
    _shorts()[:6]
    + [
        {
            "id": "review",
            "type": "human.gate",
            "needs": ["score"],
            "params": {"gate_id": "shorts", "title": "Approve Shorts"},
        },
        {
            "id": "reframe",
            "type": "shorts.reframe",
            "needs": ["review"],
            "params": {"mode": "center_crop_9_16"},
        },
        {
            "id": "captions",
            "type": "shorts.captions",
            "needs": ["review"],
            "params": {"enabled": True},
        },
        {
            "id": "render",
            "type": "shorts.render",
            "needs": ["reframe", "captions"],
            "params": {"burn_subtitles": True},
        },
    ],
    description="Pause for human approval before rendering Shorts.",
)

_hook_ab_steps = _shorts(minimum=20, maximum=60, count=3)
_score_index = next(
    index for index, step in enumerate(_hook_ab_steps) if step.get("type") == "shorts.score"
)
_hook_ab_steps.insert(
    _score_index + 1,
    {"id": "ab", "type": "shorts.ab", "needs": ["score"], "params": {}},
)
for _step in _hook_ab_steps:
    if _step.get("id") in {"reframe", "captions"} and "score" in _step.get("needs", []):
        _step["needs"] = ["ab" if item == "score" else item for item in _step["needs"]]
_add_recipe(
    "hook_duration_ab",
    "Hook and duration A/B",
    _hook_ab_steps,
    description="Real hook and duration variants per Short, rendered for comparison.",
)

_variant_base = _shorts()[:5]
_variant_base[-1] = {
    "id": "shorts",
    "type": "shorts.select",
    "needs": ["transcribe", "retakes"],
    "params": {
        "target_duration_min_sec": 30,
        "target_duration_max_sec": 60,
        "min_clips": 1,
        "max_clips_to_generate": 3,
        "selection_mode": "auto",
        "aspect_ratio": "{{ aspect }}",
        "hook_mode": "{{ hook_mode }}",
    },
}
_variant_base += [
    {"id": "score", "type": "shorts.score", "needs": ["shorts"], "params": {}},
    {
        "id": "reframe",
        "type": "shorts.reframe",
        "needs": ["score"],
        "params": {"mode": "center_crop_9_16"},
    },
    {
        "id": "captions",
        "type": "shorts.captions",
        "needs": ["score"],
        "params": {"enabled": True, "caption_style": {"font_size": "{{ caption_size }}"}},
    },
    {
        "id": "render",
        "type": "shorts.render",
        "needs": ["reframe", "captions"],
        "params": {
            "burn_subtitles": True,
            "caption_style": {"font_size": "{{ caption_size }}"},
        },
    },
]
_add_recipe(
    "reframe_variants",
    "Reframe variants",
    _variant_base,
    description="Render 9:16, 1:1, and 16:9 variants.",
    variables={
        "aspect": {"type": "enum", "default": "9:16", "options": ["9:16", "1:1", "16:9"]},
        "hook_mode": {"type": "enum", "default": "off", "options": ["off", "metadata", "reorder"]},
        "caption_size": {"type": "number", "default": 72},
    },
    variants=[
        {"name": "9x16", "variables": {"aspect": "9:16", "caption_size": 72}},
        {"name": "1x1", "variables": {"aspect": "1:1", "caption_size": 64}},
        {"name": "16x9", "variables": {"aspect": "16:9", "caption_size": 56}},
    ],
)
_add_recipe(
    "caption_styles",
    "Caption styles",
    _variant_base,
    description="Render caption style variants.",
    variables={
        "aspect": {"type": "string", "default": "9:16"},
        "hook_mode": {"type": "string", "default": "off"},
        "caption_size": {"type": "number", "default": 72},
    },
    variants=[
        {"name": "clean", "variables": {"caption_size": 64}},
        {"name": "bold", "variables": {"caption_size": 84}},
        {"name": "large", "variables": {"caption_size": 96}},
    ],
)
_add_recipe(
    "ab_test_variants",
    "A/B test variants",
    _variant_base,
    description="Render hook A/B variants for comparison.",
    variables={
        "aspect": {"type": "string", "default": "9:16"},
        "hook_mode": {"type": "enum", "default": "off", "options": ["off", "metadata", "reorder"]},
        "caption_size": {"type": "number", "default": 72},
    },
    variants=[
        {"name": "hook-off", "variables": {"hook_mode": "off"}},
        {"name": "hook-metadata", "variables": {"hook_mode": "metadata"}},
        {"name": "hook-reorder", "variables": {"hook_mode": "reorder"}},
    ],
)

for recipe_id, label, profile in (
    ("podcast_to_shorts", "Podcast to Shorts", "podcast"),
    ("interview_quotes", "Interview quotes", "default"),
    ("lecture_to_shorts", "Lecture to Shorts", "education"),
    ("product_demo_shorts", "Product demo Shorts", "default"),
    ("testimonial_quotes", "Testimonial quotes", "default"),
    ("livestream_highlights", "Livestream highlights", "hook"),
):
    _add_recipe(
        recipe_id,
        label,
        _shorts(minimum=20, maximum=60, count=5, top_k=3, profile=profile),
        description=f"{label} pipeline with scoring and rendering.",
    )

_add_recipe(
    "webinar_chapters",
    "Webinar chapters",
    [
        _INGEST,
        _VAD,
        _TRANSCRIBE,
        _TIMELINE_NO_RETAKES,
        {
            "id": "chapters",
            "type": "chapters.plan",
            "needs": ["transcribe"],
            "params": {},
        },
        _EXPORT,
    ],
    description="Build a chaptered webinar timeline and NLE export.",
)
_add_recipe(
    "broll_pass",
    "B-roll pass",
    _shorts()[:6]
    + [
        {
            "id": "match",
            "type": "assets.match",
            "needs": ["shorts"],
            "params": {},
        },
        {
            "id": "reframe",
            "type": "shorts.reframe",
            "needs": ["score"],
            "params": {"mode": "center_crop_9_16"},
        },
        {
            "id": "captions",
            "type": "shorts.captions",
            "needs": ["score"],
            "params": {"enabled": True},
        },
        {
            "id": "render",
            "type": "shorts.render",
            "needs": ["reframe", "captions", "match"],
            "params": {"burn_subtitles": True},
        },
    ],
    description="Match local B-roll and render Shorts with overlays.",
)
_add_recipe(
    "music_pass",
    "Music pass",
    _shorts()[:6]
    + [
        {"id": "beats", "type": "music.beat", "needs": ["ingest"], "params": {}},
        {
            "id": "reframe",
            "type": "shorts.reframe",
            "needs": ["score"],
            "params": {"mode": "center_crop_9_16"},
        },
        {
            "id": "captions",
            "type": "shorts.captions",
            "needs": ["score"],
            "params": {"enabled": True},
        },
        {
            "id": "render",
            "type": "shorts.render",
            "needs": ["reframe", "captions", "beats"],
            "params": {"burn_subtitles": True},
        },
    ],
    description="Add a beat grid and render Shorts with music/SFX planning.",
)
_add_recipe(
    "sfx_pass",
    "SFX pass",
    _shorts()[:6]
    + [
        {"id": "sfx", "type": "sfx.plan", "needs": ["ingest"], "params": {}},
        {
            "id": "reframe",
            "type": "shorts.reframe",
            "needs": ["score"],
            "params": {"mode": "center_crop_9_16"},
        },
        {
            "id": "captions",
            "type": "shorts.captions",
            "needs": ["score"],
            "params": {"enabled": True},
        },
        {
            "id": "render",
            "type": "shorts.render",
            "needs": ["reframe", "captions", "sfx"],
            "params": {"burn_subtitles": True},
        },
    ],
    description="Plan SFX cues and render Shorts.",
)
_add_recipe(
    "metadata_pack",
    "Metadata pack",
    _shorts()[:6]
    + [
        {
            "id": "metadata",
            "type": "metadata.pack",
            "needs": ["shorts"],
            "params": {"platform": "youtube"},
        }
    ],
    description="Generate per-Short metadata without rendering.",
)
_add_recipe(
    "thumbnail_pack",
    "Thumbnail pack",
    _shorts(minimum=20, maximum=60, count=5, top_k=3),
    description="Render Shorts and one thumbnail variant per Short.",
)
_add_recipe(
    "publish_queue",
    "Publish queue",
    _shorts(minimum=20, maximum=60, count=3, top_k=3)
    + [
        {
            "id": "metadata",
            "type": "metadata.pack",
            "needs": ["render"],
            "params": {"platform": "youtube"},
        },
        {
            "id": "queue",
            "type": "publish.queue",
            "needs": ["render"],
            "params": {},
        },
    ],
    description="Render Shorts and enqueue them for publishing.",
)
_add_recipe(
    "analytics_review",
    "Analytics review",
    [
        _INGEST,
        {
            "id": "analytics",
            "type": "analytics.import",
            "params": {},
        },
        {
            "id": "review",
            "type": "analytics.review",
            "needs": ["analytics"],
            "params": {},
        },
        {"id": "evaluate", "type": "experiment.evaluate", "params": {}},
    ],
    description="Import analytics and evaluate the current experiment.",
)
_add_recipe(
    "localization_dub",
    "Localization / dub",
    _shorts(minimum=20, maximum=60, count=3, top_k=3)
    + [
        _TRANSLATE,
        {
            "id": "dub",
            "type": "localization.dub",
            "needs": ["render", "translation"],
            "params": {"target_language": "en"},
        },
    ],
    description="Translate, render, and dub Shorts into another language.",
)
_add_recipe(
    "finishing_pass",
    "Finishing pass",
    [
        _INGEST,
        _VAD,
        _TRANSCRIBE,
        _RETAKES,
        _TIMELINE,
        {
            "id": "color",
            "type": "color.grade",
            "needs": ["timeline"],
            "params": {},
        },
        {
            "id": "titles",
            "type": "titles.plan",
            "needs": ["timeline"],
            "params": {},
        },
        {
            "id": "master",
            "type": "audio.master",
            "needs": ["ingest"],
            "params": {},
        },
        {"id": "qa", "type": "audio.qa", "needs": ["master"], "params": {}},
        _EXPORT,
        {
            "id": "nle_qa",
            "type": "nle.qa",
            "needs": ["export"],
            "params": {},
        },
    ],
    description="Color, titles, audio master, exports, and NLE QA.",
)

def _localized_steps() -> list[dict[str, Any]]:
    """Viral Shorts followed by one dubbing step before the NLE export."""

    steps = [dict(step) for step in BUILTIN_RECIPES["viral_shorts_batch"]["steps"]]
    insert_at = next(
        (index for index, step in enumerate(steps) if step.get("type") == "export.nle"),
        len(steps),
    )
    steps.insert(
        insert_at,
        {
            "id": "dub",
            "type": "localization.dub",
            "needs": ["render_shorts"],
            "params": {"target_language": "en", "original_volume": 0.15},
        },
    )
    return steps


BUILTIN_RECIPES["localized_shorts"] = {
    "schema_version": 1,
    "id": "localized_shorts",
    "name": "Localized Shorts",
    "description": (
        "Viral Shorts plus an optional translated dub per Short when a TTS provider is configured."
    ),
    "llm": {"provider": "none"},
    "steps": _localized_steps(),
}


def _recut_steps(*, with_retakes: bool) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = [
        {"id": "ingest", "type": "ingest", "params": {"extract_pcm": True}},
        {
            "id": "vad",
            "type": "audio.vad",
            "needs": ["ingest"],
            "inputs": {"media": "ingest.media"},
            "params": {
                "engine": "auto",
                "noise_db": -30.0,
                "speech_threshold": 0.5,
                "min_silence_ms": 350,
                "min_speech_ms": 120,
                "spike_suppression_ms": 180,
                "merge_gap_ms": 120,
                "pad_before_ms": 80,
                "pad_after_ms": 120,
                "apply_pads": False,
            },
        },
    ]
    timeline_needs = ["vad"]
    if with_retakes:
        steps.append(
            {
                "id": "transcribe",
                "type": "transcribe",
                "needs": ["ingest"],
                "inputs": {"media": "ingest.media"},
                "params": {"mode": "auto", "language": "pt", "model_size": "small"},
            }
        )
        steps.append(
            {
                "id": "retakes",
                "type": "retakes.cull",
                "needs": ["vad", "transcribe"],
                "inputs": {
                    "speech": "vad.speech",
                    "transcript": "transcribe.transcript",
                },
                "params": {
                    "enabled": True,
                    "strategy": "keep_last",
                    "strictness": "balanced",
                },
            }
        )
        timeline_needs.append("retakes")
    steps.append(
        {
            "id": "timeline",
            "type": "edit.timeline",
            "needs": timeline_needs,
            "inputs": (
                {
                    "speech": "retakes.speech",
                    "transcript": "transcribe.transcript",
                    "silence": "vad.silence",
                    "retakes": "retakes.retakes",
                }
                if with_retakes
                else {"speech": "vad.speech", "silence": "vad.silence"}
            ),
            "params": {
                "cut_mode": "hard",
                "enable_j_cuts": False,
                "enable_l_cuts": False,
                "offset_ms": 200,
                "audio_crossfade_ms": 20,
                "fade_in_ms": 20,
                "fade_out_ms": 20,
                "handle_check": True,
                "transition_frames": 0,
                "transition_type": "crossfade",
                "zoom_mode": "manual_rules",
            },
        }
    )
    steps.append(
        {
            "id": "export",
            "type": "export.nle",
            "needs": ["timeline"],
            "inputs": {"timeline": "timeline.timeline"},
            "params": {
        "targets": ["resolve", "premiere", "kdenlive"],
        "filename_mode": "source_timestamp",
    },
        }
    )
    return steps


_add_recipe(
    "recut_replacement",
    "Recut Replacement",
    _recut_steps(with_retakes=False),
    description=(
        "Remove silence with detailed VAD controls, choose a hard/J/L cut, and "
        "export Resolve, Premiere, and Kdenlive timelines. Render the MP4 from "
        "the Edit tab when the cut is final."
    ),
)
_add_recipe(
    "recut_replacement_retakes",
    "Recut Replacement + retakes",
    _recut_steps(with_retakes=True),
    description=(
        "The Recut Replacement flow plus transcription and retake culling before "
        "the timeline, with the same detailed silence and cut controls."
    ),
)


def _recut_preset(
    recipe_id: str,
    name: str,
    description: str,
    *,
    with_retakes: bool,
    vad: dict[str, object],
    timeline: dict[str, object],
) -> None:
    steps = _recut_steps(with_retakes=with_retakes)
    for step in steps:
        if step["id"] == "vad":
            step["params"] = {**step["params"], **vad}
        if step["id"] == "timeline":
            step["params"] = {**step["params"], **timeline}
    _add_recipe(recipe_id, name, steps, description=description)


_recut_preset(
    "recut_podcast",
    "Recut Podcast",
    "Two-speaker podcast recut with retakes, J-cuts, and generous handles.",
    with_retakes=True,
    vad={
        "noise_db": -34.0,
        "speech_threshold": 0.45,
        "min_silence_ms": 500,
        "min_speech_ms": 140,
        "spike_suppression_ms": 260,
        "merge_gap_ms": 180,
        "pad_before_ms": 120,
        "pad_after_ms": 180,
    },
    timeline={
        "cut_mode": "j_cut",
        "enable_j_cuts": True,
        "enable_l_cuts": False,
        "offset_ms": 220,
        "audio_crossfade_ms": 30,
    },
)
_recut_preset(
    "recut_lecture",
    "Recut Lecture",
    "Deterministic class or webinar recut with hard cuts and wide handles.",
    with_retakes=False,
    vad={
        "noise_db": -38.0,
        "speech_threshold": 0.4,
        "min_silence_ms": 650,
        "min_speech_ms": 160,
        "spike_suppression_ms": 300,
        "merge_gap_ms": 220,
        "pad_before_ms": 150,
        "pad_after_ms": 220,
    },
    timeline={"cut_mode": "hard", "offset_ms": 200, "audio_crossfade_ms": 20},
)
_recut_preset(
    "recut_social",
    "Recut Social",
    "Tight social recut with retakes, short handles, and L-cuts.",
    with_retakes=True,
    vad={
        "noise_db": -24.0,
        "speech_threshold": 0.62,
        "min_silence_ms": 240,
        "min_speech_ms": 90,
        "spike_suppression_ms": 120,
        "merge_gap_ms": 70,
        "pad_before_ms": 40,
        "pad_after_ms": 60,
    },
    timeline={
        "cut_mode": "l_cut",
        "enable_j_cuts": False,
        "enable_l_cuts": True,
        "offset_ms": 180,
        "audio_crossfade_ms": 15,
    },
)


_add_recipe(
    "deepseek_full_edit",
    "DeepSeek full edit",
    [
        _INGEST,
        _VAD,
        {
            **_TRANSCRIBE,
            "params": {
                "mode": "auto",
                "language": "pt",
                "model_size": "large-v3",
                "model_id": "faster-whisper-large-v3",
            },
        },
        {
            **_RETAKES,
            "params": {
                "provider_id": "deepseek",
                "enabled": True,
                "strategy": "keep_last",
                "strictness": "balanced",
                "single_pass": True,
                "context_window": 25,
                "max_group_span_seconds": 180,
                "max_discard_ratio": 0.45,
            },
        },
        {
            "id": "llm_cleanup",
            "type": "llm.cleanup",
            "needs": ["retakes"],
            "inputs": {
                "transcript": "retakes.transcript",
                "discarded": "retakes.discarded",
            },
            "params": {
                "provider_id": "deepseek",
                "max_words": 10,
                "max_cuts": 12,
                "prompt": (
                    "Remove only clear out-of-context interruptions such as a "
                    "remark about the room or recording. Preserve sponsor "
                    "segments, prices, links, CTAs, examples, and any sentence "
                    "that introduces new information."
                ),
            },
        },
        {
            **_TIMELINE,
            "needs": ["vad", "retakes", "llm_cleanup"],
            "params": {
                "cut_mode": "hard",
                "replace_manual": True,
                "zoom_mode": "manual_rules",
                "use_transcript_spans": True,
                "noise_filter": "non_speech",
                "noise_min_ms": 180,
                "pad_before_ms": 60,
                "pad_after_ms": 120,
                "max_internal_gap_ms": 150,
                "internal_gap_mode": "smart",
                "gap_energy_threshold": 800,
                "long_gap_ms": 800,
                "drop_isolated_words": False,
                "detect_repeats": True,
                "repeat_min_words": 5,
                "repeat_max_gap_seconds": 120.0,
                "repeat_pad_ms": 40,
                "repeat_max_cuts": 60,
                "word_cut_max_ratio": 0.2,
                "max_silence_ms": 500,
                "keep_silence_ms": 300,
                "silence_threshold_db": -35.0,
                "silence_frame_ms": 10,
                "min_clip_ms": 200,
            },
        },
        {
            "id": "llm_zoom",
            "type": "llm.zoom",
            "enabled": False,
            "needs": ["timeline"],
            "inputs": {"timeline": "timeline.timeline"},
            "params": {
                "provider_id": "deepseek",
                "max_actions": 24,
                "prompt": (
                    "This is a talking-head video. Read each clip's text and choose "
                    "at most one subtle zoom per major beat. Use punch_in or a smooth "
                    "envelope for numbers, comparisons, reveals, and key claims. "
                    "Never zoom non-speech or ellipsis clips, and do not alternate "
                    "zoom in/out at every hard cut."
                ),
            },
        },
        {
            "id": "llm_style",
            "type": "llm.style",
            "enabled": False,
            "needs": ["llm_zoom"],
            "inputs": {"timeline": "llm_zoom.timeline"},
            "params": {
                "provider_id": "deepseek",
                "max_actions": 16,
                "prompt": (
                    "Add only the transitions and fades that help the story. Keep "
                    "hard cuts as the default. Use a gentle fade at the start and "
                    "end, and avoid drawing attention to non-speech clips."
                ),
            },
        },
        {
            **_EXPORT,
            "needs": ["timeline"],
            "inputs": {"timeline": "timeline.timeline"},
        },
        {
            "id": "video_export",
            "type": "export.video",
            "needs": ["timeline"],
            "inputs": {"timeline": "timeline.timeline"},
            "params": {
                "preset": "ultrafast",
                "subdir": "exports",
                "filename_mode": "source_timestamp",
                "filename": "video.mp4",
            },
        },
    ],
    description=(
        "Transcribe, group retakes with DeepSeek, remove clear out-of-context "
        "asides, cap silence to a tight reference profile, and export NLE and "
        "MP4. Zoom and style nodes remain available but disabled."
    ),
)


def builtin_recipe(recipe_id: str) -> Recipe:
    try:
        payload = BUILTIN_RECIPES[recipe_id]
    except KeyError as exc:
        raise RecipeError(f"Unknown recipe: {recipe_id}") from exc
    return parse_recipe(payload)


def user_recipes_dir() -> Path:
    return portable_home() / "recipes"


def list_recipes() -> list[dict[str, object]]:
    recipes: list[dict[str, object]] = []
    seen: set[str] = set()
    directory = user_recipes_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            try:
                recipe = load_recipe(path)
            except RecipeError:
                continue
            if recipe.id in seen:
                continue
            recipes.append(
                {
                    "id": recipe.id,
                    "name": recipe.name,
                    "description": recipe.description,
                    "source": str(path),
                }
            )
            seen.add(recipe.id)
    for recipe_id, payload in BUILTIN_RECIPES.items():
        if recipe_id in seen:
            continue
        recipes.append(
            {
                "id": recipe_id,
                "name": payload["name"],
                "description": payload.get("description", ""),
                "source": "builtin",
            }
        )
        seen.add(recipe_id)
    return recipes


def resolve_recipe_paths(recipe: Recipe, roots: list[Path]) -> Recipe:
    """Resolve operator-supplied paths inside the allowlist before execution."""

    payload = recipe.model_dump(mode="json")
    for step in payload.get("steps", []):
        params = step.get("params")
        if not isinstance(params, dict):
            continue
        if step.get("type") == "transcribe" and params.get("srt_path"):
            params["srt_path"] = str(resolve_allowed(Path(str(params["srt_path"])), roots))
        if step.get("type") == "shorts.render":
            for key in (
                "overlay_path",
                "music_path",
                "intro_path",
                "outro_path",
                "second_source_path",
            ):
                if params.get(key):
                    params[key] = str(resolve_allowed(Path(str(params[key])), roots))
        if step.get("type") == "broll.plan" and params.get("asset_dir"):
            params["asset_dir"] = str(resolve_allowed(Path(str(params["asset_dir"])), roots))
    return parse_recipe(payload)


def get_recipe(recipe_id: str) -> Recipe:
    if not RECIPE_ID.match(recipe_id):
        raise RecipeError(f"Invalid recipe id: {recipe_id}")
    path = user_recipes_dir() / f"{recipe_id}.json"
    if path.is_file():
        return load_recipe(path)
    if recipe_id in BUILTIN_RECIPES:
        return builtin_recipe(recipe_id)
    raise RecipeError(f"Unknown recipe: {recipe_id}")


def recipe_history_dir(recipe_id: str) -> Path:
    return user_recipes_dir() / "history" / recipe_id


def save_user_recipe(recipe: Recipe) -> Path:
    directory = user_recipes_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{recipe.id}.json"
    if path.is_file():
        history = recipe_history_dir(recipe.id)
        history.mkdir(parents=True, exist_ok=True)
        stamp = time.time_ns()
        shutil.copy2(path, history / f"{stamp}.json")
        entries = sorted(history.glob("*.json"), key=lambda item: item.stem)
        for stale in entries[:-20]:
            stale.unlink(missing_ok=True)
    path.write_text(json.dumps(recipe.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return path


def list_recipe_history(recipe_id: str) -> list[dict[str, object]]:
    directory = recipe_history_dir(recipe_id)
    entries: list[dict[str, object]] = []
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stem, reverse=True):
        try:
            recipe = load_recipe(path)
        except RecipeError:
            continue
        entries.append(
            {
                "version": path.stem,
                "name": recipe.name,
                "description": recipe.description,
                "step_count": len(recipe.steps),
            }
        )
    return entries


def get_recipe_version(recipe_id: str, version: str) -> Recipe:
    if not version.isdigit():
        raise RecipeError(f"Unknown recipe version: {version}")
    path = recipe_history_dir(recipe_id) / f"{version}.json"
    if not path.is_file():
        raise RecipeError(f"Unknown recipe version: {version}")
    return load_recipe(path)


def restore_recipe_version(recipe_id: str, version: str) -> Recipe:
    path = recipe_history_dir(recipe_id) / f"{version}.json"
    if not path.is_file():
        raise RecipeError(f"Unknown recipe version: {version}")
    recipe = load_recipe(path)
    save_user_recipe(recipe)
    return recipe
