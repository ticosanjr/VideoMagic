---
schema_version: 2
version: 1
style_id: sr-narrative-story-arc
name: Storytelling de Transformação em 5 Atos
aspect_ratio: '9:16'
target_lufs: -16.5
max_static_sec: 3.5
min_silence_ms: 400
layout_mode: fullscreen
caption_preset: kinetic_highlight
motion_engine: ffmpeg
platforms:
- reels
- shorts
beatmap_defaults:
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: three_act
  ducking: true
hook_strategy: Antes/depois em uma frase.
intro_strategy: Hook, conflito e promessa.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#0f172a'
- '#fbbf24'
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

Cinco atos, LUT cinematográfico, grain, música emocional em ducking e UI acima das legendas.

## Regras Aprendidas

- Respeitar safe-zones da plataforma.
- Usar apenas assets licenciados.
- Gerar beatmap e pedir aprovação antes de montar.
- Exportar os quatro alvos obrigatórios.
