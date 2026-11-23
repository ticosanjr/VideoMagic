<!-- videoflow:opencode:start -->
# VideoFlow × OpenCode

Workspace preparado pelo VideoFlow {{VERSION}}.

## Protocolo

1. **Estilo, workflow e modo primeiro.** Antes de decupar, gerar beatmap,
   renderizar gráficos ou alterar qualquer vídeo, liste `./presets/*.md` e
   `./.opencode/workflows/*.md`, chame `vf_style(action="list")` e pergunte,
   em lista numerada: Estilo, Workflow e Modo (`curation` = você aprova na
   UI; `autonomous` = a IA escolhe).
2. **Não comece sem as respostas.** Para estilo novo, clone/extraia a
   referência e salve com
   `vf_style(action="save", workspace_dir="{{TARGET_DIR}}")`.
3. **Nunca escreva scripts FFmpeg manuais.** Use as tools MCP para ingest,
   transcrição, decupagem, motion, captura, QA e export.
4. **Fluxo determinístico:**
   1. `vf_ingest` + `vf_transcript` + `speech.editorial_clean` +
      `retakes.cull`.
   2. `vf_capabilities`; operações pesadas vão ao Worker Windows.
   3. `vf_decupage`; mostre o beat map e aguarde aprovação.
   4. **Modo curation:** `vf_curation(action="publish")`, mostre `board_url`,
      pare o turno e aguarde “pronto” ou “pode escolher você”. Depois use
      `vf_curation(action="read")` ou `action="auto_select"`. No modo
      `autonomous`, escolha os candidatos recomendados sem publicar board.
   5. `vf_timeline(action="apply_beatmap")`; use `vf_fx_*` somente se o
      estilo exigir.
   6. `vf_preview` + `vf_qa`; exporte `mp4`, `resolve`, `premiere` e
      `kdenlive` com `vf_export`, depois rode `vf_qa_final`.
5. **Siga `_next_step`** retornado pelas tools; ele indica a próxima ação
   concreta e evita polling desnecessário.
6. **Persistência de estilo.** Estilo novo ou clonado deve ser salvo no
   catálogo e sincronizado em `./presets/<style_id>.md`.
7. **Segurança.** Não grave tokens/API keys no workspace; use variáveis de
   ambiente (`VF_GPU_WORKER_TOKEN`, etc.).
8. **Entrega em uma pasta.** Ao concluir, sem outro destino, rode
   `vf_exec(action="step", step_id="delivery.collect", params={"mode":"copy"})`
   para consolidar em `./VideoFlow_Output/{videos,exports,shorts,scenes}`.
9. **Offload pesado.** ASR, alinhamento, matte, NVENC, scene analysis,
   ingest PCM e áudio final são forçados no Worker Windows quando saudável;
   reporte `degraded` somente em fallback autorizado.
10. **Profile enxuto.** `--profile core` (17 tools) no dia a dia;
    `--profile full` (22) apenas para FX ou estilo.

## Catálogo

{{STYLE_LIST}}

{{WORKFLOW_LIST}}

Cada estilo fica em `./presets/<style_id>.md`; cada workflow em
`./.opencode/workflows/<workflow_id>.md`. Liste os diretórios, chame
`vf_style(action="list")` e pergunte qual par usar.

## Projetos

`VF_WORKSPACE_ROOT` aponta para `{{TARGET_DIR}}/projects`.
Abra cada projeto com `vf_project(action="open", project_id="...")`.

## Regras visuais

- Texto atrás do apresentador: `vf_fx_depth(project_id, asset, start, end)`;
  nunca `remove_background(is_video=True)` no vídeo inteiro.
- Web 3D: `vf_fx_capture` + `vf_fx_motion(engine="hyperframes",
  transparent=True)`, `width_ratio=0.72`, `z=20`.
- Imagem parada: `image_to_broll_motion` ou `vf_fx_parallax`; documentário
  `max_static_sec=5.0`, Shorts `2.5`.
- Punch-in em rosto: `1.00 → 1.08`; nunca acima de `1.10`.
- Legendas: `z=40`, blocos de 4–6 palavras, `WrapStyle: 0`, safe-zones
  verticais. Lower third: `bottom_left`, `margin_x=64`, `margin_y=64`, `z=20`.
<!-- videoflow:opencode:end -->
