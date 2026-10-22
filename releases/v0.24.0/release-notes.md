# VideoFlow 0.24.0

This release gives the recipe engine its missing pieces: independent Shorts
reframe/captions steps, reusable analysis cache, and a much wider recipe editor.

## Recipe editor

- The Recipes tab now uses the full content width. The legacy New project card
  and run-summary sidebar are hidden while Recipes is active.
- The step inspector is a collapsible right-side overlay that opens when a node
  is clicked.
- **+ Add step** is a filterable popover; adding a step opens its inspector.
- **Config** opens a modal for recipe identity and the LLM router.
- **JSON** opens a large modal with the full recipe. A selected node's
  **Expand** button opens the same style of modal for its parameters.
- The canvas height scales with the viewport, and the page max width expands to
  1800px on the Recipes tab.

## Independent Shorts steps

The Shorts path is now four explicit nodes:

1. `shorts.select` — score and choose clips.
2. `shorts.reframe` — static center crop, motion tracking, or face tracking.
3. `shorts.captions` — generate ASS/karaoke files without rendering video.
4. `shorts.render` — render MP4 using the prepared caption files.

`shorts.render` still falls back to inline caption generation for older recipes.
`shorts.select` no longer tracks faces; a non-center `reframe_mode` there emits
a warning and leaves tracking to `shorts.reframe`.

## Analysis cache

`audio.vad` and local/HTTP `transcribe` results are cached by source PCM digest
plus step parameters:

```text
<videoflow-home>/cache/recipe-v1/
```

The cache is shared across output directories. The report exposes
`cache_hits` and `cache_misses`, and the recipe job panel shows hits.

```bash
videoflow recipe cache path
videoflow recipe cache clear
```

Set `VIDEOWFLOW_RECIPE_CACHE=0` to disable caching.

## Validation

- 395 Python tests passed; 14 UI tests passed; enforced coverage 98.72%.
- The AppImage was started without a terminal and served the new Recipes UI.
- A real Shorts recipe ran to `succeeded` and wrote both the `.ass` caption file
  and the MP4.
- A second run to a different output directory reused the VAD cache.
- Opening the AppImage again reused the running service.
- Playwright checks opened the step inspector and the JSON/settings modals.

## Artifacts

- `videoflow-0.24.0-linux-x86_64` — SHA-256 `89462a7cbb8a2526f21a76a8259c56c2695a2b83be8bcfafa743f206296ed823`
- `VideoFlow-0.24.0-x86_64.AppImage` — SHA-256 `0f3d0916e3813c690d4ea3f6583a4067560bc9f41f9577cb2d1cfb8f298b47cc`

The build is lean; speech weights are downloaded from the Models tab. Windows
PE is not included because no Windows/Wine build host was available.
