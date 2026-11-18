---
schema_version: 2
version: 1
style_id: lf-faceless-news-story
name: Documentário Faceless & Atualidades
aspect_ratio: "16:9"
target_lufs: -16.0
max_static_sec: 4.0
min_silence_ms: 450
layout_mode: "fullscreen_motion"
caption_preset: "kinetic_highlight"
motion_engine: "ffmpeg+hyperframes"
platforms: ['youtube']
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
palette:
  - "#111827"
  - "#f59e0b"
  - "#ef4444"
fonts:
  - "Inter"
beatmap_defaults:
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: "three_act"
  ducking: true
hook_strategy: "Manchete de impacto com evidência visual imediata."
intro_strategy: "Sequência de manchetes e mapas que resume o caso."
updated_at: "2026-11-18T00:00:00Z"
---

# Direção Visual & Editorial

Narração sem apresentador, Ken Burns, enquadramento transformativo, manchetes animadas e trilha de tensão.

## Regras

- Respeitar safe-zones da plataforma.
- Usar apenas assets licenciados.
- Gerar beatmap e pedir aprovação antes de montar.
- Exportar os quatro alvos obrigatórios.
