---
description: Generate and review a beat map for the selected style.
agent: build
---

# /beatmap

1. Read the selected style from `./presets/*.md`.
2. Draft `beat_map.json` with cuts, B-roll, overlays, zoom, SFX and music.
3. Explain the plan and wait for human approval before rendering graphics.
4. Apply it atomically with `vf_timeline(action="apply_beatmap")`.
