---
schema_version: 1
version: 1
style_id: canal-rafael-tech
name: Canal Rafael — Tech Longform
aspect_ratio: '16:9'
target_lufs: -16.5
max_static_sec: 5.0
min_silence_ms: 420
layout_mode: auto
caption_preset: clean_lower_third
motion_engine: hyperframes
platforms: []
beatmap_defaults: {}
sound_design: {}
hook_strategy: ''
intro_strategy: ''
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#0f172a'
- '#38bdf8'
- '#f8fafc'
fonts:
- Inter
cut_rhythm:
  mode: measured
  min_cut_sec: 2.0
  max_cut_sec: 5.0
  median_cut_sec: 3.2
safe_zones:
  youtube:
    bottom: 0.12
    right: 0.08
learned_rules:
- id: rule-320b6d01da86
  text: Destacar o resultado antes da explicação.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-656d739e62be
  text: Evitar zoom agressivo em texto pequeno.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
updated_at: '2026-11-16T21:00:00Z'
---

# Direção Visual & Editorial

- Estética limpa, fundo escuro e acentos azuis.
- Tipografia sans-serif, títulos curtos e legendas discretas.
- Cortes a cada 2–5 segundos, com B-roll técnico e screen capture.
- Motion graphics em HyperFrames com alpha.

## Regras Aprendidas

- Destacar o resultado antes da explicação.
- Evitar zoom agressivo em texto pequeno.
