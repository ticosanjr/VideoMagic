---
schema_version: 2
version: 1
style_id: sr-depth-3d-viral
name: Shorts Virais — Texto Atrás da Cabeça e Cards 3D
aspect_ratio: '9:16'
target_lufs: -16.5
max_static_sec: 2.5
min_silence_ms: 350
layout_mode: cutout
caption_preset: kinetic_highlight
motion_engine: hyperframes
platforms:
- shorts
- reels
- tiktok
beatmap_defaults:
  hook_depth_sec:
  - 0.0
  - 3.0
  depth_layers:
  - 0
  - 10
  - 20
  caption_block_words:
  - 4
  - 6
sound_design:
  bed: high_retention_pulse
  whoosh_on_cut: true
  impact_on_hook: true
hook_strategy: Primeiros 3 s com tipografia gigante atrás da cabeça e corte seco no
  beat.
intro_strategy: Hook em depth compositing; depois alternar apresentador, tela web
  3D e fotos Ken Burns rápido.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#0A0A0A'
- '#FFFFFF'
- '#00E5FF'
- '#FF3B30'
fonts:
- Arial
cut_rhythm:
  hook_sec: 3.0
  punch_in:
  - 1.0
  - 1.1
  broll_sec: 2.0
safe_zones:
  shorts:
    bottom: 0.16
    right: 0.14
    top: 0.08
  reels:
    bottom: 0.18
    right: 0.14
    top: 0.08
  tiktok:
    bottom: 0.2
    right: 0.16
    top: 0.1
learned_rules:
- id: rule-95aef7b60b62
  text: O recorte do apresentador no hook dura no máximo 3 s; nunca no clipe inteiro.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-06099613f47f
  text: Tipografia do hook fica em z=10 e o recorte em z=20; a legenda em z=40.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-7b83200bc415
  text: Legendas em blocos de 4–6 palavras, sem reflow e sem sair da safe-zone vertical.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-9a7a2d989a6c
  text: Alterne apresentador, web 3D e foto Ken Burns a cada 2–3 s para manter retenção.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-399cbeb4416c
  text: Nunca use mais de um recorte com alfa simultâneo no mesmo frame.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
updated_at: '2026-11-18T16:22:27+00:00'
effect: karaoke_sweep
---

## Objetivo

Shorts/Reels 9:16 de alta retenção, com texto atrás da cabeça no hook, cards 3D
e legendas karaoke estáveis.

## Execução MCP

1. `vf_ingest` + transcrição alinhada + `shorts.select` + `shorts.tighten`.
2. `vf_style_apply(style_id="sr-depth-3d-viral")`.
3. Nos primeiros 3 s:
   - vídeo base em `z=0`;
   - tipografia gigante em `render_motion_graphic(engine="hyperframes",
     transparent=True)` em `z=10`;
   - recorte do apresentador com `remove_background(is_video=True)` apenas no
     intervalo `0–3 s`, em `z=20`.
4. Monte o hook com `vf_timeline(action="apply_beatmap")` e valide a profundidade
   com `vf_overlay_preview`.
5. Ao longo do clipe, alterne:
   - apresentador na base;
   - tela web em perspectiva 3D na metade superior, `z=20`;
   - foto com Ken Burns rápido via `image_to_broll_motion`, `z=10`.
6. Legendas `kinetic_highlight`, `karaoke_sweep`, 4–6 palavras, `z=40`, dentro
   de `safe_zones` shorts/reels/tiktok.
7. Use `vf_shorts_batch` ou `vf_run` com `vf_export`; rode `vf_qa_final` antes de
   publicar.

## Regras Aprendidas

- O recorte do apresentador no hook dura no máximo 3 s; nunca no clipe inteiro.
- Tipografia do hook fica em z=10 e o recorte em z=20; a legenda em z=40.
- Legendas em blocos de 4–6 palavras, sem reflow e sem sair da safe-zone vertical.
- Alterne apresentador, web 3D e foto Ken Burns a cada 2–3 s para manter retenção.
- Nunca use mais de um recorte com alfa simultâneo no mesmo frame.
