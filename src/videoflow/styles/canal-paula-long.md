---
schema_version: 2
version: 2
style_id: canal-paula-long
name: "Canal Paula — YouTube Longform (16:9)"
aspect_ratio: "16:9"
target_lufs: -16.0
max_static_sec: 5.0
min_silence_ms: 280
layout_mode: "fullscreen"
caption_preset: "clean_lower_third"
motion_engine: "hyperframes"
platforms:
  - youtube
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
palette:
  - "#111827"
  - "#F59E0B"
  - "#F9FAFB"
fonts:
  - "Inter"
cut_rhythm:
  pacing_profile: "tight"
  max_pause_ms: 280
  min_cut_sec: 2.0
  max_cut_sec: 5.5
  punch_in:
    - 1.0
    - 1.06
beatmap_defaults:
  punch_in_scale: 1.06
  broll_motion_scale_max: 1.06
  lower_third_anchor: "bottom_left"
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: "three_act"
  ducking: true
  music_gain_db: -22.0
safe_zones:
  youtube:
    bottom: 0.10
    right: 0.06
updated_at: "2026-11-25T12:00:00Z"
---

# Direção Editorial — Canal Paula Longform

- Ritmo limpo e dinâmico: eliminar retakes, gagueiras e pausas mortas >280 ms preservando sílabas.
- Punch-in suave apenas entre 1.00 e 1.06 (nunca >1.08 em rostos).
- B-roll e imagens entram somente em trechos `TALKING_HEAD` alinhados à frase falada; toda imagem usa `image_to_broll_motion` com zoom sutil (1.00→1.06), nunca imagem parada.
- Legendas discretas na base (z=40), lower thirds em `bottom_left` sem cobrir o rosto.
- Trilha suave em ducking (-22 dB) com SFX pontuais apenas em viradas de assunto.
