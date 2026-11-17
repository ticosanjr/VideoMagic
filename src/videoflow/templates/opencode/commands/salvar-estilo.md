---
description: Clone or create a style and save it into the VideoFlow catalog.
agent: build
---

# /salvar-estilo

Given a name, URL, folder of prints, or manual direction:

1. Extract palette, typography hints, cut rhythm and safe zones.
2. Build the canonical Markdown with YAML frontmatter:
   `style_id`, `name`, `aspect_ratio`, `target_lufs`, `min_silence_ms`,
   `layout_mode`, `caption_preset`, `motion_engine`, `export_targets`,
   `palette`, `fonts`, `cut_rhythm`, `safe_zones`.
3. Call `vf_style(action="save", style_id=..., markdown_content=...,
   workspace_dir="<workspace>")`.
4. Show `./presets/<style_id>.md` and ask for approval.
