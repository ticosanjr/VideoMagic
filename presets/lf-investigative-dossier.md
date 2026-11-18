---
schema_version: 2
version: 1
style_id: lf-investigative-dossier
name: Dossiê Investigativo & Iceberg
aspect_ratio: '16:9'
target_lufs: -16.5
max_static_sec: 8.0
min_silence_ms: 600
layout_mode: fullscreen
caption_preset: kinetic_highlight
motion_engine: hyperframes
platforms:
- youtube
beatmap_defaults:
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: three_act
  ducking: true
hook_strategy: Pergunta investigativa com uma prova visual incompleta.
intro_strategy: Intro de alta densidade montada por último.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#f8f5ec'
- '#111827'
- '#b91c1c'
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

Dossiê com textura de papel, recortes de imprensa, prancha de entidades, SFX orgânicos e revelação progressiva.

## Regras Aprendidas

- Respeitar safe-zones da plataforma.
- Usar apenas assets licenciados.
- Gerar beatmap e pedir aprovação antes de montar.
- Exportar os quatro alvos obrigatórios.
