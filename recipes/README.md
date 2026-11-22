# Recipes

A recipe is a versioned DAG of pipeline steps. The backend validates duplicate
ids, unknown dependencies, unknown step types, and cycles before running.

Built-in recipes are mirrored here for reading and editing. These JSON files
are examples that mirror the Python definitions; they are not a second runtime
catalog and are not loaded automatically:

- `youtube_talking_head.json` — main cut and NLE exports.
- `viral_shorts_batch.json` — main cut plus three vertical Shorts.
- `full_podcast_curation.json` — main cut plus five Shorts with audio/scene boosts.
- `localized_shorts.json` — Viral Shorts plus an optional translated dub per Short.
- `opusclip_auto_shorts.json` — OpusClip-style cleanup, curation, reframe, kinetic captions, render, and NLE export.
- `opusclip_auto_broll.json` — Viral Shorts with synthetic or local B-roll planning.
- `opusclip_nle_bridge.json` — Long-form timeline, chapters, NLE exports, QA, Shorts metadata, and delivery package.

Run one with:

```bash
videoflow recipe validate recipes/youtube_talking_head.json
videoflow recipe run recipes/youtube_talking_head.json /media/source.mp4 -o /media/out
```

The same JSON is accepted by `POST /api/v1/recipes/run` and by the
`videoflow_run_recipe_inline` MCP tool.

Secrets are referenced by environment variable name (`api_key_env`); never put
an API key in a recipe.
