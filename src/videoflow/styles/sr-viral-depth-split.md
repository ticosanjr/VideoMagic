---
schema_version: 2
version: 2
style_id: sr-viral-depth-split
name: "Shorts Viral — Depth 3D, Split-Screen & Cutout (9:16)"
aspect_ratio: "9:16"
target_lufs: -16.0
max_static_sec: 2.2
min_silence_ms: 200
layout_mode: "cutout"
caption_preset: "word_highlight_blue"
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
  - "#0A0A0A"
  - "#00E5FF"
  - "#FFFFFF"
fonts:
  - "Inter"
cut_rhythm:
  pacing_profile: "tight"
  max_pause_ms: 180
  hook_sec: 3.0
  punch_in:
    - 1.0
    - 1.08
beatmap_defaults:
  hook_depth_sec:
    - 0.0
    - 3.0
  punch_in_scale: 1.08
  caption_block_words:
    - 3
    - 4
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  bed: "high_retention_pulse"
  ducking: true
  music_gain_db: -20.0
  impact_on_hook: true
safe_zones:
  shorts:
    bottom: 0.20
    right: 0.15
    top: 0.08
updated_at: "2026-11-25T12:00:00Z"
---

# Direção Editorial — Shorts Viral Depth & Split

- 0–3 s: `vf_fx_depth` com tipografia gigante atrás da cabeça + SFX de impacto.
- Ao longo do Short (25–45 s): alternar `FULL_FACE`, `SPLIT_BROLL` (imagens em Ken Burns 1.00→1.06 ou web 3D) e `SPLIT_SCREEN_SAFE` para cenas de tela.
- Legendas `karaoke_sweep` queimadas no vídeo, 3–4 palavras, máx. 2 linhas, dentro da safe-zone.
