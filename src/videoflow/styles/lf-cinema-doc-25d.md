---
schema_version: 2
version: 2
style_id: lf-cinema-doc-25d
name: "Documentário Cinema — Depth Title & Parallax 2.5D (16:9)"
aspect_ratio: "16:9"
target_lufs: -16.0
max_static_sec: 5.0
min_silence_ms: 320
layout_mode: "fullscreen"
caption_preset: "minimalist_box"
motion_engine: "hyperframes"
effect: "static"
platforms:
  - youtube
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
palette:
  - "#080B10"
  - "#D4A24C"
  - "#F5F0E6"
fonts:
  - "Inter"
cut_rhythm:
  pacing_profile: "balanced"
  max_pause_ms: 350
  broll_sec: 4.5
  punch_in:
    - 1.0
    - 1.07
beatmap_defaults:
  depth_compositing_sec:
    - 0.0
    - 3.0
  punch_in_scale: 1.07
  broll_motion_scale_max: 1.06
  parallax_rotate:
    - -3
    - 3
  lower_third_anchor: "bottom_left"
sound_design:
  music_arc: "three_act"
  ducking: true
  music_gain_db: -21.0
  risers: true
safe_zones:
  youtube:
    bottom: 0.10
    top: 0.06
updated_at: "2026-11-25T12:00:00Z"
---

# Direção Editorial — Documentário Cinema & 2.5D

- Abertura cinematográfica (0–3 s): título atrás do apresentador via `vf_fx_depth` (somente 2–3 s, nunca no vídeo inteiro).
- Fotos-chave de personagens, provas ou mapas usam `vf_fx_parallax` (camadas separadas, `rotateY` entre -3deg e +3deg); demais imagens usam `image_to_broll_motion` alternando `zoom_in`, `zoom_out`, `pan_left`, `pan_right` (escala 1.00→1.06).
- Trilha em 3 atos com risers e SFX de papel apenas em viradas narrativas.
