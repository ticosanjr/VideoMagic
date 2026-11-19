<!-- videoflow:opencode:start -->
# VideoFlow × OpenCode

Este workspace foi preparado pelo VideoFlow {{VERSION}}.

## Protocolo obrigatório

1. **Escolha obrigatória de estilo e workflow**: antes de decupar, gerar
   beatmap, renderizar gráficos ou alterar qualquer vídeo, liste
   `./presets/*.md` e `./.opencode/workflows/*.md`, chame
   `vf_style(action="list")` e **pergunte explicitamente ao usuário**, em lista
   numerada, qual Estilo e qual Workflow devem ser usados.
2. **Não comece sem as duas respostas.** Se o usuário quiser um novo estilo,
   clone/extraia a referência e salve com
   `vf_style(action="save", workspace_dir="{{TARGET_DIR}}")`.
3. **Nunca escreva scripts FFmpeg manuais no bash.** Use as tools MCP do
   VideoFlow para ingest, transcrição, beatmap, motion, captura, QA e export.
4. **Fluxo determinístico em 5 etapas**:
   1. `vf_ingest` (CFR + multi-take/multicam) + `transcribe_word_aligned` +
      `speech.editorial_clean` + `session.cull`.
   2. Gerar `beat_map.json` a partir do `.md` do estilo escolhido e **aguardar
      aprovação humana** antes de renderizar gráficos.
   3. Montagem atômica com `vf_timeline(action="apply_beatmap")`,
      `render_motion_graphic` (`draft_scale=0.5`) e `capture_web_or_screen`
      ou `mcp-vf-media-fetch`.
   4. Auditoria visual obrigatória com `vf_job(action="qa")` e correção
      antes de mostrar o rascunho.
   5. Exportar com `vf_export(targets="all")` para
      YouTube MP4, Resolve `.fcpxml`, Premiere `.xml` e Kdenlive MLT; registrar
      feedback com `vf_style(action="learn_rule")`.
5. **Persistência de estilo**: qualquer estilo novo ou clonado deve ser salvo no
   catálogo e sincronizado em `./presets/<style_id>.md`.
6. **Segurança**: não grave tokens/API keys em arquivos do workspace. Use
   variáveis de ambiente (`VF_GPU_WORKER_TOKEN`, etc.).
7. **Resultado em uma pasta só (conveniência)**: ao concluir, quando o usuário
   não pedir outro destino, rode
   `vf_exec(action="step", step_id="delivery.collect", params={"mode":"copy"})`
   para consolidar vídeos e exports em
   `./VideoFlow_Output/{videos,exports,shorts,scenes}` na raiz do workspace.
   Isso não é requisito de validação: o MCP aceita qualquer caminho e nunca
   bloqueia uma entrega porque as saídas estão em outra pasta.
8. **Offload pesado**: use `compute_policy="auto"` ou `"remote"` para ASR,
   alinhamento forçado, matte, render NVENC, scene analysis e Short render
   quando o worker Windows estiver disponível; reporte `degraded` se houver
   fallback local.

## Estilos disponíveis no catálogo

{{STYLE_LIST}}

## Workflows disponíveis

{{WORKFLOW_LIST}}

## Comandos

- `/decupar <fonte>` — ingest, transcrição, cull e timeline base.
- `/beatmap <estilo>` — gera e revisa o manifesto de cenas.
- `/salvar-estilo <nome-ou-url>` — cria/clona e salva um estilo.
- `/exportar` — bundle MP4 + Resolve + Premiere + Kdenlive.

## Projetos

`VF_WORKSPACE_ROOT` aponta para `{{TARGET_DIR}}/projects`.
Cada projeto é aberto com `vf_project(action="open", project_id="...")`.
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

<!-- videoflow:opencode:end -->
