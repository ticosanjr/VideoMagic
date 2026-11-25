---
schema_version: 2
version: 2
style_id: canal-rafael-tech
name: "Canal Rafael — Tech, Código & Web 3D (16:9)"
aspect_ratio: "16:9"
target_lufs: -16.0
max_static_sec: 6.0
min_silence_ms: 260
layout_mode: "pip_bottom_right"
caption_preset: "word_highlight_blue"
motion_engine: "hyperframes"
effect: "karaoke_sweep"
platforms:
  - youtube
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
palette:
  - "#0F172A"
  - "#38BDF8"
  - "#F8FAFC"
fonts:
  - "Inter"
cut_rhythm:
  pacing_profile: "tight"
  max_pause_ms: 260
  min_cut_sec: 2.0
  max_cut_sec: 6.0
  punch_in:
    - 1.0
    - 1.06
beatmap_defaults:
  punch_in_scale: 1.06
  web_capture_duration_sec: 6.0
  presenter_pip_anchor: "bottom_right"
  presenter_pip_width_ratio: 0.26
  presenter_pip_z: 25
  caption_safe_zone: true
  linked_sfx: true
sound_design:
  bed: "clean_tech_pulse"
  ducking: true
  music_gain_db: -23.0
  whoosh_on_screen_change: true
safe_zones:
  youtube:
    bottom: 0.10
    right: 0.06
updated_at: "2026-11-25T12:00:00Z"
---

# Direção Editorial — Canal Rafael Tech

- Estética escura limpa com acento ciano/azul e resultado mostrado antes da explicação.
- Quando citar sites, repos ou dashboards, usar `vf_fx_capture` (`scroll_animation=True`, 6 s) + `vf_fx_motion` (`transparent=True`, perspectiva 3D suave `rotateY(-8deg)`) com apresentador em PiP arredondado (`bottom_right`, z=25).
- Nunca aplicar zoom agressivo sobre código ou texto pequeno; proteger 100% das cenas `SCREEN_SHARE_*` contra B-roll.
- Legendas discretas com destaque de palavras técnicas (glossário PT-BR + inglês).
