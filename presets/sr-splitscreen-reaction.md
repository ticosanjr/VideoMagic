---
schema_version: 2
version: 1
style_id: sr-splitscreen-reaction
name: Split-Screen Reação & Prova
aspect_ratio: '9:16'
target_lufs: -16.5
max_static_sec: 3.0
min_silence_ms: 400
layout_mode: split_screen_50_50
caption_preset: kinetic_highlight
motion_engine: ffmpeg
platforms:
- shorts
- reels
- tiktok
beatmap_defaults:
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: three_act
  ducking: true
hook_strategy: Referência e reação no mesmo frame.
intro_strategy: Topo com a prova; base com o apresentador.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#111827'
- '#f43f5e'
- '#f8fafc'
fonts:
- Inter
cut_rhythm: {}
safe_zones: {}
learned_rules:
- id: rule-af83f9614b10
  text: Respeitar safe-zones da plataforma.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-d96d6e423870
  text: Usar apenas assets licenciados.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-f62f83f55570
  text: Gerar beatmap e pedir aprovação antes de montar.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-88ff74980bfe
  text: Exportar os quatro alvos obrigatórios.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
updated_at: '2026-11-18T00:00:00Z'
---

# Direção Visual & Editorial

Split 50/50, ducking, legenda na divisória e fullscreen nos pontos críticos.

## Regras Aprendidas

- Respeitar safe-zones da plataforma.
- Usar apenas assets licenciados.
- Gerar beatmap e pedir aprovação antes de montar.
- Exportar os quatro alvos obrigatórios.
