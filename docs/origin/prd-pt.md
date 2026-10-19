# Original Portuguese requirements (non-normative)

This file is the historical PRD that started the repository. It is kept so the
origin of the product is auditable. It is **not** the specification.

Normative English spec: [docs/prd.md](../prd.md).

Where this document disagrees with the English spec or the ADRs, the English
spec wins. Known disagreements include float seconds as authoritative time,
CUDA-first defaults, FCPXML as a Premiere import format, Jinja2 as the FCPXML
builder, and storing `api_key` in project state.

---

# DOCUMENTO DE ESPECIFICAÇÃO DE REQUISITOS TÉCNICOS (PRD)

**Projeto:** VideoFlow Core — Headless Pipeline, Rack UI & MCP Server para Pré-Edição Automatizada

**Versão:** 1.0.0

**Perfil de Arquitetura:** Backend FastAPI (Python 3.11+) + MCP Server (JSON-RPC) + UI Rack Modular (Tailwind/Svelte/React) + Motor de Mídia (FFmpeg / Faster-Whisper / Silero-VAD / ONNX / Jinja2)

---

## 1. Visão Geral da Arquitetura

O sistema é um orquestrador de pré-edição de vídeo não-destrutivo. Ele analisa arquivos brutos de gravação, elimina silêncios e gagues/retakes via IA, injeta dinâmicas visuais (zooms, J/L-cuts), gera legendas dinâmicas, extrai cortes verticais (Shorts/Reels) e exporta um arquivo **FCPXML v1.9/1.10** nativo para DaVinci Resolve e Premiere Pro, além de renderizações diretas via FFmpeg.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        INTERFACES DE CONTROLE                          │
│   ┌──────────────────────────────┐  ┌──────────────────────────────┐   │
│   │   Web UI: Rack Sequencial    │  │   Agente LLM / Chat Client   │   │
│   │   (Sliders, Toggles, Cache)  │  │   (Cursor, OpenCode, Claude) │   │
│   └──────────────┬───────────────┘  └──────────────┬───────────────┘   │
└──────────────────┼─────────────────────────────────┼───────────────────┘
                   │ HTTP / WebSocket                │ JSON-RPC (stdio/SSE)
┌──────────────────▼─────────────────────────────────▼───────────────────┐
│                     CAMADA DE ENTRADA & CONTROLE                       │
│   ┌──────────────────────────────┐  ┌──────────────────────────────┐   │
│   │        FastAPI Core          │  │       MCP Server Nativo      │   │
│   └──────────────┬───────────────┘  └──────────────┬───────────────┘   │
│                  └────────────────┬────────────────┘                   │
│                                   ▼                                    │
│                 Pipeline Runner & Cache Controller                     │
│               (Estado Unificado: TimelineProjectState)                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Execução Sequencial / Parcial
┌───────────────────────────────────▼────────────────────────────────────┐
│                  MÓDULOS PLUGÁVEIS (PIPELINE RACK)                     │
│  [01: Ingest] ──► [02: Silero-VAD] ──► [03: Faster-Whisper]            │
│  [04: LLM Retakes] ──► [05: J/L-Cut] ──► [06: Zooms & Pans]           │
│  [07: Vertical Shorts Engine] ──► [08: FCPXML / MP4 Exporter]          │
└────────────────────────────────────────────────────────────────────────┘

```

---

## 2. Estrutura de Dados Central (`TimelineProjectState`)

O pipeline inteiro compartilha e manipula uma única estrutura de dados serializável em JSON, persistida no diretório do projeto (`.videoflow/project_state.json`):

```json
{
  "project_id": "uuid4",
  "media_info": {
    "source_path": "/path/to/raw_video.mp4",
    "duration_sec": 720.45,
    "fps": 30.0,
    "width": 3840,
    "height": 2160,
    "audio_sample_rate": 48000
  },
  "modules_config": { ... },
  "cache_hashes": { ... },
  "vad_intervals": [ [1.2, 5.8], [6.4, 12.1] ],
  "transcript": [
    {
      "id": 1,
      "start": 1.25,
      "end": 5.75,
      "text": "Olá pessoal, bem-vindos a mais um vídeo.",
      "words": [
        {"word": "Olá", "start": 1.25, "end": 1.55, "probability": 0.98},
        {"word": "pessoal,", "start": 1.58, "end": 2.10, "probability": 0.95}
      ]
    }
  ],
  "retake_culls": [ 4, 5 ],
  "timeline_cuts": [
    {
      "clip_id": "c1",
      "source_in": 1.15,
      "source_out": 5.85,
      "timeline_in": 0.0,
      "timeline_out": 4.70,
      "audio_lead_in": 0.20,
      "audio_lead_out": 0.0,
      "transform": { "scale": 1.15, "pos_x": 0.0, "pos_y": 0.0, "type": "punch_in" }
    }
  ],
  "vertical_clips": [
    {
      "title": "A sacada sobre IA",
      "start_sec": 120.5,
      "end_sec": 165.2,
      "crop_focus_x": 0.5
    }
  ]
}

```

---

## 3. Especificação Funcional dos Módulos (Plugins do Rack)

### Módulo 01: Ingest & Normalização (FFmpeg)

* **Responsabilidade:** Validar conformidade do vídeo. Arquivos com taxa de quadros variável (VFR) geram dessincronia temporal entre o Whisper e a timeline.
* **Parâmetros de Configuração:**
* `force_cfr` (bool, default: `true`): Converte VFR para CFR (Constant Frame Rate).
* `extract_audio_pcm` (bool, default: `true`): Extrai áudio WAV 16kHz mono para alimentar VAD e Whisper sem decodificação redundante de vídeo.
* `generate_proxy` (bool, default: `false`): Cria proxy intra-frame leve (ProRes Proxy ou H.264 All-Intra 720p).



### Módulo 02: Detecção de Voz e Silêncio (Silero-VAD)

* **Biblioteca:** `silero-vad` via **ONNX Runtime** (execução em CUDA ou CPU multithreaded).
* **Lógica:** Identifica probabilidades de fala humana a cada bloco de 30ms.
* **Parâmetros de Configuração:**
* `speech_threshold` (float: 0.1 a 0.9, default: `0.5`): Sensibilidade de detecção de fala.
* `min_silence_duration_ms` (int, default: `400`): Duração mínima de pausa para justificar um corte. Pausas menores que isso são mantidas para preservar a respiração natural.
* `speech_pad_before_ms` (int, default: `120`): Margem de segurança adicionada antes do início da fala (evita decepar consoantes oclusivas como P, B, T).
* `speech_pad_after_ms` (int, default: `150`): Margem de segurança retida após o término da fala.
* `keep_handles_ms` (int, default: `200`): Reserva oculta de áudio/vídeo (*handles*) para viabilizar transições de J-Cut e morph cut no NLE.



### Módulo 03: Transcrição Multilíngue e Timestamps (Faster-Whisper)

* **Biblioteca:** `faster-whisper` (CTranslate2).
* **Lógica:** Gera a transcrição com marcações temporais no nível de palavras (*word-level timestamps*) usando Dynamic Time Warping (DTW).
* **Parâmetros de Configuração:**
* `model_size` (enum: `tiny`, `base`, `small`, `medium`, `large-v3`, default: `large-v3`).
* `language` (enum: `pt`, `it`, `en`, `es`, `auto`, default: `pt`).
* `device` (enum: `cuda`, `cpu`, default: `cuda`).
* `compute_type` (enum: `float16`, `int8`, `float32`, default: `float16`).
* `vad_filter` (bool, default: `false`): Desativado no Whisper se o Módulo 02 já estiver ativo, para evitar dupla filtragem conflitante.



### Módulo 04: Limpeza de Retakes e Repetições (LLM Engine)

* **Lógica:** Identifica frases iniciadas e abortadas, gagues, pigarreios ou múltiplas tentativas de leitura do mesmo parágrafo, mantendo estritamente a última tentativa válida.
* **Conector Universal de LLM:**
* `provider`: `ollama` | `openai_compatible` (Groq, Together, LM Studio, Anthropic via bridge).
* `base_url`: Endpoint de API (ex: `http://localhost:11434/v1` para Ollama ou `[https://api.groq.com/openai/v1](https://api.groq.com/openai/v1)`).
* `api_key`: String (vazia para Ollama/LM Studio local).
* `model_name`: Nome do modelo (ex: `qwen2.5:7b-instruct`, `llama-3.3-70b-versatile`).


* **Parâmetros do Módulo:**
* `strictness` (enum: `conservative`, `balanced`, `aggressive`): Define se o modelo descarta apenas repetições óbvias ou também frases redundantes.
* `context_window_sentences` (int, default: `15`): Tamanho dos blocos de contexto enviados à LLM para evitar estourar a janela ou perder referências cruzadas.
* `retake_strategy` (enum: `keep_last`, `keep_best`, default: `keep_last`).


* **Protocolo de Retorno Estruturado:** A LLM recebe sentenças indexadas por ID e **deve** responder exclusivamente um JSON Schema restrito:
```json
{ "discard_sentence_ids": [3, 4, 12], "reasoning": "Tentativas falhas antes da versão definitiva no ID 5" }

```



### Módulo 05: Transições de Áudio Automatizadas (J-Cut / L-Cut Engine)

* **Lógica:** Transforma o corte seco em corte dinâmico deslocando as pontas das trilhas de áudio sobre o vídeo do clipe vizinho.
* **Parâmetros de Configuração:**
* `enable_j_cuts` (bool, default: `true`): O áudio do clipe seguinte entra antes da transição do vídeo.
* `enable_l_cuts` (bool, default: `false`): O áudio do clipe anterior continua por baixo do vídeo seguinte.
* `offset_ms` (int, range: 100-500, default: `200`): Duração do avanço do áudio.
* `audio_crossfade_ms` (int, range: 10-50, default: `20`): Micro-crossfade com curva logarítmica para neutralizar ruídos elétricos ou estouros acústicos (*pops/clicks*).
* `handle_check` (bool, default: `true`): Impede a criação de J-Cut caso a margem do corte anterior seja menor que o `offset_ms` solicitado (evita sobreposição de palavras).



### Módulo 06: Enquadramento Dinâmico & Zooms (Punch-In / Pan)

* **Lógica:** Alternância automatizada de escala e posição entre os cortes para criar dinamismo visual e mascarar os *jump cuts* sem necessitar de keyframes manuais.
* **Parâmetros de Configuração:**
* `mode` (enum: `alternate_cuts`, `topic_change`, `manual_rules`, default: `alternate_cuts`).
* `punch_in_scale` (float: 1.05 a 1.30, default: `1.15`): Taxa de aproximação digital.
* `anchor_point` (enum: `center`, `upper_third`, `face_detect`, default: `upper_third`): Centro de rotação/zoom.
* `progressive_zoom` (bool, default: `false`): Transforma o punch-in estático em zoom contínuo lento (Slow Zoom-In / Zoom-Out) ao longo da duração do take.
* `pan_direction` (enum: `none`, `left_to_right`, `right_to_left`, default: `none`): Deslocamento suave no eixo horizontal para vídeos 4K em timelines 1080p.



### Módulo 07: Extrator de Cortes Verticais (Shorts / Reels 9:16)

* **Lógica:** Análise semântica via LLM sobre a transcrição total para encontrar trechos autossuficientes, dinâmicos e com potencial de retenção (gancho, desenvolvimento e conclusão), gerando clipes 1080x1920.
* **Parâmetros de Configuração:**
* `target_duration_min_sec` (int, default: `30`).
* `target_duration_max_sec` (int, default: `60`).
* `max_clips_to_generate` (int, default: `3`).
* `reframe_mode` (enum: `center_crop_9_16`, `auto_face_tracking_yolo`, default: `center_crop_9_16`).
* `burn_subtitles` (bool, default: `true`): Aplica legendas ativas estilo karaokê embutidas no clipe vertical.
* `subtitles_preset` (enum: `tiktok_bold`, `minimalist_box`, `highlight_word`, default: `tiktok_bold`).
* `export_format` (enum: `fcpxml_timeline`, `standalone_mp4`, `both`, default: `both`).



### Módulo 08: Exportação e Compilação da Timeline

* **Formatos Suportados:**
1. **FCPXML (v1.9 / v1.10):** Gera a timeline do projeto com faixas de áudio e vídeo desvinculadas (para os J-Cuts) e elementos `<adjust-transform scale="1.15 1.15"/>` aplicados nos cortes com zoom. Compatível nativamente com DaVinci Resolve Studio e Premiere Pro.
2. **OpenTimelineIO (.otio):** Padrão aberto universal para intercâmbio de NLEs.
3. **Render Direto (FFmpeg MP4):** Para clipes de shorts ou prévias rápidas sem abrir o NLE.



---

## 4. Arquitetura da Interface Visual: Pipeline Rack UI

A interface deve adotar o paradigma de **Rack de Plugins Sequencial Vertical** (inspiração: Ableton Live / Audio Inserts / n8n vertical execution chain).

### Componentes Visuais do Rack

1. **Header Global:**
* Seletor de Arquivo de Mídia (Drag-and-Drop de vídeo).
* Barra de Progresso Global do Pipeline (com indicação do módulo em execução e ETA).
* Dropdown de **Presets Globais** (`Salvar Preset`, `Carregar Preset`, ex: "YouTube Falado Padrão", "Shorts Agressivo", "Curso/Aula Limpo").
* Botão Master: `Executar Pipeline Completo`.


2. **Lista Vertical de Cards (Plugins):**
Cada módulo é um card vertical expansível que apresenta:
* **Toggle Switch (On/Off):** Ativa ou ignora o módulo na esteira.
* **Indicador de Status / Cache:**
* 🟢 *Cached* (Parâmetros inalterados; execução instantânea).
* 🟡 *Dirty* (Parâmetros alterados; necessita reprocessamento).
* 🔵 *Running* (Processando no momento via SSE/WebSocket).
* ⚪ *Bypassed* (Módulo desativado).


* **Botão de Execução Local:** `Rodar Apenas Este Bloco`.
* **Corpo Expansível (Accordion):** Sliders numéricos, switches, campos de texto e seletores drop-down para cada parâmetro documentado no Capítulo 3.


3. **Painel de Inspeção e Refinamento:**
* Visualizador do texto transcrito com marcações coloridas: verde (mantido), vermelho riscado (retake descartado), cinza (silêncio podado).
* Permite ao usuário clicar em uma palavra para ouvir ou alternar manualmente o estado de exclusão antes de mandar compilar o FCPXML.



---

## 5. Especificação Técnica do Servidor MCP (Model Context Protocol)

O servidor MCP expõe as capacidades de edição do backend para qualquer agente externo (Claude Desktop, Cursor, OpenCode, Hermes, scripts em Python). O transporte opera via `stdio` (linha de comando local) ou `SSE` (Server-Sent Events via FastAPI).

### 5.1 Tools Expostas pelo Servidor MCP

| Nome da Tool | Descrição Técnica | Parâmetros Principais | Retorno |
| --- | --- | --- | --- |
| `videoflow_load_media` | Registra e extrai metadados do vídeo bruto. | `file_path: string` | Metadados técnicos (fps, duração, resolução). |
| `videoflow_run_vad` | Executa o Silero-VAD para fatiar silêncios. | `speech_threshold: float`, `min_silence_duration_ms: int`, `speech_pad_before_ms: int` | Total de silêncios encontrados e segundos podados. |
| `videoflow_transcribe` | Roda transcrição Faster-Whisper. | `model: string`, `language: string` | Número de sentenças e palavras identificadas. |
| `videoflow_get_transcript` | Retorna o texto transcrito estruturado. | `include_word_timestamps: bool` | JSON com array de sentenças, IDs e timestamps. |
| `videoflow_cull_retakes` | Aplica exclusão de repetições por regras ou IDs. | `discard_sentence_ids: list[int]`, `manual_word_indices: list[int]` | Nova duração estimada do corte bruto. |
| `videoflow_configure_zooms` | Define a cadência de enquadramento. | `mode: string`, `scale: float`, `anchor: string` | Contagem de trechos modificados com zoom. |
| `videoflow_apply_jcuts` | Injeta J-Cuts e micro-fades de áudio. | `offset_ms: int`, `crossfade_ms: int` | Quantidade de J-cuts criados com sucesso. |
| `videoflow_generate_shorts` | Identifica e extrai clipes verticais 9:16. | `min_duration: int`, `max_duration: int`, `count: int`, `subtitles: bool` | Lista de clipes verticais gerados com links de preview. |
| `videoflow_export_fcpxml` | Compila e salva o arquivo de timeline final. | `output_path: string`, `target_nle: string` | Caminho do arquivo `.fcpxml` pronto para importação. |
| `videoflow_run_pipeline` | Executa a esteira completa ponta a ponta. | `preset_name: string` (opcional), `overrides: dict` (opcional) | Status do projeto e paths de todos os artefatos gerados. |

### 5.2 Resources Expostos pelo MCP

* `videoflow://project/state`: Retorna o JSON completo do estado atual do projeto.
* `videoflow://project/transcript`: Retorna o arquivo de texto puro ou SRT gerado no projeto.
* `videoflow://presets/list`: Retorna todos os presets de edição salvos na máquina.

---

## 6. Sistema de Cache Inteligente e Execução Parcial

Para eliminar reprocessamentos caros de modelos neurais, cada módulo calcula um hash SHA-256 baseado em:


$$\text{Hash}_{\text{módulo}} = \text{SHA256}(\text{CaminhoDoArquivo} + \text{ModificaçãoTimestamp} + \text{ParametrosDoModulo} + \text{HashDoModuloAnterior})$$

* Se o usuário alterar apenas o parâmetro de `punch_in_scale` no Módulo 06 e rodar a execução, o pipeline:
1. Verifica os hashes dos Módulos 01 a 05 $\rightarrow$ **Idênticos** $\rightarrow$ Carrega os dados diretamente da memória/disco (`.cache/`).
2. Executa exclusivamente o Módulo 06 e compila o FCPXML no Módulo 08.
3. Tempo de execução: **menor que 1 segundo** (em vez de esperar minutos por uma nova transcrição).



---

## 7. Critérios de Aceite e Testes de Qualidade

1. **Precisão de Áudio:** O arquivo FCPXML gerado importado no DaVinci Resolve não pode apresentar nenhum estalo de áudio (*pop/click* audível) na junção de clipes podados.
2. **Sincronismo Labial:** A sincronia entre voz e vídeo ao longo de uma gravação de 60 minutos não pode desviar mais de 1 quadro (tolerância máxima de $\pm 33\text{ms}$).
3. **Determinismo da LLM:** O filtro de retakes nunca deve cortar a versão final de uma frase quando o locutor tiver cometido repetições múltiplas; a frase mantida deve ser categoricamente a última iteração.
4. **Autonomia do Agente MCP:** Um agente externo conectado via MCP deve ser capaz de receber um caminho de vídeo cru e, usando estritamente as tools expostas, entregar um arquivo FCPXML funcional e 3 shorts verticais sem intervenção humana no teclado.
