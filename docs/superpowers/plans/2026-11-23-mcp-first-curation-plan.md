# Plano — VideoFlow MCP-First + Curadoria Visual + Offload Total

**TL;DR:** O repositório atual já concluiu a consolidação de `packages/vf-shared/`,
`src/videoflow/domains/` e a remoção do editor de timeline da UI. Para atingir os
5 objetivos fechados (**1a** UI de 3 telas, **2b** curadoria visual sob demanda
vs. autônomo, **3a** offload total >5s para Windows RTX 3060 via HTTP cacheado
por `media_id`, **4b** 4 exports NLE/MP4 e **5a** FX avançados opt-in) pelo
**caminho mais curto e simples possível**, esta especificação quebra o trabalho
em **5 Microspecs atômicas (P0 → P2)** prontas para execução pelo DeepSeek V4 no
OpenCode.

---

## 1. Objetivo Final e Escopo

**Objetivo Final:** Transformar o VideoFlow em um motor de edição determinístico
**MCP-First** otimizado para DeepSeek V4, composto por:

1. Offload automático para o Worker Windows de toda operação pesada (>5s) com
   upload HTTP único cacheado por SHA-256 (`media_id`);
2. Board de Curadoria Visual em 2 turnos sem timeout no MCP (`vf_curation` +
   tela web);
3. UI enxuta de 3 telas (`Curadoria`, `Jobs`, `Setup`);
4. MCP compacto com `_next_step`, 4 alvos de exportação (`mp4`, `resolve`,
   `premiere`, `kdenlive`) e FX avançados opt-in;
5. Remoção segura de módulos legados de "suíte completa".

**Fora de Escopo (NÃO alterar):**

- Algoritmos internos de timebase, retakes, decupagem e exportadores NLE
  (`src/videoflow/domain/timebase.py`, `src/videoflow/exporters/*`,
  `src/videoflow/application/decupage/*`).
- Implementação interna dos 5 efeitos FX
  (`src/videoflow/domains/vision/{motion,capture,matte}.py`,
  `src/videoflow/application/compositor.py`).
- UI embarcada do worker Windows
  (`packages/gpu-worker/src/gpu_worker/ui/*`).
- Workflows de CI/packaging (`.github/workflows/*`, `packaging/*`).

---

## 2. Mapa de Arquivos

| Arquivo | Ação | Motivo |
| --- | --- | --- |
| `packages/gpu-worker/src/gpu_worker/api_uploads.py` | Modificar | Adicionar `HEAD /artifacts/{sha256}` para checar cache `media_id` sem re-upload. |
| `packages/gpu-worker/src/gpu_worker/gpu_handlers/render.py` | Modificar | Adicionar handlers remotos leves para `ingest_pcm`, `audio_finalize` e `shorts_render`. |
| `packages/gpu-worker/src/gpu_worker/gpu_handlers/registry.py` | Modificar | Registrar os novos handlers pesados na allowlist oficial. |
| `packages/vf-shared/src/vf_shared/compute/client_transfer.py` | Modificar | Consultar `HEAD /artifacts/{sha256}` antes de subir mídia (upload único por hash). |
| `packages/vf-shared/src/vf_shared/compute/router.py` | Modificar | Implementar política `offload_all_heavy=True` (tudo >5s vai ao Worker Windows; fail-closed). |
| `packages/vf-shared/src/vf_shared/compute/router_health.py` | Modificar | Timeout `1.5s` no `/health` e retorno explícito de `worker_source` (`settings`/`mdns`/`env`). |
| `src/videoflow/application/curation_board.py` | Criar | Persistência atômica de `curation/board.json` e `curation/decisions.json` + auto-seleção. |
| `src/videoflow/api/routes_curation.py` | Criar | Endpoints REST da Curadoria Visual (`GET boards`, `GET board`, `GET media`, `POST decide`). |
| `src/videoflow/api/routes.py` | Modificar | Registrar `register_curation_routes` e remover rotas mortas na P2-1. |
| `src/videoflow/mcp_server/core_tools/official.py` | Modificar | Expor `vf_curation`, injetar `_next_step` e manter 4 alvos de export + FX opt-in. |
| `src/videoflow/mcp_server/guard.py` | Modificar | Limitar payloads longos (`<= 800 tokens` em listas) e padronizar `did_you_mean`. |
| `src/videoflow/mcp_server/registry.py` | Modificar | Garantir perfil `core` com **17 tools** (inclui `vf_jobs`) e `full` com **22** (`+5` FX opt-in). |
| `src/videoflow/templates/opencode/AGENTS.md` | Modificar | Enxugar para `<= 80 linhas` com fluxo `autonomous` vs `curation` e guia DeepSeek V4. |
| `src/videoflow/workflows/*.md` | Modificar | Adicionar passo explícito de `vf_curation` (modo curadoria) vs auto-seleção. |
| `ui/src/lib/CurationBoard.svelte` | Criar | Tela 1: Curadoria visual de Estilo, Música, SFX e B-Rolls com player e botão "IA escolhe". |
| `ui/src/lib/SetupPanel.svelte` | Criar | Tela 3: Consolida `GpuPanel`, `StylesPanel` e Bootstrap OpenCode em 3 sub-abas. |
| `ui/src/lib/navigation.ts` e `ui/src/routes/+page.svelte` | Modificar | Reduzir navegação para 3 telas: `Curation`, `Jobs` e `Setup` + `GpuStatusPill`. |
| `ui/src/lib/{Capabilities,Formats,Help,HitlInbox,Models,Plugins,Services,Settings,Workspace}Panel.svelte` | Remover | Painéis da antiga suíte completa fora das 3 telas do novo escopo. |
| `src/videoflow/application/hilt_channels/` | Remover | Pollers/webhooks Slack, E-mail IMAP e Signal não utilizados. |
| `src/videoflow/steps/research/` e `src/videoflow/application/search/` | Remover | Motor de pesquisa web e roteiro fora do escopo de edição MCP. |
| `src/videoflow/engine/recipes/definitions_{lamera,opusclip,full_ai_editor,synthetic}.py` | Remover | Receitas legadas da antiga suíte. |
| `src/videoflow/application/{live_source,publishing,plugins,plugin_sandbox}.py` e `src/videoflow/plugin_api.py` | Remover | Subsistemas de editor web/plugins/agendador fora do escopo MCP. |
| `docs/{3.0-blockers,backlog-2.80,opusclip-parity,migration-3.*,performance-3.*,refactor-3.*,hilt,plugins,shell,ui-spec}.md` e `docs/qa-evidence/` | Remover | Documentação histórica obsoleta que confunde agentes de código. |
| `scripts/{cut_eval,train_audio_events,resolve_smoke,tray_smoke,qa_evidence,gpu_acceptance,gpu_worker_smoke}.py` | Remover | Scripts redundantes substituídos por `scripts/e2e_micro_gate.py`. |

---

## 3. Contratos, Schemas e Invariantes

### 3.1. Contrato de Cache HTTP por `media_id` (`gpu-worker` ↔ `vf-shared`)

- **Endpoint no Worker Windows:** `HEAD /artifacts/{sha256}` (protegido por
  `X-VF-Token`).
- `200 OK` + header `X-VF-Artifact-Id: <sha256>`: arquivo já existe no cache do
  Windows — **não fazer upload**.
- `404 Not Found`: controlador envia via `POST /artifacts` uma única vez e
  reutiliza `sha256` em todos os jobs seguintes (`ingest_pcm`, `asr`, `scene`,
  `shorts_render`, `audio_finalize`, `render_nvenc`, `matte`).

**Regra de Offload (`router.py`):**

```python
HEAVY_CAPABILITIES = frozenset({
    "ingest_pcm", "asr", "audio_events", "scene", "audio_finalize",
    "shorts_render", "render_nvenc", "matte", "face_track", "upscale",
})
```

- Se `capability in HEAVY_CAPABILITIES` e o Worker Windows responder `/health`
  em `<= 1.5s`, **sempre** despachar para o Windows.
- **Fail-closed:** Se `require_worker=True` (padrão para vídeos >60s) e o Worker
  estiver offline, retornar
  `{"ok": False, "error_code": "gpu_worker_offline", "fix_hint": "Start VideoFlowGPU.bat on Windows or pass allow_cpu_fallback=True"}`
  em `< 2s`, sem fritar a CPU do Linux.

### 3.2. Contrato do Board de Curadoria Visual (`curation/board.json` e `decisions.json`)

```python
class CurationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    category: Literal["style", "music", "sfx", "broll", "image"]
    scene_id: str = ""
    title: str
    local_path: str = ""          # caminho local no projeto (validado por resolve_allowed)
    media_type: Literal["audio", "video", "image", "style"]
    duration_sec: float = 0.0
    recommended: bool = False     # escolha sugerida pela IA para o modo auto/delegate
    reason: str = ""
    status: Literal["pending", "selected", "rejected"] = "pending"

class CurationBoard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    board_id: str
    status: Literal["waiting_human", "decided", "delegated_to_ai"] = "waiting_human"
    items: list[CurationItem]
    updated_at: str
```

- **Streaming seguro na UI:**
  `GET /api/v1/curation/{project_id}/media/{item_id}` resolve `item.local_path`
  obrigatoriamente via `resolve_allowed()`, retornando `403` fora dos diretórios
  permitidos e `FileResponse` com suporte a `Range` (necessário para `<audio>` e
  `<video>` no navegador).

### 3.3. Contrato da Tool MCP `vf_curation` (2 Turnos, Zero Timeout)

```python
def vf_curation(
    action: Literal["publish", "read", "auto_select"],
    project_id: str,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]: ...
```

- `action="publish"`: grava `board.json`, **retorna imediatamente**
  `{ok: True, status: "waiting_human", board_url: "http://127.0.0.1:8765/#curation/<project_id>", item_count: N, _next_step: "Informe o link board_url ao usuário e aguarde ele dizer 'pronto' ou 'pode escolher você'."}`.
- `action="read"`: lê `decisions.json`. Se `status == "delegated_to_ai"`, aplica
  automaticamente os itens `recommended=True`. Se ainda `waiting_human`, retorna
  `{ok: True, status: "waiting_human", _next_step: "Aguardando confirmação na UI ou autorização para auto_select."}`.
- `action="auto_select"`: marca os itens `recommended=True` como `selected` (ou
  o 1º de cada `category`/`scene_id` se nenhum estiver marcado), grava
  `decisions.json` com `status="delegated_to_ai"` e retorna os itens
  selecionados.

### 3.4. Contrato de Resposta Compacta MCP (`_next_step`)

- Toda resposta bem-sucedida de tool MCP DEVE incluir
  `"_next_step": "<ação concreta>"`.
- Listas longas (sentenças, cenas, assets) devem ser paginadas ou truncadas no
  retorno direto (`max_items=30`) com `total_count` e `next_offset`, mantendo o
  retorno médio `< 800 tokens`.

---

## 4. Fases Atômicas de Implementação (Microspecs)

### FASE P0-1 — Offload Total (>5s) para Worker Windows com Upload Único (`media_id`)

**Arquivos da fase:**

- **Ler:** `packages/gpu-worker/src/gpu_worker/api_uploads.py`,
  `packages/gpu-worker/src/gpu_worker/artifacts.py`,
  `packages/gpu-worker/src/gpu_worker/gpu_handlers/render.py`,
  `packages/gpu-worker/src/gpu_worker/gpu_handlers/registry.py`,
  `packages/vf-shared/src/vf_shared/compute/client_transfer.py`,
  `packages/vf-shared/src/vf_shared/compute/router.py`,
  `packages/vf-shared/src/vf_shared/compute/router_health.py`.
- **Modificar:** Os 7 arquivos acima.
- **Não tocar:** `src/videoflow/exporters/*`, `ui/*`.

**Passos determinísticos:**

1. Em `packages/gpu-worker/src/gpu_worker/api_uploads.py`, adicionar rota
   `HEAD /artifacts/{artifact_id}` (autenticada por `X-VF-Token`) consultando
   `artifacts.py` se o arquivo content-addressed existe em disco (`200` com
   `X-VF-Artifact-Id` ou `404`).
2. Em `packages/vf-shared/src/vf_shared/compute/client_transfer.py`, antes de
   enviar multipart em `upload_artifact()`, calcular o SHA-256 local do arquivo
   e chamar `HEAD /artifacts/{sha256}`; se `200`, retornar imediatamente o
   `artifact_id` sem trafegar bytes na LAN.
3. Em `packages/gpu-worker/src/gpu_worker/gpu_handlers/render.py` e
   `registry.py`, registrar 3 handlers leves de FFmpeg/áudio: `ingest_pcm`
   (extrai WAV 48 kHz stereo + probe CFR), `audio_finalize` (executa `loudnorm`
   2-pass `-15.5 LUFS` + `aresample=48000`) e `shorts_render` (crop + queima
   `.ass` + `h264_nvenc` / fallback `libx264` rápido na CPU do Windows).
4. Em `packages/vf-shared/src/vf_shared/compute/router.py`, adicionar o conjunto
   `HEAVY_CAPABILITIES` da Seção 3.1 e fazer `route()` preferir o Worker Windows
   para **100%** dessas capabilities quando saudável; se offline e
   `allow_cpu_fallback=False`, levantar `GpuWorkerOfflineError` (fail-closed);
   se `allow_cpu_fallback=True`, executar local marcando `degraded=True`.
5. Em `router_health.py`, fixar timeout HTTP de `/health` em `1.5s` e incluir
   `worker_source` (`settings` → `mdns` → `env`) no resultado.
6. Criar teste `tests/unit/test_worker_media_id_cache.py` cobrindo hit/miss do
   `HEAD /artifacts/{sha256}` e roteamento de `HEAVY_CAPABILITIES`.

**Refatoração/Simplificação/Limpeza acoplada:** Remover qualquer fallback
silencioso que converta erro de conexão do worker em `local_cpu` sem preencher
`degraded=True`.

**Edge cases obrigatórios:**

- Arquivo local modificado com mesmo nome: o SHA-256 muda, garantindo miss no
  `HEAD` e upload novo.
- Worker retorna `401` (token errado): falhar imediatamente com
  `error_code="gpu_worker_auth_failed"`, nunca mascarar como offline.

**Validação:**

```bash
uv run pytest tests/unit/test_worker_media_id_cache.py tests/unit/test_compute_fail_closed.py tests/unit/test_gpu_worker.py -q
```

**Critério PASS:** `0 failed`; 2ª chamada de upload do mesmo arquivo faz `0`
`POST /artifacts`.

---

### FASE P0-2 — Backend de Curadoria Visual (`curation_board.py`, API REST e Tool `vf_curation`)

**Arquivos da fase:**

- **Ler:** `src/videoflow/domain/paths.py`, `src/videoflow/application/files.py`,
  `src/videoflow/api/routes.py`,
  `src/videoflow/mcp_server/core_tools/official.py`,
  `src/videoflow/mcp_server/registry.py`.
- **Criar:** `src/videoflow/application/curation_board.py`,
  `src/videoflow/api/routes_curation.py`, `tests/unit/test_curation_board.py`.
- **Modificar:** `src/videoflow/api/routes.py`,
  `src/videoflow/mcp_server/core_tools/official.py`,
  `src/videoflow/mcp_server/registry.py`.
- **Não tocar:** `ui/*` (será feito na P0-3).

**Passos determinísticos:**

1. Criar `src/videoflow/application/curation_board.py` com os modelos Pydantic
   da Seção 3.2 (`CurationItem`, `CurationBoard`) e funções:
   `publish_board(project_dir, project_id, items)`, `load_board(project_dir)`,
   `save_decisions(project_dir, selected_ids, rejected_ids, delegate_to_ai=False)`,
   `auto_select_board(project_dir)` e `list_pending_boards(projects_root)`.
   Usar `write_json_atomic` de `application/files.py`.
2. Criar `src/videoflow/api/routes_curation.py` com:
   - `GET /api/v1/curation/boards` (lista boards de todos os projetos conhecidos);
   - `GET /api/v1/curation/{project_id}` (retorna board + decisões atuais);
   - `GET /api/v1/curation/{project_id}/media/{item_id}` (valida `local_path`
     com `resolve_allowed()` e serve via `FileResponse`);
   - `POST /api/v1/curation/{project_id}/decide` (aceita
     `{selected_ids, rejected_ids, delegate_to_ai}`).
3. Registrar `register_curation_routes(app)` em `src/videoflow/api/routes.py`.
4. Adicionar a tool `vf_curation` (contrato Seção 3.3) em
   `src/videoflow/mcp_server/core_tools/official.py` e registrá-la no perfil
   `core` em `src/videoflow/mcp_server/registry.py`.
5. Escrever `tests/unit/test_curation_board.py` testando publish → decide humano
   → read, publish → `delegate_to_ai=True` → read, path traversal bloqueado
   (`403`) no endpoint de mídia, e retorno imediato com `_next_step`.

**Refatoração/Simplificação/Limpeza acoplada:** Reutilizar
`application/files.py:write_json_atomic` e `domain/paths.py:resolve_allowed` sem
criar helpers paralelos.

**Edge cases obrigatórios:**

- `item_id` duplicado no `publish`: rejeitar com
  `error_code="duplicate_item_id"` (fail-closed).
- `local_path` com `..` ou fora de `allowed_roots`: retornar HTTP
  `403 path_not_allowed`.
- `auto_select` quando nenhum item tiver `recommended=True`: selecionar
  deterministicamente o 1º item de cada `(category, scene_id)`.

**Validação:**

```bash
uv run pytest tests/unit/test_curation_board.py tests/unit/test_core_tools.py -q
```

**Critério PASS:** `0 failed`, `vf_curation` aparece no perfil `core` e endpoint
de mídia bloqueia path fora da allowlist.

---

### FASE P0-3 — Interface Web Minimalista de 3 Telas (`Curadoria`, `Jobs`, `Setup`)

**Arquivos da fase:**

- **Ler:** `ui/src/routes/+page.svelte`, `ui/src/lib/navigation.ts`,
  `ui/src/lib/api.ts`, `ui/src/lib/JobsPanel.svelte`,
  `ui/src/lib/GpuPanel.svelte`, `ui/src/lib/StylesPanel.svelte`,
  `ui/src/lib/IntegrationsPanel.svelte`, `ui/src/lib/GpuStatusPill.svelte`.
- **Criar:** `ui/src/lib/CurationBoard.svelte`, `ui/src/lib/SetupPanel.svelte`.
- **Modificar:** `ui/src/lib/api.ts`, `ui/src/lib/navigation.ts`,
  `ui/src/routes/+page.svelte`, `ui/src/lib/navigation.test.ts`,
  `ui/src/lib/panelRender.test.ts`.
- **Remover:** `ui/src/lib/CapabilitiesPanel.svelte`,
  `ui/src/lib/FormatsPanel.svelte`, `ui/src/lib/HelpPanel.svelte`,
  `ui/src/lib/HitlInbox.svelte`, `ui/src/lib/ModelsPanel.svelte`,
  `ui/src/lib/PluginsPanel.svelte`, `ui/src/lib/ServicesPanel.svelte`,
  `ui/src/lib/SettingsPanel.svelte`, `ui/src/lib/WorkspacePanel.svelte`.

**Passos determinísticos:**

1. Em `ui/src/lib/api.ts`, adicionar funções tipadas:
   `listCurationBoards()`, `getCurationBoard(projectId)`,
   `curationMediaUrl(projectId, itemId)` e
   `submitCurationDecision(projectId, payload)`.
2. Criar `ui/src/lib/CurationBoard.svelte`:
   - Lista boards pendentes à esquerda (com badge de contagem);
   - Agrupa cards por aba (`Estilos`, `Músicas`, `SFX`, `B-Rolls & Imagens`);
   - Renderiza `<audio controls src={mediaUrl}>` para música/SFX,
     `<video controls muted src={mediaUrl}>` para B-roll e `<img src={mediaUrl}>`
     para imagem;
   - Botões por card: **Selecionar** (borda verde) e **Excluir** (opacidade
     reduzida);
   - Barra fixa no topo: botão **"Deixar IA escolher os melhores"**
     (`delegate_to_ai: true`) e botão primário **"Confirmar Seleções"** (exibe
     aviso claro: *"Salvo! Volte ao OpenCode e digite 'pronto'."*).
3. Criar `ui/src/lib/SetupPanel.svelte` contendo exatamente 3 sub-abas:
   **Worker GPU Windows** (`GpuPanel.svelte`), **Estilos & Workflows**
   (`StylesPanel.svelte`) e **OpenCode Bootstrap** (`IntegrationsPanel.svelte`).
4. Simplificar `ui/src/lib/navigation.ts` e `ui/src/routes/+page.svelte` para
   apenas **3 abas de topo**: `#curation` (**Curadoria**), `#jobs` (**Jobs**) e
   `#setup` (**Setup**), mantendo `GpuStatusPill` no header.
5. Remover os 9 arquivos `*Panel.svelte` / `HitlInbox.svelte` listados acima e
   atualizar `navigation.test.ts` e `panelRender.test.ts` para as 3 telas.

**Refatoração/Simplificação/Limpeza acoplada:** Remover imports mortos e rotas
hash legadas que apontavam para os painéis excluídos em `navigation.ts` e
`+page.svelte`.

**Edge cases obrigatórios:**

- Nenhum board pendente: exibir estado vazio amigável explicando que basta pedir
  uma edição no OpenCode em modo curadoria.
- Deep-link `#curation/<project_id>` colado do OpenCode deve abrir diretamente o
  board daquele projeto.

**Validação:**

```bash
cd ui && npm run check && npm test -- --run && npm run build
```

**Critério PASS:** `svelte-check` com 0 erros, Vitest 100% verde e `vite build`
concluído sem warnings de imports quebrados.

---

### FASE P1-1 — Ergonomia MCP para DeepSeek V4 (`_next_step`, Compactação, 4 Exports e FX Opt-in)

**Arquivos da fase:**

- **Ler:** `src/videoflow/mcp_server/guard.py`,
  `src/videoflow/mcp_server/registry.py`,
  `src/videoflow/mcp_server/core_tools/official.py`,
  `src/videoflow/bootstrap/opencode_workspace.py`,
  `src/videoflow/templates/opencode/AGENTS.md`,
  `src/videoflow/workflows/youtube-longform.md`,
  `src/videoflow/workflows/reels-from-raw.md`,
  `src/videoflow/workflows/shorts-from-long.md`.
- **Modificar:** Os 8 arquivos acima.
- **Não tocar:** `src/videoflow/exporters/*`, `packages/*`.

**Passos determinísticos:**

1. Em `src/videoflow/mcp_server/guard.py`, adicionar normalização automática no
   retorno de sucesso de toda tool:
   - Garantir campo `_next_step` (usando o hint retornado pela tool ou um mapa
     padrão `DEFAULT_NEXT_STEP[tool_name]`);
   - Truncar qualquer lista de itens >30 elementos em respostas MCP adicionando
     `truncated: true`, `total_count` e
     `hint: "Use pagination/query parameters"`, mantendo a resposta compacta
     para a janela do DeepSeek V4.
2. Em `src/videoflow/mcp_server/registry.py`, consolidar os dois perfis:
   - `core` (**17 tools**): `vf_project`, `vf_session_brief`,
     `vf_capabilities`, `vf_ingest`, `vf_run`, `vf_transcript`, `vf_decupage`,
     `vf_scenes`, `vf_preview`, `vf_curation`, `vf_timeline`, `vf_shorts`,
     `vf_audio`, `vf_media`, `vf_export`, `vf_qa`, `vf_jobs`.
   - `full` (**22 tools** = core + 5 FX/Estilo opt-in): `vf_fx_depth`,
     `vf_fx_parallax`, `vf_fx_motion`, `vf_fx_capture`, `vf_style`.
3. Confirmar em `vf_export` (`official.py`) que os 4 alvos obrigatórios (`mp4`,
   `resolve`, `premiere`, `kdenlive`) permanecem habilitados por padrão (`4b`).
4. Reescrever `src/videoflow/templates/opencode/AGENTS.md` com **<= 80 linhas**
   diretas para o DeepSeek V4:
   - Passo 1: perguntar **Estilo**, **Workflow** e **Modo (`curation` na UI vs
     `autonomous`)**;
   - Passo 2: conferir Worker Windows (`vf_capabilities`);
   - Passo 3: decupar + buscar candidatos (música/SFX/B-roll);
   - Passo 4: em `curation`, chamar `vf_curation(action="publish")`, mostrar
     `board_url` e **parar o turno**; no retorno do usuário, chamar
     `vf_curation(action="read")` ou `auto_select`;
   - Passo 5: usar `vf_fx_*` **somente** se o estilo selecionado exigir;
     exportar os 4 alvos e rodar `vf_qa`.
5. Atualizar os arquivos
   `src/videoflow/workflows/{youtube-longform,reels-from-raw,shorts-from-long}.md`
   refletindo a etapa `vf_curation` e o modo autônomo/curadoria.

**Refatoração/Simplificação/Limpeza acoplada:** Garantir que
`bootstrap/opencode_workspace.py` gere `opencode.json` com **1 única entrada**
`"videoflow"` apontando para `videoflow mcp --profile full` (ou configurável pela
UI `SetupPanel`).

**Edge cases obrigatórios:**

- Se `vf_curation` receber `items=[]`, falhar com
  `error_code="empty_curation_board"` (fail-closed).
- `AGENTS.md` gerado não pode exceder 80 linhas
  (`assert len(text.splitlines()) <= 80` no teste).

**Validação:**

```bash
uv run pytest tests/unit/test_core_tools.py tests/unit/test_mcp_server_guard.py tests/unit/test_bootstrap_opencode.py tests/contract/test_mcp.py -q
```

**Critério PASS:** `0 failed`, toda tool retorna `_next_step`, `AGENTS.md <= 80
linhas`.

---

### FASE P2-1 — Limpeza Segura de Subsistemas Obsoletos da Antiga Suíte

**Arquivos da fase:**

- **Ler:** `src/videoflow/api/routes.py`, `src/videoflow/api/routes_admin.py`,
  `src/videoflow/api/routes_hilt.py`,
  `src/videoflow/application/export_service.py`,
  `src/videoflow/engine/recipes/catalog.py`, `src/videoflow/steps/registry.py`.
- **Modificar:** Os 6 arquivos acima + remoção/atualização dos testes exclusivos
  dos módulos removidos.
- **Remover:**
  - `src/videoflow/application/hilt_channels/` (Slack/Email/Signal) +
    `tests/unit/test_hilt_channels*.py`, `tests/unit/test_hilt_pollers.py`;
  - `src/videoflow/steps/research/` e `src/videoflow/application/search/` +
    `tests/unit/test_research_steps.py`, `tests/unit/test_parallel_research.py`,
    `tests/unit/test_search*.py`;
  - `src/videoflow/engine/recipes/definitions_{lamera,opusclip,full_ai_editor,synthetic}.py`
    + `tests/unit/test_lamera_recipe.py`, `tests/unit/test_full_ai_editor.py`;
  - `src/videoflow/application/{live_source,publishing,plugins,plugin_sandbox}.py`
    e `src/videoflow/plugin_api.py` + `tests/unit/test_live_source.py`,
    `tests/unit/test_publishing*.py`, `tests/unit/test_plugin*.py`;
  - Docs obsoletos: `docs/3.0-blockers.md`, `docs/backlog-2.80.md`,
    `docs/opusclip-parity.md`, `docs/migration-3.*.md`,
    `docs/performance-3.*.md`, `docs/refactor-3.*.md`, `docs/hilt.md`,
    `docs/plugins.md`, `docs/shell.md`, `docs/ui-spec.md`,
    `docs/qa-evidence/`;
  - Scripts redundantes: `scripts/cut_eval.py`,
    `scripts/train_audio_events.py`, `scripts/resolve_smoke.py`,
    `scripts/tray_smoke.py`, `scripts/qa_evidence.py`,
    `scripts/gpu_acceptance.py`, `scripts/gpu_worker_smoke.py`.

**Passos determinísticos:**

1. Antes de remover cada grupo, executar
   `rg "<nome_modulo>" src/ tests/ scripts/` para listar 100% dos imports ativos.
2. Remover referências a `hilt_channels` em `api/routes_hilt.py` e
   `application/hilt.py` (mantendo apenas o que for necessário se `hilt.py`
   ainda for usado por testes restantes, ou removendo os endpoints
   `/slack/events`, `/email/inbound`, `/hilt/channels`, `/hilt/secrets`).
3. Remover as 3 linhas de `plugin_api.exporter(target)` em
   `application/export_service.py` e as rotas `/api/v1/plugins*` em
   `api/routes_admin.py`.
4. Remover registros de `research.*` em `steps/registry.py` e das 4 definições de
   receita legadas em `engine/recipes/catalog.py`.
5. Deletar os diretórios/arquivos listados e seus testes exclusivos.
6. Rodar `ruff check` e a suíte completa de testes Python e UI para confirmar zero
   referências quebradas.

**Refatoração/Simplificação/Limpeza acoplada:** Rodar
`uv run python scripts/export_schemas.py` caso algum schema JSON tenha mudado e
validar `test_schemas.py`.

**Edge cases obrigatórios:**

- **NÃO** remover `src/videoflow/application/intelligence/` nem
  `src/videoflow/application/retakes/` (ainda usados por `editorial_clean` e
  `retakes.cull`).
- Conferir `tests/contract/test_openapi.py` e `tests/unit/test_repo_policy.py`
  após remover rotas antigas.

**Validação:**

```bash
uv run ruff check src packages scripts && uv run pytest -q && (cd ui && npm run check && npm test -- --run)
```

**Critério PASS:** `ruff` com 0 erros, `pytest` 100% verde e `ui` 100% verde.

---

## 5. Prompt de Execução para o OpenCode

```markdown
Você vai implementar a simplificação e evolução do VideoFlow para o novo
objetivo **MCP-First + Curadoria Visual + Offload Total para Worker Windows**
seguindo rigorosamente as 5 Microspecs (**P0-1, P0-2, P0-3, P1-1, P2-1**)
descritas acima.

## REGRAS OBRIGATÓRIAS DE EXECUÇÃO

1. **UMA FASE POR VEZ:** Comece EXCLUSIVAMENTE pela **FASE P0-1**. Não leia nem
   edite arquivos de fases futuras antes de concluir e validar a fase atual.
2. **LEITURA RESTRITA:** Leia primeiro apenas os arquivos listados na seção
   `Arquivos da fase` da fase atual.
3. **SIMPLIFICAÇÃO & FAIL-CLOSED:**
   - Prefira sempre a implementação mais simples, direta e sem abstrações
     extras.
   - Nunca silencie exceções (`except Exception: pass`) nem faça fallback
     silencioso de GPU para CPU sem registrar `degraded=True`.
   - Nunca delete ou enfraqueça testes de comportamento ativo para forçar
     `pytest` a passar.
   - Antes de remover qualquer arquivo na P2-1, execute `rg` em `src/`, `tests/`
     e `scripts/` para atualizar todos os imports primeiro.
4. **VALIDAÇÃO OBRIGATÓRIA:** Ao final de cada fase, rode o comando exato da
   seção `Validação` e corrija qualquer erro até obter `0 failed`.
5. **PARADA ENTRE FASES:** Ao concluir a fase atual com testes 100% verdes,
   apresente um resumo curto (arquivos tocados + saída do teste) e **PARE**
   perguntando se pode avançar para a próxima fase (`P0-2`, `P0-3`, `P1-1`,
   `P2-1`).

Inicie agora a **FASE P0-1** lendo os 7 arquivos listados e executando os
passos 1 a 6.
```

---

## 6. Decisões aprovadas e execução

### Decisões do usuário

- Perfil `core` mantém **17 tools**: `vf_jobs` permanece e `vf_curation` é
  adicionada. `full` passa a **22**.
- Offload pesado **força remote** quando o worker está saudável, ignorando fila,
  VRAM livre e utilização da GPU. O worker Windows é sempre considerado mais
  forte que o CPU local.
- Configurações desabilitadas explicitamente continuam fail-closed, sem fallback
  silencioso.
- A UI mantém apenas o que é útil: Curadoria, Jobs e Setup.
- HITL permanece funcional: curadoria em 2 turnos e aprovações/perguntas
  acessíveis na tela de Jobs.
- A release pode usar qualquer versão abaixo de 5.0; a próxima é **4.3.0**.

### Registro de execução — P0-1

```text
Fase: P0-1
Data: 2026-11-23
Arquivos alterados:
  packages/gpu-worker/src/gpu_worker/api_uploads.py
  packages/gpu-worker/src/gpu_worker/gpu_handlers/{audio,render,registry,__init__}.py
  packages/gpu-worker/src/gpu_worker/capabilities.py
  packages/vf-shared/src/vf_shared/compute/{capabilities,client,client_common,client_transfer,router,router_execute,router_health,router_submit,__init__}.py
  src/videoflow/application/{settings,schema_migrations,compute}.py
  tests/unit/test_worker_media_id_cache.py
  tests/unit/test_{compute_fail_closed,compute_router_stage7,compute_gpu_load_guard,gpu_capabilities,gpu_http_streaming,vf_contracts_compute}.py
Comando de validação:
  uv run pytest tests/unit/test_worker_media_id_cache.py tests/unit/test_compute_fail_closed.py tests/unit/test_gpu_worker.py -q
Resultado: 45 passed
Regressão: 3004 passed, 1 skipped, 1 xfailed; media 29 passed, 2 skipped.
Riscos residuais: fila/VRAM/utilização são ignoradas para capabilities pesadas por
decisão explícita; jobs podem esperar na fila do worker. Workers antigos sem
HEAD usam o fallback /artifacts/init.
```

### Registro de execução — P0-2

```text
Fase: P0-2
Data: 2026-11-23
Arquivos criados:
  src/videoflow/application/curation_board.py
  src/videoflow/api/routes_curation.py
  tests/unit/test_curation_board.py
Arquivos alterados:
  src/videoflow/api/routes.py
  src/videoflow/mcp_server/core_tools/official.py
  src/videoflow/mcp_server/registry.py
  tests/contract/test_mcp.py
  tests/unit/test_headless_mcp.py
  docs/mcp.md, docs/architecture.md e AGENTS.md
Perfis: core=17, full=22.
Comando de validação:
  uv run pytest tests/unit/test_curation_board.py tests/unit/test_core_tools.py -q
Resultado: 31 passed
Regressão: 3011 passed, 1 skipped, 1 xfailed; media 29 passed, 2 skipped.
Riscos residuais: o endpoint /boards lista apenas boards aguardando humano;
boards já decididos continuam acessíveis por /curation/{project_id}. O board
não valida local_path no publish; a validação ocorre no endpoint de mídia com
resolve_allowed.
```
