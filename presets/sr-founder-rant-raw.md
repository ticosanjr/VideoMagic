---
schema_version: 2
version: 1
style_id: sr-founder-rant-raw
name: Opinião Direta & Punch-In
aspect_ratio: '9:16'
target_lufs: -16.5
max_static_sec: 2.0
min_silence_ms: 300
layout_mode: fullscreen_punchin
caption_preset: karaoke_emoji
motion_engine: ffmpeg
platforms:
- reels
- shorts
- x
beatmap_defaults:
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: three_act
  ducking: true
hook_strategy: Afirmação polêmica em 2 s.
intro_strategy: Câmera direta, sem rodeios.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#111827'
- '#facc15'
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

Cortes agressivos, punch-in 100↔114%, karaoke com emojis e bass drop/whoosh.

## Regras Aprendidas

- Respeitar safe-zones da plataforma.
- Usar apenas assets licenciados.
- Gerar beatmap e pedir aprovação antes de montar.
- Exportar os quatro alvos obrigatórios.
