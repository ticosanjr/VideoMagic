---
schema_version: 2
version: 2
style_id: canal-paula-reels
name: "Canal Paula — Reels & Shorts Retenção (9:16)"
aspect_ratio: "9:16"
target_lufs: -16.0
max_static_sec: 2.5
min_silence_ms: 220
layout_mode: "fullscreen_punchin"
caption_preset: "kinetic_highlight"
motion_engine: "hyperframes"
effect: "karaoke_sweep"
platforms:
  - shorts
  - reels
  - tiktok
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
palette:
  - "#111827"
  - "#F97316"
  - "#FEF3C7"
fonts:
  - "Inter"
cut_rhythm:
  pacing_profile: "tight"
  max_pause_ms: 200
  min_cut_sec: 0.9
  max_cut_sec: 2.8
  punch_in:
    - 1.0
    - 1.08
beatmap_defaults:
  punch_in_scale: 1.07
  broll_motion_scale_max: 1.06
  caption_block_words:
    - 3
    - 4
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  music_arc: "high_retention_pulse"
  ducking: true
  music_gain_db: -20.0
safe_zones:
  shorts:
    bottom: 0.20
    right: 0.15
    top: 0.08
updated_at: "2026-11-25T12:00:00Z"
---

# Direção Editorial — Reels & Shorts

- Corte vertical 9:16 com centralização facial (`crop_x`) e alternância entre `FULL_FACE`, `SPLIT_BROLL` (nunca sobre `PROTECT_FROM_BROLL`) e `SPLIT_SCREEN_SAFE`.
- Hook forte nos primeiros 2 s; opcional `vf_fx_depth` (texto atrás da cabeça) nos 0–3 s.
- Legendas `karaoke_sweep` queimadas no vídeo, 3–4 palavras, máx. 2 linhas, estritamente dentro da safe-zone (`MarginR=160`).
- B-roll de 2–3 s sempre em movimento suave (1.00→1.06) e SFX sutis em trocas de layout.
