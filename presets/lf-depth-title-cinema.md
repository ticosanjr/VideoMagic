---
schema_version: 2
version: 1
style_id: lf-depth-title-cinema
name: Longform Cinematográfico — Texto Atrás do Apresentador
aspect_ratio: '16:9'
target_lufs: -16.5
max_static_sec: 7.0
min_silence_ms: 600
layout_mode: fullscreen
caption_preset: clean_white
motion_engine: hyperframes
platforms:
- youtube
beatmap_defaults:
  depth_compositing_sec:
  - 2.0
  - 4.0
  punch_in_scale: 1.08
  lower_third_anchor: bottom_left
sound_design:
  bed: cinematic_three_act
  risers: true
  impact_on_chapter: true
hook_strategy: Abrir com uma pergunta visual e um título gigante atrás da silhueta
  nos primeiros 2–4 s.
intro_strategy: Título/card gráfico atrás do apresentador recortado; retorno a cortes
  limpos com punch-in suave.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#080B10'
- '#F5F0E6'
- '#D4A24C'
- '#8B5E34'
fonts:
- Arial
cut_rhythm:
  hook_cut_sec: 2.2
  chapter_cut_sec: 6.0
  punch_in:
  - 1.0
  - 1.08
safe_zones:
  youtube_16_9:
    bottom: 0.1
    top: 0.06
learned_rules:
- id: rule-d8ae500b2cdb
  text: Nunca rode `remove_background(is_video=True)` no vídeo inteiro; recorte só
    o sub-trecho de 2–4 s.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-f4356f174418
  text: 'Texto atrás do apresentador exige três camadas: base em z=0, gráfico em z=10
    e recorte em z=20.'
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-20fabf910c69
  text: Punch-in cinematográfico fica entre 100% e 108%, com retorno suave.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-abb265aca0b9
  text: Lower third sempre ancorado em bottom_left com margem de 64 px.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-6aea0ee01ddd
  text: Não use mais de um efeito de profundidade no mesmo plano; preserve o ritmo
    dos cortes limpos.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
updated_at: '2026-11-18T16:22:27+00:00'
effect: static
---

## Objetivo

Longform cinematográfico 16:9 com títulos e cards gráficos atrás da silhueta
do apresentador, cortes limpos e punch-ins suaves.

## Execução MCP

1. `vf_ingest` com CFR e `transcribe_word_aligned`; rode `transcript.dedupe` e
   `retakes.cull`.
2. `vf_style_apply(style_id="lf-depth-title-cinema")` para compilar parâmetros,
   beatmap draft e diff.
3. Nos ganchos, introduções e aberturas de capítulo, renderize o texto/card com
   `render_motion_graphic(engine="hyperframes", transparent=True)` em 1920x1080.
4. Aplique `remove_background(is_video=True)` **somente** no intervalo de
   `2.0s` a `4.0s` do plano em que o efeito acontece. Nunca no vídeo inteiro.
5. Monte em `vf_timeline(action="apply_beatmap")` com as três camadas:
   - `z=0`: vídeo base completo;
   - `z=10`: gráfico/texto transparente;
   - `z=20`: clipe recortado com alfa, alinhado ao mesmo timestamp da base.
6. Para o recorte, use `vf_overlay` com `anchor="center"` ou `"top_center"`,
   `width_ratio=1.0` e `z=20`; valide com `vf_overlay_preview`.
7. Lower thirds: `anchor="bottom_left"`, `margin_x=64`, `margin_y=64`, `z=20`.
8. Punch-ins: `scale` de `1.00` para `1.08` em 8–12 frames; nunca acima de
   `1.10` em rostos.
9. Rode `vf_layout`, `vf_qa_autofix` e `vf_qa_final` antes de `vf_export`.

## Regras Aprendidas

- Nunca rode `remove_background(is_video=True)` no vídeo inteiro; recorte só o sub-trecho de 2–4 s.
- Texto atrás do apresentador exige três camadas: base em z=0, gráfico em z=10 e recorte em z=20.
- Punch-in cinematográfico fica entre 100% e 108%, com retorno suave.
- Lower third sempre ancorado em bottom_left com margem de 64 px.
- Não use mais de um efeito de profundidade no mesmo plano; preserve o ritmo dos cortes limpos.
