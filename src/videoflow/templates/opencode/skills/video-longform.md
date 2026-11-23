---
name: video-longform
description: Edit long-form interviews with VideoFlow MCP tools and a selected style.
---

# Long-form workflow

1. Read the selected `presets/*.md` and confirm it with the user.
2. `vf_project(action="open")` or `init` with `style_id`.
3. `vf_ingest` → `transcribe_word_aligned` → `session.cull`.
4. Build `beat_map.json` from the style and request approval.
5. `vf_timeline(action="apply_beatmap")`, motion, B-roll, captions.
6. `vf_jobs(action="qa")` and fix defects.
7. `vf_export(targets="all")` and report the manifest.
