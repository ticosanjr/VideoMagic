# Migration to 3.1.0

3.1.0 makes the tools-only MCP surface stateful and adds delivery integrity,
render performance, disk governance, style compilation, and final QA. Recipes
remain UI/CLI/REST-only.

## Project state

- `project_state.json` is schema 3.
- It now contains a `pipeline` block with transcript, selected Shorts, captions,
  analysis spans, artifacts, metadata, `time_map`, and step checkpoints.
- `projects/{project_id}/state.json` mirrors the same document.
- Existing schema 1/2 projects migrate automatically.

## MCP

New core tools:

```text
vf_run             vf_jobs            vf_export          vf_crop_preview
vf_style_validate  vf_style_apply     vf_beatmap_plan    vf_overlay
vf_shorts_batch    vf_qa_final        vf_font
```

The core profile now exposes 28 tools. Recipes and DAG execution are still not
available through MCP.

## Timeline and beatmaps

- `apply_beatmap` accepts `time_basis`, `keep_ranges`, `remove_ranges`,
  `dry_run`, and `force`.
- `cuts` remains a timeline-frame keep-list alias with a deprecation warning.
- Edits that remove more than 50% of the timeline require `force=true`.
- Each mutation creates `history/rev_NNN.json`; use
  `vf_project(action="history"|"undo"|"restore")`.

## Captions

- Default `word_timing` is `word`, with explicit fallback to sentence timing.
- `WrapStyle` is `0`; keyword tags use `{\c&H...&}`. Existing saved styles with
  unknown presets now fail validation instead of silently falling back.
- Intro cards shift burned ASS timestamps by the intro duration.

## Exports

- Every real MP4 passes a 100 ms duration gate. Drifting concat output is
  re-encoded with CFR.
- `vf_export` is the canonical delivery entry point. `export.video`, the bundle,
  and `vf_export` share `master_export`.
- Delivery sidecars use PCM 24-bit.

## Storage

- `VF_CACHE_DIR` (or `paths.cache_dir`) stores analysis, masks, and temporary
  render caches.
- Extracted PCM/proxies are hardlinked into
  `{VF_WORKSPACE_ROOT}/_pool/{sha256}/` with symlink/copy fallbacks.
- `VF_WORKSPACE_ROOT` may point either at the workspace parent or directly at
  its `projects` directory; both resolve without duplication.

## Verification

```bash
uv sync --extra dev --extra vision --extra faster-whisper --extra tray
uv run pytest tests/unit tests/contract
./scripts/gate_local.sh --full
```
