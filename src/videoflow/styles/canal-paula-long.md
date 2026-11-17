---
schema_version: 1
style_id: canal-paula-long
name: Canal Paula — Longform Entrevistas
aspect_ratio: "16:9"
target_lufs: -16.5
max_static_sec: 6.0
min_silence_ms: 520
layout_mode: "full_screen"
caption_preset: "clean_lower_third"
motion_engine: "ffmpeg"
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
palette:
  - "#111827"
  - "#f59e0b"
  - "#f9fafb"
fonts:
  - "Inter"
cut_rhythm:
  mode: measured
  min_cut_sec: 2.5
  max_cut_sec: 7.0
  median_cut_sec: 4.2
safe_zones:
  youtube:
    bottom: 0.12
    right: 0.08
updated_at: "2026-11-16T21:00:00Z"
---

# Direção Visual & Editorial

- Entrevistas longas com ritmo calmo e respiro entre ideias.
- Legendas baixas, contraste alto e sem excesso de motion.
- B-roll documental apenas quando sustenta a fala.
- Capítulos e marcadores de revisão no timeline.

## Regras Aprendidas

- Preservar pausas dramáticas acima de 300 ms.
- Não cobrir o rosto do entrevistado com lower third.
