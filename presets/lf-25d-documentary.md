---
schema_version: 2
version: 1
style_id: lf-25d-documentary
name: Documentário 2.5D Câmera Contínua
aspect_ratio: '16:9'
target_lufs: -16.5
max_static_sec: 6.0
min_silence_ms: 650
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
hook_strategy: Mapa ou documento que abre uma pergunta histórica.
intro_strategy: Cena contínua que estabelece o mundo antes da tese.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#e7e2d8'
- '#1f2937'
- '#c084fc'
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

Câmera virtual 2.5D, mapas animados, documentos históricos com profundidade e som atmosférico.

## Regras Aprendidas

- Respeitar safe-zones da plataforma.
- Usar apenas assets licenciados.
- Gerar beatmap e pedir aprovação antes de montar.
- Exportar os quatro alvos obrigatórios.
