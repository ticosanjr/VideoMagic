---
schema_version: 2
version: 2
style_id: sr-feed-4x5-card
name: "Feed Nativo — X, LinkedIn & Instagram (4:5)"
aspect_ratio: "4:5"
target_lufs: -16.0
max_static_sec: 2.8
min_silence_ms: 240
layout_mode: "headline_card"
caption_preset: "high_contrast_box"
motion_engine: "ffmpeg"
effect: "static"
platforms:
  - x
  - linkedin
  - instagram
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
palette:
  - "#09090B"
  - "#EF4444"
  - "#FFFFFF"
fonts:
  - "Inter"
cut_rhythm:
  pacing_profile: "tight"
  max_pause_ms: 240
  punch_in:
    - 1.0
    - 1.06
beatmap_defaults:
  punch_in_scale: 1.06
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  bed: "clean_tech_pulse"
  ducking: true
  music_gain_db: -22.0
safe_zones:
  feed_4_5:
    bottom: 0.14
    top: 0.12
updated_at: "2026-11-25T12:00:00Z"
---

# Direção Editorial — Feed Nativo 4:5 (1080x1350)

- Proporção exata 4:5 (`1080x1350`) com barra superior de manchete (máx. 8 palavras) legível sem som.
- Legendas de alto contraste (`high_contrast_box`) queimadas no MP4, cortes secos sem pausas longas.
