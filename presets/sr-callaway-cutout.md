---
schema_version: 2
version: 1
style_id: sr-callaway-cutout
name: Cutout Superior 3D
aspect_ratio: '9:16'
target_lufs: -16.5
max_static_sec: 2.5
min_silence_ms: 350
layout_mode: cutout
caption_preset: kinetic_highlight
motion_engine: hyperframes
platforms:
- reels
- tiktok
- shorts
beatmap_defaults:
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: three_act
  ducking: true
hook_strategy: Objeto 3D entra antes da fala.
intro_strategy: Pessoa recortada na base e visual no topo.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#f97316'
- '#111827'
- '#fef3c7'
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

Cutout com cabeça ultrapassando a borda, 3D/papel, B-roll no topo, fullscreen nos picos e safe-zones.

## Regras Aprendidas

- Respeitar safe-zones da plataforma.
- Usar apenas assets licenciados.
- Gerar beatmap e pedir aprovação antes de montar.
- Exportar os quatro alvos obrigatórios.
