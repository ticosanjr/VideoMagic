"""Base built-in recipes."""

from __future__ import annotations

from videoflow.engine.recipes.catalog import (
    _EXPORT,
    _EXPORT_WITH_SHORTS,
    _INGEST,
    _RETAKES,
    _TIMELINE,
    _TIMELINE_NO_RETAKES,
    _TRANSCRIBE,
    _TRANSLATE,
    _VAD,
    BUILTIN_RECIPES,
    _add_recipe,
    _shorts,
)

BUILTIN_RECIPES.update({
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
})

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
    _TRANSLATE,
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
