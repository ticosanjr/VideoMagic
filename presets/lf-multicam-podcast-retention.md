---
schema_version: 2
version: 1
style_id: lf-multicam-podcast-retention
name: Podcast Multicam de Alta Retenção
aspect_ratio: '16:9'
target_lufs: -16.5
max_static_sec: 12.0
min_silence_ms: 750
layout_mode: multicam_auto
caption_preset: kinetic_highlight
motion_engine: ffmpeg
platforms:
- youtube
beatmap_defaults:
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: three_act
  ducking: true
hook_strategy: Trailer hook de 15–20 s com o momento de maior tensão.
intro_strategy: Abertura com o hook e apresentação dos participantes.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#111827'
- '#22c55e'
- '#f9fafb'
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

Sincronia por waveform, active speaker, reação, B-roll contextual e capítulos.

## Regras Aprendidas

- Respeitar safe-zones da plataforma.
- Usar apenas assets licenciados.
- Gerar beatmap e pedir aprovação antes de montar.
- Exportar os quatro alvos obrigatórios.
