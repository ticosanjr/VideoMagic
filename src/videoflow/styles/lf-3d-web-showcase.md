---
schema_version: 2
version: 1
style_id: lf-3d-web-showcase
name: Longform Tech/SaaS — Web em Perspectiva 3D
aspect_ratio: '16:9'
target_lufs: -16.5
max_static_sec: 8.0
min_silence_ms: 550
layout_mode: pip_bottom_right
caption_preset: word_highlight_blue
motion_engine: hyperframes
platforms:
- youtube
beatmap_defaults:
  web_capture_duration_sec: 6.0
  presenter_pip_anchor: bottom_right
  presenter_pip_z: 25
sound_design:
  bed: clean_tech_pulse
  whoosh_on_screen_change: true
hook_strategy: Abrir com o dashboard em perspectiva 3D e o apresentador em PiP arredondado.
intro_strategy: Captura web em movimento suave dentro de moldura liquid glass; apresentador
  em PiP no canto inferior direito.
export_targets:
- mp4_youtube
- resolve
- premiere
- kdenlive
palette:
- '#07111F'
- '#2F80ED'
- '#56CCF2'
- '#FFFFFF'
fonts:
- Arial
cut_rhythm:
  screen_demo_sec: 6.0
  pip_cut_sec: 8.0
safe_zones:
  youtube_16_9:
    bottom: 0.1
    right: 0.06
learned_rules:
- id: rule-e3334070e0a0
  text: Captura web sempre em `video_clip` com `scroll_animation=True`; nunca use
    screenshot estático para demo.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-fc7157954bbe
  text: A cena 3D precisa de `transparent=True` e fundo próprio; não achate o vídeo
    no fundo do projeto.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-71ed06828354
  text: PiP do apresentador fica em bottom_right, z=25, com máscara arredondada cacheada.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-cc3e49cd4e87
  text: Legendas karaoke_sweep ficam em z=40 e nunca entram na borda inferior.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
- id: rule-e25dfe7dac8e
  text: Mantenha a perspectiva entre rotateY(-10deg) e rotateY(-6deg) para leitura.
  scope: learned
  weight: 1.0
  source: style_markdown
  created_at: ''
updated_at: '2026-11-18T16:22:27+00:00'
effect: karaoke_sweep
---

## Objetivo

Longform tech/SaaS 16:9 com gravações web em perspectiva 3D, moldura liquid
glass e apresentador em PiP arredondado.

## Execução MCP

1. `vf_ingest` + transcrição alinhada + `retakes.cull`.
2. `vf_style_apply(style_id="lf-3d-web-showcase")`.
3. Para cada site, ferramenta, dashboard ou artigo citado:
   `capture_web_or_screen(url=..., mode="video_clip", scroll_animation=True,
   duration_sec=6)`.
4. Gere a cena 3D em `render_motion_graphic(engine="hyperframes",
   transparent=True)` com:
   - container `border-radius: 16px`;
   - `box-shadow` amplo;
   - fundo texturizado/desfocado;
   - `transform: perspective(1200px) rotateY(-10deg) rotateX(4deg)`;
   - flutuação contínua e sombra projetada.
5. Insira com `vf_overlay(anchor="center" ou "top_center", width_ratio=0.72,
   z=20)`.
6. Apresentador em PiP: `layout_mode="rounded_window"`, máscara PNG em cache,
   `anchor="bottom_right"`, `margin_x=32`, `margin_y=32`, `width_ratio=0.28`,
   `z=25`.
7. Legendas: `word_highlight_blue`, `effect="karaoke_sweep"`, blocos de 4–6
   palavras, `z=40`, dentro da safe-zone.
8. Valide com `vf_overlay_preview`, `vf_layout`, `vf_qa_final` e exporte com
   `vf_export(targets=["mp4_youtube", "resolve", "premiere", "kdenlive"])`.

## Regras Aprendidas

- Captura web sempre em `video_clip` com `scroll_animation=True`; nunca use screenshot estático para demo.
- A cena 3D precisa de `transparent=True` e fundo próprio; não achate o vídeo no fundo do projeto.
- PiP do apresentador fica em bottom_right, z=25, com máscara arredondada cacheada.
- Legendas karaoke_sweep ficam em z=40 e nunca entram na borda inferior.
- Mantenha a perspectiva entre rotateY(-10deg) e rotateY(-6deg) para leitura.
