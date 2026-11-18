---
schema_version: 2
version: 1
style_id: sr-x-native-video-card
name: Nativo Feed X & Facebook
aspect_ratio: "4:5"
target_lufs: -16.0
max_static_sec: 2.5
min_silence_ms: 300
layout_mode: "headline_card"
caption_preset: "high_contrast_box"
motion_engine: "ffmpeg"
platforms: ['x', 'facebook']
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
palette:
  - "#000000"
  - "#ffffff"
  - "#ef4444"
fonts:
  - "Inter"
beatmap_defaults:
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: "three_act"
  ducking: true
hook_strategy: "Manchete de até 8 palavras."
intro_strategy: "Card de headline sem som."
updated_at: "2026-11-18T00:00:00Z"
---

# Direção Visual & Editorial

Barra superior fixa, legendas de alto contraste, cortes secos e gráficos autoexplicativos.

## Regras

- Respeitar safe-zones da plataforma.
- Usar apenas assets licenciados.
- Gerar beatmap e pedir aprovação antes de montar.
- Exportar os quatro alvos obrigatórios.
