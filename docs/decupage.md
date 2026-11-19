# Decupagem MCP — fases 1–3

As fases 1–3 entregam a base acústica, ASR/alinhamento/ASUs e a revisão
determinística + LLM. Tudo é executado por steps do catálogo MCP, portanto
`vf_catalog_search` e `vf://docs/steps/{type}` expõem os parâmetros ao modelo
chamador.

## Pipeline

```text
ingest / session.ingest
        ├── audio.events   (YAMNet ou heurística/AST)
        └── audio.vad      (Silero com histerese + RMS 10 ms)
                ↓
        transcribe         (anti-alucinação, local ou worker remoto)
                ↓
        alignment.forced   (WhisperX/stable-ts/faster-whisper/remoto)
                ↓
        speech.asu         (Atomic Speech Units)
                ↓
        decupage.prefilter (grupos fuzzy + quarentena)
                ↓
        decupage.llm       (caller | videoflow | none)
                ↓
        decupage.apply     (decisões → cortes/flags)
```

### `audio.events`

Detecta tosse, pigarro, espirro, fungada, suspiro e transientes. O caminho de
qualidade usa YAMNet ONNX; sem modelo/labels, cai para a heurística existente e
marca o relatório com `engine="heuristic"`.

Parâmetros principais:

| Parâmetro | Default | Uso |
| --- | ---: | --- |
| `threshold` | `0.45` | Score forte para remoção. |
| `low_threshold` | `0.30` | Score fraco aceito quando o ASR está vazio ou incerto. |
| `asr_confidence` | `0.35` | Limite de confiança média das palavras sobrepostas. |
| `min_event_ms` | `150` | Duração mínima do evento. |
| `merge_gap_ms` | `120` | Junta janelas vizinhas do mesmo evento. |
| `use_ast_fallback` | `true` | Usa o tagger AST quando disponível. |

Saídas:

- `work/audio_events.json` — eventos com `start_sample`, `end_sample`, `label`,
  `score`, `action` e `source`.
- `metadata.audio_events` — lista pronta para o próximo estágio.
- `metadata.audio_events_report` — engine, disponibilidade, contagens e motivo
  do fallback.

Modelo:

```bash
export VIDEOWFLOW_YAMNET_MODEL=/models/yamnet/yamnet.onnx
export VIDEOWFLOW_YAMNET_LABELS=/models/yamnet/yamnet_labels.json
```

O class map pode ser JSON (`["Speech", ...]` ou `{"0": "Speech"}`) ou CSV
AudioSet no formato `index,mid,display_name`.

### `audio.vad`

Além dos parâmetros existentes, aceita `neg_threshold` para histerese:

- entra em fala com `speech_threshold`;
- permanece em fala enquanto o score estiver acima de `neg_threshold`;
- fecha a fala abaixo de `neg_threshold`.

O step grava `work/vad_rms.json` com RMS em dBFS a cada 10 ms, janela de 25 ms,
na taxa de áudio do projeto. Esse mapa será usado pelo snap acústico das fases
seguintes.

## Chamada via MCP

```text
vf_exec(action="step", project_id="...", step_id="audio.events",
        params={"threshold": 0.45}, wait=True)
vf_exec(action="step", project_id="...", step_id="audio.vad",
        params={"engine": "auto", "neg_threshold": 0.35}, wait=True)
```

## ASR e ASU

`transcribe` agora expõe `compute_policy` (`auto`, `local`, `remote`,
`remote_only`) e o perfil anti-alucinação:

- `condition_on_previous_text=false`;
- `no_speech_threshold=0.6`;
- `compression_ratio_threshold=2.2`;
- `repetition_penalty=1.1`.

Com `compute_policy=auto`, o step tenta o worker remoto de ASR quando ele está
saudável e configurado; se falhar, volta ao Faster-Whisper local e registra o
warning. `remote_only` falha em vez de degradar silenciosamente.

`alignment.forced` tenta WhisperX sobre o texto existente, depois stable-ts,
depois Faster-Whisper local e, por fim, o ASR remoto. O backend usado fica em
`metadata.forced_alignment.backend`.

`speech.asu` agrupa palavras em ASUs com quebra por pausa (`250 ms`), pontuação
forte (`120 ms`) ou duração máxima (`15 s`). Cada ASU carrega pausas, RMS médio,
probabilidade média, taxa de palavras, eventos acústicos sobrepostos e palavras
indexadas. O artefato fica em `work/decupage/asus.json`.

## Pré-filtro e LLM (Fase 3)

`decupage.prefilter` roda antes de qualquer LLM:

- agrupa ASUs fuzzy por prefixo/token set com lookahead de 45 s;
- atribui `retake_group_id`;
- marca `has_stutter_candidate`;
- coloca ruído isolado e alucinações de baixa confiança em quarentena;
- protege CTAs, preços, links, patrocínio e ofertas.

`decupage.llm` prepara ou executa a revisão semântica:

| `llm_policy` | Comportamento |
| --- | --- |
| `caller` | Não chama modelo. Escreve `work/decupage/llm_request_pass1.json` e deixa `metadata.decupage_llm.status="waiting"`. |
| `videoflow` | Chama o provider LLM configurado e grava as decisões. |
| `none` | Pula a revisão e marca o contrato como `skipped`. |

O request para o chamador contém apenas `asu_id`, texto, pausas, probabilidade,
palavras e flags; **não contém timestamps**. A LLM chamadora deve responder e
submeter as decisões com `decupage.apply`. O resultado do job inclui o campo
`llm` com `required`, `policy`, `status`, `roles`, `calls_planned` e
`calls_made`, além do artefato do contrato.

Exemplo:

```text
vf_exec(action="step", step_id="decupage.prefilter", wait=True)
vf_exec(action="step", step_id="decupage.llm",
        params={"llm_policy": "caller", "mode": "pass1"}, wait=True)
# ler work/decupage/llm_request_pass1.json
vf_exec(action="step", step_id="decupage.apply",
        params={"decisions": [...]}, wait=True)
```

`decupage.apply` valida IDs, ações e índices de palavras, aplica `REMOVE` e
`TRIM_WORDS`, grava cortes em `metadata.decupage_cuts`, flags em
`metadata.decupage_review_flags` e o estado em `work/decupage/state.json`.
Nenhum passo altera a timeline ainda; o snap e o apply da fase seguinte
consomem esses cortes.

## Snap e timeline (Fase 4)

`decupage.snap` transforma os ASUs mantidos em um plano acústico:

- busca o menor RMS em `[start-100ms, start+20ms]` e `[end-20ms, end+130ms]`;
- aplica pré-roll de 70 ms e post-roll de 110 ms;
- não invade eventos de ruído;
- funde micro-gaps abaixo de 180 ms, exceto quando há ruído ou `TRIM_WORDS`;
- quantiza início para baixo e fim para cima na grade exata de FPS;
- planeja crossfade equal-power de 18 ms por emenda;
- marca `needs_broll_or_punch_in` em cortes intra-ASU/retake.

Saídas:

- `work/decupage/plan.json`;
- `work/decupage/report.md`;
- `metadata.decupage_plan`;
- `metrics` com duração original/final, redução, cortes e emendas.

`decupage.timeline` aplica o plano ao `project_state.json`:

- valida `expected_revision` quando `replace_manual=false`;
- gera `video_segments` e `audio_segments` pela grade de frames;
- reconstrói `inactive_segments` com razões `retake`, `noise` e `silence`;
- grava `work/decupage/quarantine.json` com o mapeamento source→timeline;
- adiciona marcadores coloridos em `timeline_meta.json` para os cortes
  recuperáveis (vermelho=retake, laranja=noise, amarelo=review);
- não aplica J/L cuts nem punch-ins automáticos;
- deixa a timeline pronta para `vf_export`/`export.nle`.

```text
vf_exec(action="step", step_id="decupage.snap", wait=True)
vf_exec(action="step", step_id="decupage.timeline",
        params={"expected_revision": 7}, wait=True)
```

## Compute routing (Fase 5)

O worker Windows anuncia novas capabilities:

```text
asr
forced_align
audio_events   (requer modelo YAMNet no worker)
vision_blur
render_nvenc
```

`forced_align` usa o modelo ASR do worker com word timestamps; `vision_blur`
usa OpenCV Laplacian em frames amostrados. `audio.events` continua local por
padrão até o modelo YAMNet ser configurado no worker.

`transcribe` e `alignment.forced` aceitam `compute_policy`:

```text
auto          usa remoto quando saudável, com fallback local
local         nunca usa rede
remote        tenta remoto e aceita fallback local
remote_only   falha se o worker não estiver disponível
```

O preflight de decupagem retorna `compute.stages`:

```text
vf_preflight_plan(project_id, operation="decupage",
                  params={"compute_policy":"auto"})
```

Cada estágio informa `class`, `preferred`, `placement`, `degraded` e `reason`.
Políticas `local`/`local_only` não são marcadas como degradadas; fallback
inesperado do worker é.

## Benchmark

O harness determinístico e o procedimento do golden video estão em
[decupage-benchmark.md](decupage-benchmark.md) e
[qa-evidence/decupage-benchmark.json](qa-evidence/decupage-benchmark.json).

```bash
uv run python scripts/decupage_benchmark.py --self-test --require-thresholds
```

## Limites desta fase

- YAMNet é opcional e roda em CPU local nesta fase.
- O alinhamento remoto usa o ASR do worker como fallback; um handler dedicado
  de forced alignment no worker será adicionado na fase de compute routing.
- `decupage.timeline` aplica o plano ao source primário; o caminho multi-source
  continua usando `session.cull` até o conform multi-source ser fechado.
- A exportação com trilhas V2/A2 de quarentena no FCPXML/OTIO fica para a fase
  de exportação; por enquanto os cortes recuperáveis estão em
  `inactive_segments`, `plan.json`, `quarantine.json`, `report.md` e nos
  marcadores do `timeline_meta.json`.
- `audio.events` continua local até um handler YAMNet ser ativado no worker.
- O wheel do worker precisa ser reconstruído para distribuir as novas
  capabilities.
