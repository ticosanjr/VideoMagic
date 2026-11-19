# Migration to 3.3.0

3.3.0 keeps the 3.2 project schema and adds editorial cleanup, faster delivery,
scoped licensing, and high-level compositors. No project-state migration is
required.

## Editorial cleanup

- `speech.editorial_clean` runs after transcription and before `retakes.cull`.
- It removes immediate word repetitions, phonetic false starts, fuzzy sentence
  retakes, and optional semantic retakes, then snaps cuts to a low-energy
  boundary and applies 15 ms micro-fades.
- `transcript_clean.json` and `editorial_clean.json` record the kept text and
  the cut report; `clipped_words` must stay at zero.

## Delivery

- `vf_export` defaults to `fps=30` for the social MP4. Pass `fps="source"` to
  keep the source cadence. NLE targets stay on the source fps.
- `qa_mode="fast"` (default) checks frames, edge silence, and overlay bounds.
  `qa_mode="full"` dispatches a background QA job. `qa_mode="off"` skips export
  QA. `vf_qa_final` remains complete and short-aware.
- The encoder uses `h264_nvenc` when available and falls back to
  `libx264 -preset veryfast`.
- `max_wer` defaults to `0.12`; `0.06–0.12` is a warning.

## Assets and projects

- The license gate only blocks assets referenced by the timeline, overlays,
  B-roll plan, or audio plan. `vf_assets` lists, approves, and quarantines
  records. `quarantined` is a blocking status.
- Project ids may be slugs. The registry keeps the slug; `ProjectState` stores a
  deterministic UUIDv5. `vf_project_init` can create from `project_id` alone,
  and clone accepts a target id.
- `audio.compose` follows the timeline duration and no longer caps music at
  120 seconds.

## Compositors

New tools:

```text
vf_depth_composite  vf_pip  vf_parallax  vf_style_preview
```

They append normal overlay clips with explicit anchors and `z` values, so MP4
delivery, NLE export, previews, and QA see the same layers. See
[compositors.md](compositors.md).

## Tool count

The core MCP now exposes **37 tools**. No legacy aliases were added.
