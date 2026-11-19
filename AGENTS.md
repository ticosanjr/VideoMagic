# VideoFlow × OpenCode

Este workspace foi preparado pelo VideoFlow 3.7.0.

## Protocolo obrigatório

1. Liste `./presets/*.md` e `./.opencode/workflows/*.md`, chame
   `vf_style(action="list")` e pergunte ao usuário qual estilo e workflow usar
   antes de decupar, gerar beatmap ou renderizar.
2. Nunca escreva scripts FFmpeg manuais. Use as tools MCP atômicas do
   VideoFlow para ingest, transcrição, timeline, motion, captura, QA e export.
3. Estilos novos ou alterados devem ser salvos com
   `vf_style(action="save", workspace_dir="<workspace>")`, sincronizando `./presets/`.
4. Exporte com `vf_export` e rode `vf_qa_final` antes de considerar a entrega
   aprovada. `needs_review` não é sucesso.
5. Não grave tokens ou API keys no workspace; use variáveis de ambiente.
6. Quando um step exigir LLM, isso deve ser explícito: use
   `decupage.llm` com `llm_policy="caller"` para receber o request e decidir
   como a LLM chamadora, ou `llm_policy="videoflow"` para delegar ao provider
   configurado. `none` é sempre registrado como degradado. Nunca envie
   timestamps para a LLM; use `asu_id` e índices de palavras.
7. **Entrega em uma pasta só (conveniência, não requisito):** ao concluir,
   quando o usuário não indicar outro destino, rode
   `vf_exec(action="step", step_id="delivery.collect",
   params={"mode":"copy"})` para consolidar vídeos e exports em
   `./VideoFlow_Output/{videos,exports,shorts,scenes}` na raiz do workspace.
   O MCP é flexível por contrato: aceita qualquer caminho de saída e nunca deve
   bloquear, falhar ou limitar um projeto porque os arquivos estão em outra
   pasta. Se a única cópia de uma entrega estiver em `work/`, apenas avise.
8. **Offload de processamento pesado:** ASR, alinhamento, matte, render NVENC,
   scene analysis e Short render devem usar `compute_policy="auto"` ou
   `"remote"` quando o worker Windows estiver configurado. Não force execução
   local sem motivo; se o worker cair, aceite fallback somente com
   `degraded=true` explícito e reporte o motivo.

## Receitas Técnicas de Efeitos Visuais Avançados

Estas regras são obrigatórias para qualquer edição futura.

### 1. Texto ou gráficos atrás do apresentador (Depth Compositing Seletivo)

- **NUNCA** rode `remove_background(is_video=True)` no vídeo inteiro; isso
  esgota CPU/VRAM.
- Prefira `vf_depth_composite(project_id, text_or_asset, start_sec, end_sec)`:
  ele recorta só o intervalo, aplica rembg no sub-trecho e cria as camadas
  `z=10` (gráfico) e `z=20` (apresentador com alfa).
- Se precisar montar manualmente, recorte apenas o sub-trecho exato de `2s a 4s`
  onde o efeito ocorre. No hook vertical, o limite é `0s a 3s`.
- Empilhe na timeline via `vf_timeline(action="apply_beatmap")`:
  - Camada 1 (`z=0`): vídeo original completo;
  - Camada 2 (`z=10`): texto/gráfico com
    `render_motion_graphic(engine="hyperframes", transparent=True)`;
  - Camada 3 (`z=20`): clipe recortado com canal alfa, alinhado ao mesmo
    timestamp da camada base.
- Valide o alinhamento e as caixas com `vf_overlay_preview` e `vf_layout`.
- Lower thirds usam `anchor="bottom_left"`, `margin_x=64`, `margin_y=64`,
  `z=20`.
- Punch-ins: `1.00 → 1.08`, retornando suavemente; nunca acima de `1.10` em
  rostos.

### 2. Página web com scroll suave, fundo e perspectiva 3D

- **Passo A:** `capture_web_or_screen(url=..., mode="video_clip",
  scroll_animation=True, duration_sec=6)` gera o MP4 plano da navegação.
- **Passo B:** `render_motion_graphic(engine="hyperframes",
  transparent=True)` cria o micro-projeto HTML/CSS/GSAP com:
  - `border-radius: 16px`;
  - `box-shadow` amplo;
  - fundo ambientado/desfocado;
  - `transform: perspective(1200px) rotateY(-10deg) rotateX(4deg)`;
  - flutuação contínua e sombra projetada.
- **Passo C:** insira com `vf_overlay` usando `anchor="center"` ou
  `"top_center"`, `width_ratio=0.72`, `z=20`.
- Apresentador em PiP: prefira `vf_pip(project_id, overlay_asset, start_sec,
  end_sec, anchor="bottom_right", width_ratio=0.28)`; ele usa máscara PNG em
  cache e `z=25`. Alternativa manual: `layout_mode="rounded_window"`.

### 3. Zoom in/out e pan left/right em imagens (Ken Burns)

- Nunca insira `.jpg`/`.png` estáticos direto como B-roll de tela cheia.
- Passe toda imagem por `image_to_broll_motion(image_path=...,
  duration_sec=..., motion="zoom_in" | "zoom_out" | "pan_left" | "pan_right")`.
- Alterne a direção entre cortes consecutivos.
- Em documentário, use `max_static_sec=5.0`; em Shorts, no máximo `2.5`.

### 4. Perspectiva 3D e parallax 2.5D em imagens

- **Cards/documentos flutuantes:** renderize a imagem num plano CSS 3D em
  `render_motion_graphic(engine="hyperframes")` com `rotateY` de `-4deg` a
  `+4deg` e `scale` de `1.0` a `1.06`.
- **Fotos com separação de profundidade (2.5D real):** prefira
  `vf_parallax(project_id, image_path, start_sec, end_sec)`:
  - `remove_background(is_video=False)` gera o PNG recortado;
  - o compositor anima duas camadas sobrepostas no `hyperframes`;
  - fundo: `scale 1.0 → 1.04`, blur leve;
  - sujeito: `scale 1.0 → 1.12`, deslocamento lateral oposto;
  - inclinação de câmera entre `-3deg` e `+3deg`.
- Legendas sempre em `z=40`, blocos de 4–6 palavras, `WrapStyle: 0`, dentro das
  safe-zones verticais.

### 5. Ordem operacional recomendada

1. `vf_ingest` + `transcribe_word_aligned` + `speech.editorial_clean` +
   `retakes.cull`.
2. `vf_style_apply(style_id=...)`; valide com `vf_style_preview`.
3. `vf_beatmap_plan` / `vf_depth_composite` / `vf_pip` / `vf_parallax` /
   `render_motion_graphic` / `capture_web_or_screen` / `image_to_broll_motion`.
4. `vf_timeline(action="apply_beatmap")` e `vf_overlay` com âncoras/z.
5. `vf_overlay_preview`, `vf_caption_preview`, `vf_layout`, `vf_qa_autofix`.
6. `vf_export` + `vf_qa_final`; só publique se o status for `succeeded`.

## Estilos disponíveis no catálogo

- `lf-depth-title-cinema` — longform cinematográfico com texto atrás do
  apresentador.
- `lf-3d-web-showcase` — longform tech/SaaS com web em perspectiva 3D.
- `lf-parallax-25d-doc` — documentário com Ken Burns e parallax 2.5D.
- `sr-depth-3d-viral` — Shorts virais com texto atrás da cabeça e cards 3D.
