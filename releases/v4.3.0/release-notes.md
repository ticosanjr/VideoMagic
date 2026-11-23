# VideoFlow 4.3.0

Release MCP-First: curadoria visual em dois turnos, offload total para o Worker
Windows e limpeza dos subsistemas fora do escopo de edição.

## Destaques

- **Curadoria visual:** `vf_curation` (`publish`, `read`, `auto_select`), board
  persistente em `curation/board.json` e `curation/decisions.json`, API REST
  `/api/v1/curation/*` e tela **Curation** com player, botão **IA escolhe** e o
  modal local **Needs you**.
- **Offload total:** `HEAD /artifacts/{sha256}` com cache de upload por
  conteúdo, handlers remotos `ingest_pcm`, `audio_finalize` e `shorts_render`,
  e capabilities pesadas forçadas no Worker Windows saudável. `remote` segue
  fail-closed; fallback local exige `allow_slow_cpu_fallback=True` e registra
  `degraded=true`.
- **MCP mais direto:** `core` com 17 tools (`vf_jobs` + `vf_curation`) e `full`
  com 22. Toda resposta bem-sucedida inclui `_next_step`; listas acima de 30
  itens são truncadas, exceto `capabilities`.
- **UI em três telas:** **Curation**, **Jobs** e **Setup**. Configuração, GPU,
  estilos e bootstrap do OpenCode ficam em Setup; o HITL local continua em Jobs.
- **Limpeza estrutural:** publishing/webhooks, plugins, live source, pesquisa
  web, canais externos de HITL (Slack, e-mail IMAP e Signal) e receitas legadas
  lâmera, OpusClip, Full AI Editor e Synthetic foram removidos.

## Melhorias de performance e robustez

- Manifesto de capabilities com cache curto e invalidação em mudanças de GPU,
  eliminando probes de descoberta repetidos.
- Cache de `settings.json` por assinatura de arquivo, reduzindo leituras e
  validação Pydantic em subprocessos FFmpeg, caches e polling de preview/render.
- Sidecars de estado calculam o SHA-256 dos bytes já escritos, sem reler cada
  arquivo após a gravação.
- Listagem de artefatos resolve cada caminho uma única vez.
- Corrigidos: deadlock de `heartbeat`/`update_result`, jobs podados que
  ressuscitavam do SQLite, cache de schema após restore, escrita atômica de
  providers e coluna `recipe` para receitas aninhadas.
- Streaming SSE inclui `message`, `current_step`, `step_progress`, `eta_sec` e
  `log_count`, evitando eventos perdidos.

## Upgrade notes

- O perfil MCP padrão é `core`. Use `--profile full` para FX e estilo.
- `vf_exec` deixou de fazer parte do perfil oficial; use `vf_run` para uma
  cadeia de steps e as tools especializadas (`vf_shorts`, `vf_audio`, etc.).
- Os canais externos de HITL não existem mais. Aprovações, perguntas e arquivos
  continuam locais.
- Projetos existentes seguem válidos. O board de curadoria é opcional; sem ele,
  o fluxo autônomo escolhe os candidatos recomendados.
- O kit Windows empacota `videoflow_gpu_worker-4.3.0` e `vf_shared-4.3.0`.

## Artifacts

Binários Linux, AppImage, Windows, kit do GPU worker, SBOM e checksums são
publicados como assets desta release.

## Validation

- `ruff check src packages tests scripts` limpo.
- `pytest -q`: 2.905 testes verdes, 1 skipped, 1 xfailed; cobertura 96,8%.
- `pytest -m media`: 29 passed, 2 skipped.
- Svelte check sem erros; Vitest 53 passed; Playwright E2E 2 passed; build OK.
