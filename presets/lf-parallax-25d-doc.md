---
schema_version: 2
version: 1
style_id: lf-parallax-25d-doc
name: Documentário — Ken Burns e Parallax 2.5D
aspect_ratio: '16:9'
target_lufs: -16.5
max_static_sec: 5.0
min_silence_ms: 500
layout_mode: fullscreen
caption_preset: minimalist_box
motion_engine: hyperframes
platforms:
- youtube
beatmap_defaults:
  ken_burns_motions:
  - zoom_in
  - zoom_out
  - pan_left
  - pan_right
  parallax_rotate:
  - -3
  - 3
sound_design:
  bed: three_act_documentary
  paper_sfx: true
  risers: true
hook_strategy: Abrir com uma foto-chave em 2.5D e uma pergunta narrativa; nunca com
  imagem parada.
intro_strategy: Movimento imediato em todas as imagens; planos de fundo e sujeito
  com velocidades distintas.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#101010'
- '#E8E1D5'
- '#B08D57'
- '#6B7A8F'
fonts:
- Arial
cut_rhythm:
  broll_sec: 4.5
  key_photo_sec: 6.0
safe_zones:
  youtube_16_9:
    bottom: 0.1
    top: 0.06
learned_rules:
- id: rule-2c35a4b96231
  text: Nunca insira JPG/PNG estático como B-roll de tela cheia; use image_to_broll_motion.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-7e4d1faad6f4
  text: Alterne a direção do Ken Burns entre cortes consecutivos.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-af4f9875995e
  text: Fotos 2.5D exigem sujeito e fundo em planos separados com escalas diferentes.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-887cf65f57dc
  text: A inclinação de câmera fica entre -3deg e +3deg; acima disso o texto fica
    ilegível.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-327e21ec875d
  text: SFX de papel e riser entram somente em viradas narrativas, nunca em toda frase.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
updated_at: '2026-11-18T16:22:27+00:00'
effect: static
---

## Objetivo

Documentário/storytelling 16:9 sem imagens estáticas, com Ken Burns, pan e
parallax 2.5D em fotos-chave.

## Execução MCP

1. `vf_ingest` + transcrição + `retakes.cull`.
2. `vf_style_apply(style_id="lf-parallax-25d-doc")`.
3. Toda imagem de cobertura passa por
   `image_to_broll_motion(image_path=..., duration_sec=..., motion=...)`,
   alternando `zoom_in`, `zoom_out`, `pan_left` e `pan_right` entre cortes.
4. Fotos-chave de personagens, provas ou documentos:
   - `remove_background(is_video=False)` para gerar o PNG do sujeito;
   - `render_motion_graphic(engine="hyperframes")` com duas camadas:
     fundo `scale 1.00 → 1.04` com blur leve;
     sujeito `scale 1.00 → 1.12` com deslocamento lateral oposto;
   - `rotateY` entre `-3deg` e `+3deg`.
5. Insira as cenas com `vf_overlay(anchor="center", width_ratio=1.0, z=10)`.
6. Áudio em três atos, SFX de papel e risers nos pontos de virada.
7. Legendas `minimalist_box`, `effect="static"`, `z=40`.
8. Rode `vf_overlay_preview`, `vf_layout`, `vf_qa_final` e exporte.

## Regras Aprendidas

- Nunca insira JPG/PNG estático como B-roll de tela cheia; use image_to_broll_motion.
- Alterne a direção do Ken Burns entre cortes consecutivos.
- Fotos 2.5D exigem sujeito e fundo em planos separados com escalas diferentes.
- A inclinação de câmera fica entre -3deg e +3deg; acima disso o texto fica ilegível.
- SFX de papel e riser entram somente em viradas narrativas, nunca em toda frase.
