# Especificação v2 — Decupagem Perfeita, Shorts, MCP e Windows Nativo

**Status:** pendente de execução  
**Fonte:** `/especificacaov2`

**TL;DR:** Esta especificação corrige todos os defeitos reais encontrados no teste do OpenCode — decupagem cortando 50–65s sem guarda, `retakes.cull` quebrando antes do VAD, perda de `word_timestamps` em `captions.plan`, `beat_map.json` incompatível com `apply_beatmap`, Shorts sem legenda queimada/cortando screen-share/ignorando `count=2`, `vf_curation` sem suporte a Shorts, `vf_jobs(wait)` vazio, true peak `-1.3` vs `-1.5 dBTP` e erros de schema — e prepara o VideoFlow para **rodar e gerar releases nativos no Windows 11 (com GPU CUDA/NVENC local sem precisar de worker remoto)** em **5 Microspecs atômicas (P0 → P2)**.

---

## 1. Objetivo Final e Escopo

**Objetivo Final:** Garantir:

1. **Decupagem determinística perfeita** sem corte acidental de fala nem perda de `word_timestamps`, com revisão visual de cortes longos suspeitos.
2. **Shorts prontos para publicar** com legenda queimada, preferência por câmera e suporte no Board de Curadoria.
3. **MCP sem tentativa-e-erro** para DeepSeek v4.
4. **Execução e release nativos no Windows 11** aproveitando diretamente a GPU local (CUDA/NVENC) sem quebrar em caminhos `C:\`, fontes ou `/proc`.

**Fora de Escopo (NÃO alterar):**

- Algoritmos internos de DSP/DTW em `src/videoflow/domains/audio/compare_*.py`.
- Efeitos FX avançados (`src/videoflow/domains/vision/{matte,motion,capture}.py`, `src/videoflow/application/compositor.py`).
- Arquitetura do worker remoto HTTP (`packages/gpu-worker/*`) — permanece opcional, mas não é mais obrigatório quando rodando localmente no Windows.
- Exportadores XML NLE além da preservação do contrato atual (`src/videoflow/exporters/{fcpxml,xmeml,kdenlive}/*`).

---

## 2. Mapa de Arquivos

| Arquivo | Ação | Motivo |
| --- | --- | --- |
| `src/videoflow/steps/retakes.py` | Modificar | Validar/auto-exigir `audio.vad` antes de `retakes.cull` e preservar `words` na transcrição. |
| `src/videoflow/steps/editorial_clean.py` | Modificar | Preservar `word_timestamps` em 100% das sentenças mantidas e fechar loop de candidatos semânticos. |
| `src/videoflow/application/decupage/deterministic.py` | Modificar | Implementar guarda `VAD ∪ ASR` (nunca apagar fala transcrita) e sinalizar cortes `> 15s` para revisão. |
| `src/videoflow/application/decupage/snap.py` | Modificar | Garantir piso rígido de pads (`90ms / 150ms`) após snap acústico em vale RMS. |
| `src/videoflow/application/beatmap_plan.py` | Modificar | Emitir exatamente o schema aceito por `apply_beatmap` (`keep_ranges` + `overlays` + `captions`). |
| `src/videoflow/application/beatmap.py` | Modificar | Aceitar `beat_map_path` diretamente e validar com o mesmo modelo de `beatmap_plan.py`. |
| `src/videoflow/steps/captions.py` | Modificar | Carregar `words` de `state.transcript` / `transcript_clean.json` garantindo `\kf` palavra-a-palavra. |
| `src/videoflow/steps/shorts_select.py` | Modificar | Honrar `count`, corrigir contradição `speech_ratio` (selecionado vs descartado) e preferir cenas em câmera (`vf_scenes`). |
| `src/videoflow/application/shorts_batch.py` | Modificar | Adicionar `burn_subtitles: bool = True`, `time_basis: "edited" \| "source"`, e rejeitar clipes `< 3.0s`. |
| `src/videoflow/application/curation_board.py` | Modificar | Adicionar categorias `"short"` e `"cut_review"` em `CurationItem.category`. |
| `ui/src/lib/CurationBoard.svelte` | Modificar | Adicionar abas **Shorts** e **Revisão de Cortes** no Board visual. |
| `src/videoflow/domains/audio/finalize.py` | Modificar | Ajustar 2-pass `loudnorm` para `TP=-2.0 dBTP` (evita overshoot AAC de `-1.3` vs `-1.5`) e `48 kHz`. |
| `src/videoflow/core/media_contract/constants.py` | Modificar | Alinhar constante única `TARGET_LUFS = -16.0`, `TOLERANCE_LUFS = 1.5`, `MAX_TRUE_PEAK_DBTP = -1.0`. |
| `src/videoflow/steps/video_export.py` | Modificar | Auto-executar `audio.finalize` se `final_mix.wav` não existir antes do mux/export. |
| `src/videoflow/steps/delivery_collect.py` | Modificar | Isolar entrega em `{delivery_root}/{project_slug}/` (nunca misturar runs na mesma raiz). |
| `src/videoflow/mcp_server/registry.py` | Modificar | Incluir `vf_style` no perfil `core` para leitura/validação/aplicação sem ler `.md` na mão. |
| `src/videoflow/mcp_server/core_tools/core_projects.py` | Modificar | Aceitar aliases `create`/`new` → `init`, `output` opcional e resolver `slug ↔ uuid` em todo lugar. |
| `src/videoflow/mcp_server/core_tools/core_jobs.py` | Modificar | Corrigir `vf_jobs(wait)` (nunca retornar `{}`) e escopar/filtrar `params` por step em `vf_run`. |
| `src/videoflow/mcp_server/core_tools/core_export.py` | Modificar | Garantir payload completo em sucesso/erro (nunca `{ok: False}` vazio). |
| `src/videoflow/mcp_server/guard.py` | Modificar | Incluir `expected_fields` no `fix_hint` quando ocorrer `ValidationError`. |
| `src/videoflow/adapters/ffmpeg/helpers.py` | Modificar | Criar `escape_ffmpeg_filter_path(path)` tratando drive Windows (`C\:/...`) em `ass=` e `drawtext=`. |
| `src/videoflow/application/fonts.py` | Modificar | Resolver fontes nativas em `C:\Windows\Fonts` quando `os.name == "nt"` (sem depender de `fc-match`). |
| `src/videoflow/application/services.py` | Modificar | Implementar descoberta/parada de processo Windows (`os.name == "nt"`) sem ler `/proc` nem usar `killpg`. |
| `src/videoflow/application/render_gate.py` | Modificar | Adicionar lock cross-process no Windows usando `msvcrt.locking` (paridade com `fcntl` no Linux). |
| `packages/vf-shared/src/vf_shared/compute/router.py` | Modificar | Suportar `compute_mode="local_gpu"` detectando CUDA/NVENC local automaticamente no Windows. |
| `scripts/build_portable.py` e `packaging/videoflow.spec` | Modificar | Garantir build nativo Windows (`videoflow.exe` + `ffmpeg.exe`/`ffprobe.exe` + Silero + UI + hiddenimports). |
| `.github/workflows/windows-build.yml` | Modificar | Validar build nativo Windows + rodar smoke test real (`scripts/smoke_windows.py`) no runner `windows-latest`. |
| `scripts/smoke_windows.py` | Criar | Smoke test determinístico Windows: FFmpeg `C:\` filter escape, font lookup, local CUDA/NVENC probe, `serve /health`, `mcp`. |
| `ui/src/lib/{HitlInbox,SettingsPanel,WorkspacePanel}.svelte` | Remover | Painéis legados ainda presentes em `ui/src/lib/` fora da UI de 3 telas (`Curation`, `Jobs`, `Setup`). |

---

## 3. Contratos, Schemas e Invariantes

### 3.1. Invariante de Decupagem Perfeita (`VAD ∪ ASR` + Guarda de Cortes Longos)

```python
def build_safe_speech_spans(
    vad_spans: list[tuple[int, int]],
    kept_sentences: list[Sentence],
    discard_ids: set[int],
    *,
    sample_rate: int = 48_000,
    min_word_prob: float = 0.45,
    pad_before_ms: int = 90,
    pad_after_ms: int = 150,
    long_cut_review_sec: float = 15.0,
) -> tuple[list[tuple[int, int]], list[dict[str, Any]]]:
    """Une intervalos VAD com palavras ASR mantidas (prob >= 0.45),
    aplica piso de pads e retorna (kept_spans, flagged_long_cuts)."""
```

- **Regra 1 (Zero Fala Deletada por VAD):** Qualquer sentença não descartada por retake contendo palavras com `probability >= 0.45` entra na união `VAD ∪ ASR` — voz baixa nunca é apagada como silêncio.
- **Regra 2 (Guarda de Cortes `> 15s`):** Todo gap removido `> 15.0s` gera um item em `flagged_long_cuts` (`{start_sec, end_sec, duration_sec, rms_dbfs, word_count, reason}`). Se `word_count > 0` ou `rms_dbfs > -42.0`, o corte é marcado `requires_review=True` e elegível para `vf_curation(category="cut_review")`.
- **Regra 3 (Ordem Canônica):** `vf_decupage(action="run_full", project_id, style_id)` executa deterministicamente: `ingest → audio.vad → transcribe → speech.editorial_clean → retakes.cull → decupage.snap → edit.timeline` — eliminando erro de ordem (`retakes.cull` antes de `audio.vad`).

### 3.2. Contrato Único `BeatMapPlan` (`beatmap_plan.py` == `beatmap.py`)

```python
class BeatMapPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2] = 2
    style_id: str
    time_basis: Literal["edited", "source"] = "edited"
    keep_ranges: list[TimeRangeSec] = Field(default_factory=list)
    remove_ranges: list[TimeRangeSec] = Field(default_factory=list)
    overlays: list[dict[str, Any]] = Field(default_factory=list)
    transitions: list[dict[str, Any]] = Field(default_factory=list)
    captions: list[dict[str, Any]] = Field(default_factory=list)
```

- `build_beatmap_plan()` retorna `BeatMapPlan.model_dump(mode="json")`.
- `vf_timeline(action="apply_beatmap", project_id=..., beat_map_path="beat_map.json")` valida e aplica o arquivo diretamente sem erro de campo proibido.

### 3.3. Contrato de Áudio & QA (Sem Falha de `-1.3` vs `-1.5 dBTP`)

Em `src/videoflow/core/media_contract/constants.py`:

- `TARGET_LUFS = -16.0`, `TOLERANCE_LUFS = 1.5` (aprovado: `[-17.5, -14.5] LUFS`).
- `LOUDNORM_TARGET_TP_DB = -2.0` (alvo passado ao filtro `loudnorm` 2-pass para absorver overshoot do encoder AAC).
- `QA_MAX_TRUE_PEAK_DBTP = -1.0` (gate de aprovação no MP4 AAC final, padrão EBU R128 / YouTube).

### 3.4. Contrato de Shorts (`vf_shorts`) e Curadoria (`vf_curation`)

- `ShortsClipSpec`:
  - `time_basis: Literal["edited", "source"] = "edited"` (padrão explícito e documentado).
  - `burn_subtitles: bool = True` (queima `.ass` no MP4 por padrão + preserva sidecar `.ass`).
  - Validação fail-closed: `end_sec - start_sec < 3.0` levanta `error_code="invalid_short_duration"` (nunca renderiza clipe de `0.3s`).
- `CurationItem.category`: `Literal["style", "music", "sfx", "broll", "image", "short", "cut_review"]`.

### 3.5. Contrato de Escape de Caminhos Windows para Filtros FFmpeg

```python
def escape_ffmpeg_filter_path(path: Path | str) -> str:
    """Converte C:\\Users\\foo\\sub.ass -> C\\:/Users/foo/sub.ass
    e escapa aspas simples/colchetes para filtros ass= e drawtext=."""
```

- Uso obrigatório em `subtitles.py`, `scene_web.py`, `motion.py`, `shorts_batch.py` e `exporters/mp4.py`.

---

## 4. Fases Atômicas de Implementação (Microspecs)

### FASE P0-1 — Decupagem Perfeita, Preservação de `word_timestamps` e Beatmap Unificado

**Arquivos da fase:**

- **Ler:** `src/videoflow/application/decupage/deterministic.py`, `src/videoflow/application/decupage/snap.py`, `src/videoflow/steps/retakes.py`, `src/videoflow/steps/editorial_clean.py`, `src/videoflow/steps/captions.py`, `src/videoflow/application/beatmap_plan.py`, `src/videoflow/application/beatmap.py`.
- **Modificar:** os 7 arquivos acima + `src/videoflow/mcp_server/core_tools/core_timeline.py`.
- **Não tocar:** `ui/*`, `packages/*`, `src/videoflow/exporters/*`.

**Passos determinísticos:**

1. Em `src/videoflow/steps/retakes.py`, verificar se `context.speech_intervals` (do `audio.vad`) está populado; se vazio, levantar erro explícito `error_code="missing_prerequisite", fix_hint="Execute audio.vad antes de retakes.cull ou use vf_decupage(action='run_full')"` (elimina o falso erro `"Culling and overrides removed all speech"`).
2. Em `src/videoflow/application/decupage/deterministic.py`, implementar `build_safe_speech_spans()` (Seção 3.1): unir `vad_spans` com palavras mantidas (`probability >= 0.45`), gerar `flagged_long_cuts` para qualquer remoção `> 15.0s` e gravar `decupage/report.json`.
3. Em `src/videoflow/application/decupage/snap.py`, impor o piso de pads após o snap em vale RMS (`start = min(snapped_start, first_word - 90ms)`, `end = max(snapped_end, last_word + 150ms)`) usando `floor`/`ceil` na quantização de frame.
4. Em `src/videoflow/steps/editorial_clean.py` e `src/videoflow/steps/captions.py`, garantir que `Sentence.words` nunca seja zerado/descartado ao gravar `transcript_clean.json` e `state.transcript`, e fazer `captions.plan` carregar `words` de `state.transcript` (ou `transcript_clean.json`) gerando `\kf` palavra-a-palavra quando `effect="karaoke_sweep"`.
5. Unificar `application/beatmap_plan.py` e `application/beatmap.py` no modelo único `BeatMapPlan` (Seção 3.2), adicionando suporte a `beat_map_path` em `vf_timeline(action="apply_beatmap")`.
6. Adicionar `action="run_full"` em `vf_decupage` executando a sequência canônica (`audio.vad → transcribe → speech.editorial_clean → retakes.cull → decupage.snap → edit.timeline`) e retornando `flagged_long_cuts`, `beat_map_path` e estatísticas de corte.
7. Criar testes em `tests/unit/test_decupage_perfect.py` cobrindo: erro de ordem antes do VAD, voz baixa protegida por `VAD ∪ ASR`, flag de corte `> 15s`, round-trip `beatmap_plan → apply_beatmap` e preservação de `words` até `captions.plan`.

**Refatoração/Simplificação/Limpeza acoplada:** Remover campos obsoletos emitidos por `beatmap_plan.py` que causavam `extra_forbidden` em `apply_beatmap`.

**Edge cases obrigatórios:**

- Vídeo com 3 minutos iniciais de microfone mudo (`rms < -55 dBFS`, `word_count == 0`): pode ser cortado automaticamente, mas aparece documentado em `flagged_long_cuts` com `requires_review=False`.
- Bloco de 50s com voz baixa transcrita (`word_count > 5`): preservado pela união `VAD ∪ ASR` e nunca cortado como silêncio.

**Validação:**

```bash
uv run pytest tests/unit/test_decupage_perfect.py tests/unit/test_beatmap.py tests/unit/test_retakes.py tests/unit/test_decupage_snap.py -q
```

**Critério PASS:** `0 failed`; `beatmap_plan` aplica em `apply_beatmap` sem adaptar 1 campo; `captions.plan` gera `\kf`.

---

### FASE P0-2 — Shorts Perfeitos (`burn_subtitles`, Câmera vs Tela), Curadoria de Shorts e Áudio/Delivery

**Arquivos da fase:**

- **Ler:** `src/videoflow/steps/shorts_select.py`, `src/videoflow/application/shorts_batch.py`, `src/videoflow/application/curation_board.py`, `src/videoflow/domains/audio/finalize.py`, `src/videoflow/core/media_contract/constants.py`, `src/videoflow/steps/video_export.py`, `src/videoflow/steps/delivery_collect.py`, `ui/src/lib/CurationBoard.svelte`.
- **Modificar:** os 8 arquivos acima.
- **Não tocar:** `src/videoflow/exporters/*`.

**Passos determinísticos:**

1. Em `src/videoflow/steps/shorts_select.py`:
   - Corrigir bug de contabilidade que colocava o mesmo candidato em `selected` e `discarded`.
   - Calcular `speech_ratio` sobre a duração da janela *editada/tightened* (nunca contra o intervalo bruto com silêncio), honrando `count` / `max_clips_to_generate`.
   - Ler `scenes_manifest.json` quando existir: pontuar positivamente cenas `TALKING_HEAD` e penalizar/evitar `SCREEN_SHARE_FULL` em crops `9:16` centrais (ou selecionar layout `SPLIT_SCREEN_SAFE`).

2. Em `src/videoflow/application/shorts_batch.py`:
   - Adicionar `burn_subtitles: bool = True` (queimando o `.ass` gerado no MP4 final do Short e mantendo o `.ass` sidecar).
   - Adicionar `time_basis: Literal["edited", "source"] = "edited"` com erro explícito informando a duração válida da timeline editada quando `start_sec`/`end_sec` sair do intervalo.
   - Rejeitar qualquer clipe com `duration < 3.0s` (`error_code="invalid_short_duration"`, nunca criar clipe de `0.3s`).

3. Em `src/videoflow/application/curation_board.py` e `ui/src/lib/CurationBoard.svelte`, adicionar suporte às categorias `"short"` e `"cut_review"` (com player de vídeo nos cards de Short/Corte para aprovação visual na UI).

4. Em `src/videoflow/core/media_contract/constants.py` e `src/videoflow/domains/audio/finalize.py`, aplicar Seção 3.3 (`LOUDNORM_TARGET_TP_DB = -2.0`, `QA_MAX_TRUE_PEAK_DBTP = -1.0`, `TARGET_LUFS = -16.0 ± 1.5`).

5. Em `src/videoflow/steps/video_export.py`, executar `audio.finalize` automaticamente antes do mux caso `audio/final_mix.wav` ainda não exista (elimina QA falhando com `-26 LUFS`).

6. Em `src/videoflow/steps/delivery_collect.py`, gravar a entrega sempre em `{target_root}/{project_slug}/` (isolando cada projeto na pasta de saída).

7. Criar testes em `tests/unit/test_shorts_and_audio_fixes.py`.

**Refatoração/Simplificação/Limpeza acoplada:** Remover constantes duplicadas de `TARGET_LUFS` / `TRUE_PEAK` em `qa_final.py`, importando exclusivamente de `core/media_contract/constants.py`.

**Edge cases obrigatórios:**

- `shorts.select(count=2)` com 3 candidatos válidos deve retornar exatamente 2 clipes distintos e `set(selected_ids).isdisjoint(discarded_ids)`.
- Short de `0.3s` deve falhar antes de invocar FFmpeg e deixar 0 arquivos órfãos em `shorts/batch/`.

**Validação:**

```bash
uv run pytest tests/unit/test_shorts_and_audio_fixes.py tests/unit/test_curation_board.py tests/unit/test_audio_finalize.py -q && (cd ui && npm run check)
```

**Critério PASS:** `0 failed` no `pytest` e `0 errors` no `svelte-check`.

---

### FASE P0-3 — Ergonomia MCP à Prova de DeepSeek v4 (`vf_style`, Slugs, `vf_run`, `vf_jobs`, Schemas)

**Arquivos da fase:**

- **Ler:** `src/videoflow/mcp_server/registry.py`, `src/videoflow/mcp_server/core_tools/core_projects.py`, `src/videoflow/mcp_server/core_tools/core_jobs.py`, `src/videoflow/mcp_server/core_tools/core_export.py`, `src/videoflow/mcp_server/guard.py`, `src/videoflow/application/projects.py`.
- **Modificar:** os 6 arquivos acima + `src/videoflow/mcp_server/agent_resources.py`.
- **Não tocar:** `ui/*`, `packages/*`.

**Passos determinísticos:**

1. Em `src/videoflow/mcp_server/registry.py`, mover `vf_style` para o perfil `core` (garantindo que o OpenCode leia/valide/aplique estilos via MCP sem ler arquivos `.md` manualmente).
2. Em `src/videoflow/mcp_server/core_tools/core_projects.py` e `application/projects.py`:
   - Aceitar `action in {"init", "create", "new"}` criando o projeto com `slug = project_id or name`.
   - Tornar `output` opcional (default: `$VF_WORKSPACE_ROOT/projects/{slug}`).
   - Retornar sempre `project_id: slug` + `uuid` e garantir resolução `slug ↔ uuid` em **100%** das tools.
3. Em `src/videoflow/mcp_server/core_tools/core_jobs.py`:
   - Em `vf_run(steps=[...], params=...)`, aceitar `step_params: dict[str, dict]` E, se receber `params` plano, filtrar automaticamente apenas os campos presentes em `step.params_model.model_fields` para cada step (falhando com `invalid_params` apenas se uma chave não pertencer a *nenhum* step da lista).
   - Em `vf_jobs(action="wait", job_id=...)`, aguardar até estado terminal e retornar sempre `{ok, job_id, status, result, error, artifacts}` (nunca `{}`).
4. Em `src/videoflow/mcp_server/core_tools/core_export.py`, garantir que qualquer falha retorne payload estruturado via `@mcp_tool_guard` (nunca `{ok: False}` vazio).
5. Em `src/videoflow/mcp_server/guard.py`, ao capturar `pydantic.ValidationError`, incluir `expected_fields: {campo: tipo}` no `fix_hint` para o DeepSeek v4 corrigir na chamada seguinte sem adivinhação.
6. Adicionar testes em `tests/unit/test_mcp_ergonomics_v43.py`.

**Refatoração/Simplificação/Limpeza acoplada:** Centralizar a resolução `resolve_project_ref(project_id)` em `application/projects.py` para ser chamada por todos os `core_tools/*.py`.

**Edge cases obrigatórios:**

- `vf_project(action="create", project_id="paula-ep-10")` sem passar `output` cria `$VF_WORKSPACE_ROOT/projects/paula-ep-10` e funciona em `vf_ingest(project_id="paula-ep-10")`.
- `vf_run(steps=["timeline.load", "shorts.select"], params={"count": 2, "aspect_ratio": "9:16"})` entrega `count`/`aspect_ratio` apenas para `shorts.select`, sem quebrar `timeline.load`.

**Validação:**

```bash
uv run pytest tests/unit/test_mcp_ergonomics_v43.py tests/unit/test_core_tools.py tests/unit/test_mcp_server_guard.py tests/contract/test_mcp.py -q
```

**Critério PASS:** `0 failed`.

---

### FASE P1-1 — Execução Nativa Windows 11 + GPU Local CUDA/NVENC (Zero `/proc`, Escape `C\:/`, Fontes Windows)

**Arquivos da fase:**

- **Ler:** `src/videoflow/adapters/ffmpeg/helpers.py`, `src/videoflow/adapters/ffmpeg/subtitles.py` (ou `shorts.py`/`render.py`), `src/videoflow/application/fonts.py`, `src/videoflow/application/motion.py`, `src/videoflow/application/services.py`, `src/videoflow/application/render_gate.py`, `packages/vf-shared/src/vf_shared/compute/router.py`, `src/videoflow/application/asr_profiles.py`.
- **Modificar:** os arquivos acima + `src/videoflow/application/scene_web.py`.
- **Não tocar:** `packages/gpu-worker/src/gpu_worker/ui/*`.

**Passos determinísticos:**

1. Em `src/videoflow/adapters/ffmpeg/helpers.py`, criar `escape_ffmpeg_filter_path(path: Path | str) -> str`: normalizar `\` → `/`, escapar `:` como `\:` (crítico para `C:\...` no Windows) e `'` como `\'`. Aplicar em **todos** os locais que montam filtros `ass=`, `subtitles=`, `fontsdir=` e `fontfile=` (`adapters/ffmpeg/*`, `application/motion.py`, `application/scene_web.py`, `exporters/mp4.py`).
2. Em `src/videoflow/application/fonts.py` e `application/motion.py`, adicionar fallback nativo para Windows (`os.name == "nt"`): varrer `Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"` (`arial.ttf`, `segoeui.ttf`, `calibri.ttf`, `consola.ttf`) antes de tentar `fc-match`.
3. Em `src/videoflow/application/services.py`, adicionar ramo `if os.name == "nt":` em `discover_services()`, `process_alive()` e `stop_service_pid()` usando PID file + `probe_service()` + `ctypes.windll.kernel32` / `taskkill /PID <pid> /T /F` (sem tocar em `/proc` nem `os.killpg`).
4. Em `src/videoflow/application/render_gate.py`, usar `msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)` quando `os.name == "nt"` (garantindo exclusão mútua entre processos no Windows).
5. **Modo GPU Local Nativo (`local_gpu`) no Windows:** em `packages/vf-shared/src/vf_shared/compute/router.py` e `src/videoflow/application/asr_profiles.py` / `src/videoflow/core/nvenc.py`:
   - Ao rodar em uma máquina com NVIDIA CUDA + `h264_nvenc` local (como o desktop Windows 11 com RTX 3060), detectar automaticamente `local_gpu_available = True` (`ctranslate2.get_cuda_device_count() > 0` ou `nvidia-smi` + probe `h264_nvenc`);
   - Selecionar `device="cuda", compute_type="float16"` no Faster-Whisper local e `h264_nvenc` no FFmpeg local automaticamente quando `compute_policy in {"auto", "local_gpu"}` (mantendo fallback `cpu`/`int8` quando não houver GPU NVIDIA, como em CI).
6. Criar testes `tests/unit/test_windows_compat.py` simulando caminhos `C:\Users\Rafael\vídeo\sub.ass`, `os.name == "nt"` sem `/proc`, lock de arquivo e resolução `local_gpu`.

**Refatoração/Simplificação/Limpeza acoplada:** Remover chamadas duplicadas de escape manual `.replace("\\", "/").replace(":", "\\:")` espalhadas em `scene_web.py` e `ffmpeg/`, substituindo pela função única `escape_ffmpeg_filter_path()`.

**Edge cases obrigatórios:**

- Caminho Windows com espaço e acento (`C:\Users\Rafael\Edição Vídeo\legenda.ass`): deve gerar filtro FFmpeg sintaticamente válido.
- Input 10-bit 4:2:2 (Sony ZV-E10 II) em `local_gpu`: decodificar em CPU e encodar em `h264_nvenc` (`-pix_fmt yuv420p`) sem falhar no NVDEC.

**Validação:**

```bash
uv run pytest tests/unit/test_windows_compat.py tests/unit/test_services.py tests/unit/test_nvenc_probe.py tests/unit/test_asr_profiles.py -q
```

**Critério PASS:** `0 failed`, escape `C\:/...` validado e `services.py` sem dependência de `/proc` no Windows.

---

### FASE P2-1 — Release Nativo Windows Primeiro-Cidadão & Limpeza Residual da UI

**Arquivos da fase:**

- **Ler:** `scripts/build_portable.py`, `packaging/videoflow.spec`, `.github/workflows/windows-build.yml`, `scripts/release.py`, `ui/src/routes/+page.svelte`.
- **Criar:** `scripts/smoke_windows.py`.
- **Modificar:** `scripts/build_portable.py`, `packaging/videoflow.spec`, `.github/workflows/windows-build.yml`.
- **Remover:** `ui/src/lib/HitlInbox.svelte`, `ui/src/lib/SettingsPanel.svelte`, `ui/src/lib/WorkspacePanel.svelte` (confirmando antes com `rg` que nenhum componente ativo os importa).

**Passos determinísticos:**

1. Verificar via `rg` em `ui/src/` se `HitlInbox.svelte`, `SettingsPanel.svelte` e `WorkspacePanel.svelte` têm referências mortas; remover imports órfãos e deletar os 3 arquivos.
2. Em `packaging/videoflow.spec` e `scripts/build_portable.py`, assegurar empacotamento Windows (`onedir` zipável rápido + `onefile` opcional) incluindo: `ui/build`, `src/videoflow/styles/`, `src/videoflow/workflows/`, `src/videoflow/templates/opencode/`, `ffmpeg.exe`, `ffprobe.exe`, `silero_vad.onnx` e `hiddenimports` atualizados (`videoflow.api.routes_curation`, `videoflow.application.curation_board`, `vf_shared`).
3. Criar `scripts/smoke_windows.py` que valida no executável Windows (com `PATH` limpo): `videoflow.exe version`, `videoflow.exe doctor` (confirmando `ffmpeg.exe`, `ffprobe.exe`, fontes Windows, status CUDA/NVENC local), `videoflow.exe mcp --profile core` (listando `vf_style`, `vf_curation`, `vf_decupage`, `vf_shorts`, `vf_export`), e `videoflow.exe serve` respondendo `200 /health` e `200 /api/v1/curation/boards`.
4. Atualizar `.github/workflows/windows-build.yml` para construir o frontend Svelte, empacotar o release Windows nativo (`windows-latest`), executar `scripts/smoke_windows.py` e publicar o `.zip` portátil como artifact de release.

**Refatoração/Simplificação/Limpeza acoplada:** Rodar `ruff check src packages scripts` para limpar imports não usados.

**Edge cases obrigatórios:**

- `videoflow.exe` rodando de pasta com espaços (`C:\VideoFlow Studio\videoflow.exe`) não pode quebrar descoberta de `_MEIPASS`, UI ou `ffmpeg.exe`.
- `scripts/smoke_windows.py` deve encerrar sempre o processo `serve` em bloco `finally` (sem deixar `videoflow.exe` preso no runner).

**Validação:**

```bash
uv run ruff check src packages scripts && uv run pytest -q && (cd ui && npm run check && npm test -- --run && npm run build)
```

**Critério PASS:** `ruff` 0 erros, `pytest` 100% verde, UI `check`/`test`/`build` 100% verdes e `scripts/smoke_windows.py --help` funcional.

---

## 5. Prompt de Execução para o OpenCode

```markdown
Você vai implementar as correções de **Decupagem Perfeita, Shorts/Curadoria, Ergonomia MCP e Suporte/Release Nativo para Windows 11 (com GPU CUDA/NVENC local)** seguindo estritamente as 5 Microspecs (**P0-1, P0-2, P0-3, P1-1, P2-1**) da especificação acima.

## REGRAS OBRIGATÓRIAS DE EXECUÇÃO

1. **UMA FASE POR VEZ:** Comece EXCLUSIVAMENTE pela **FASE P0-1**. Não leia nem altere arquivos de fases futuras até concluir e validar a fase atual.
2. **LEITURA RESTRITA:** Leia primeiro apenas os arquivos listados em `Arquivos da fase` da fase atual.
3. **ZERO GAMBIARRA & FAIL-CLOSED:**
   - Prefira sempre a implementação mais simples e direta.
   - Nunca silencie exceções (`except Exception: pass`) nem apague/enfraqueça testes existentes.
   - Nunca remova um arquivo sem rodar `rg` em `src/`, `ui/` e `tests/` antes para atualizar imports.
   - Todo caminho usado em filtros FFmpeg (`ass=`, `subtitles=`, `fontsdir=`, `fontfile=`) deve passar por `escape_ffmpeg_filter_path()` (Fase P1-1) para funcionar no Windows (`C\:/...`).
4. **VALIDAÇÃO DETERMINÍSTICA:** Ao final de cada fase, execute exatamente o comando da seção `Validação` e corrija qualquer falha até obter `0 failed`.
5. **PARADA ENTRE FASES:** Ao terminar a fase atual com validação 100% verde, envie um resumo objetivo (arquivos alterados + saída do comando de validação) e **PARE** perguntando se pode avançar para a próxima fase (`P0-2`, `P0-3`, `P1-1`, `P2-1`).

Inicie agora a **FASE P0-1** lendo apenas os arquivos listados na fase e executando os passos 1 a 7.
```
