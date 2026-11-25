# Changelog

## [4.7.0] - 2026-11-25

Edição inteligente guiada pelo OpenCode: decupagem assistida, mapa editorial,
contratos MCP completos, áudio idempotente, stock filtrado e catálogo enxuto.

### Added — decupagem assistida

- `vf_decupage(action="review_packet")` devolve 100% das sentenças com
  `[DISCARDED]`/`[SUSPECT_RETAKE]` e pares de retake para o OpenCode decidir.
- `vf_transcript(action="editorial_map")` retorna blocos de 15–30 s da timeline
  editada com fala, `layout_type`, `protected_from_broll` e `keyframe_path`.
- Guarda fonética de **75 ms antes / 115 ms depois** impede corte de palavras
  mantidas com `probability >= 0.40`, sem atravessar ruído ou cortes
  deliberados.
- `session.cull` restaura a timeline original e emite `cull_guard_restored_all`
  em vez de remover todos os clipes.
- Pacing `tight` em `260/260/75/115/650` e `balanced` em `380/400/90/130/900`,
  com `min_cut_gap_ms` explícito.
- Punch-in padrão `1.06`, teto `1.08`; repetições de conteúdo em janela de 1.2 s.

### Added — MCP e licenças

- `wait=True` retorna o job terminal no topo do payload.
- `vf_timeline(action="time_map")` e `page_size` até 500.
- `vf_transcript` corrige a paginação para 104/104 sentenças e expõe
  `query`/`editorial_map`.
- `approve_license` encontra assets só em `assets/`/`media/`, grava no ledger e
  desbloqueia `apply_beatmap` imediatamente.
- `vf_export(action="mp4")`, `qa_mode="skip"` e `valid_actions` nas docstrings.
- Prompt MCP `videoflow_full_test` e resource `vf://tests/full-540p` entregam o
  roteiro completo do teste rápido ao OpenCode.

### Fixed — áudio

- `audio.finalize` usa `audio/dialogue_timeline.wav`, nunca `final.wav` como
  entrada.
- Escrita atômica em `.final_mix.tmp.wav` → `final_mix.wav`/`final.wav`.
- Loop automático de música com fade-out de 2.5 s.
- SFX de `beat_map.json`/`audio/beatmap.json`/`audio/sfx-plan.json` mixados por
  timestamp e ganho; falha explícita se nenhum evento entrar.

### Changed — stock, curadoria e catálogo

- Stock keyless rejeita vídeos `>120 s`, `>80 MB` ou relevância `<0.35`, com
  fallback de query e provider.
- Auto-trim de stock longo/4K para `8 s` em `<=1080p`.
- Ken Burns de imagens em `1.00 → 1.06`, com pans em `1.06`.
- Curadoria aceita `start_sec`, `end_sec`, `spoken_context` e `note`, exibidos
  no card da UI.
- Catálogo reduzido a **6 estilos oficiais** e **5 workflows** com nós MCP
  válidos; `AGENTS.md` em 74 linhas.

### Validation

- `ruff check src packages tests scripts`: limpo.
- `pytest -q`: 3127 passed, 1 skipped, 1 xfailed; cobertura 96,72%.
- `pytest -m media`: 29 passed, 2 skipped.
- UI: `svelte-check` 0 erros/0 warnings, 55 testes, build concluído.
- `videoflow_full_test` e `vf://tests/full-540p` verificados no MCP.

## [4.6.0] - 2026-11-24

Correções de causa-raiz nos 44 sintomas reportados: NVENC e PCM, duração do
export, curadoria visual, decupagem agressiva, contratos MCP, paths/clones e
inicialização 1-clique no Windows.

### Fixed — render, áudio e overlays

- Flags NVENC passam a vir exclusivamente de `probe_nvenc()`, sem `-spatial_aq`
  hardcoded; `fullscreen` entra como âncora válida de overlay.
- `domains/audio/pcm_io.py` é o leitor único de WAV 16/24/32-bit com decodificação
  alinhada a frames; silêncio, alinhamento, análise não-fala e finalização de
  áudio usam o mesmo leitor.
- `audio.finalize` lê `loudnorm` de stdout ou stderr, expõe ducking/music gain em
  dB e resolve `audio_source` de mix/final/master no render.

### Fixed — export, NLE e QA

- Render segmentado preserva a duração da timeline no fps de saída, sem
  sobrescrever 60 fps por 30 fps.
- `resolve_render_profile()` centraliza precedência de preview/draft/fps e
  `draft_scale` chega ao `vf_export` e ao delivery bundle.
- `qa_mode` aceita `none`/`off`, `review.json` é escrito em `needs_review` e os
  nomes canônicos de NLE são resolvidos em `exports/` e na raiz do projeto.

### Fixed — curadoria e mídia

- Cards de curadoria resolvem e validam `local_path`, geram poster de vídeo,
  preview MP3 leve para WAV 24-bit/pesado e expõem `media_url`/`poster_url`.
- Streaming HTTP com MIME explícito e `Range`; `scene_id` e `local_path` são
  preservados nas decisões.
- UI renderiza cards de imagem, vídeo, áudio e estilo com retry inline.

### Changed — decupagem

- `vf_decupage(action="run_full")` executa
  `ingest → audio.vad → transcribe → speech.asu → speech.editorial_clean →
  retakes.cull → decupage.snap → edit.timeline`.
- `edit.timeline` aceita `TimelineParams` de pacing, consome spans seguros do
  snap, preserva overlays e exige `reset=True` para sobrescrever edição manual.
- Perfil `tight` passa a `min_silence_ms=180`, `max_pause_ms=200`,
  `pad_before_ms=55`, `pad_after_ms=80` e `qa_dead_air_ms=500`.
- Limpeza remove palavras repetidas em janela de 1.5 s, fragmentos desconexos de
  até 3 palavras e candidatos semânticos fracos.
- Segundo passe e agrupamento de retakes distantes ativos por padrão com
  `min_similarity=0.52` e `min_prefix_content_words=2`.
- Beatmap preenche `keep_ranges`/`remove_ranges` e usa `time_basis="source"`
  quando há ranges.

### Fixed — contratos MCP, paths e clones

- Toda ação desconhecida em `vf_project`, `vf_timeline`, `vf_ingest`, `vf_media`,
  `vf_audio`, `vf_vision`, `vf_assets`, `vf_font`, `vf_job` e `vf_exec` retorna
  `ok: False`, `error_code: "unknown_action"` e `valid_actions`.
- `vf_audio(action="music")` aceita `music_path`; `vf_media(action="search")` é
  alias de busca stock/keyless; `vf_ingest(action="probe")` retorna metadados do
  `ffprobe`.
- Instalação/remoção de modelos invalida o cache de capability e o próximo
  `transcribe` enxerga o modelo sem restart.
- Workspace e `project_dir` nunca produzem `projects/projects/<slug>`.
- Clones criam `demo-copy`, `demo-copy-2`, … automaticamente, hardlinkam `work`
  e `assets`, reescrevem caminhos internos e não quebram o projeto original.
- Vídeo keyless cai em Wikimedia Commons (`filetype:video`) e Internet Archive
  (`mediatype:movies`) sem Pexels/Pixabay; SFX sem Freesound/VF_SFX_DIR usa o
  sintetizador procedural e grava WAV real em `assets/sfx/`.

### Added — inicialização 1-clique

- `videoflow`/`videoflow.exe` sem subcomando abre o tray com navegador ou sobe
  `serve` headless quando não há display.
- `bootstrap_runtime` baixa Silero VAD e Faster-Whisper small em uma única thread
  daemon, registra progresso em `jobs` com `origin="bootstrap"` e falha offline
  sem derrubar UI/MCP.
- `--no-auto-download` (e `VIDEOWFLOW_NO_AUTO_DOWNLOAD=1`) desativam downloads.
- `serve` e o tray escolhem a próxima porta livre com `pick_available_port(...,
  span=100)`, validam bind e conexão (incluindo `SO_EXCLUSIVEADDRUSE` e
  `netstat` no Windows), gravam `active_server.json` com a porta real e nunca
  abortam por porta ocupada.
- `videoflow restart` inicia processo destacado, encerra o PID antigo com
  timeout rígido de 5 s e retorna após `/health` em até 15 s.
- Spec PyInstaller inclui `pystray._win32`, `PIL.Image`, `PIL.ImageDraw`,
  `bootstrap_runtime` e `pcm_io`; o smoke Windows ocupa a porta, valida o
  fallback, `/`, `/api/v1/curation/boards` e o download desativado.

### Validation

- `ruff check src packages tests scripts`: limpo.
- `pytest -q`: 3092 passed, 1 skipped, 1 xfailed; cobertura 96,79%.
- `pytest -m media`: 29 passed, 2 skipped.
- Fase P2-1: 64 passed.
- UI: `svelte-check` 0 erros/0 warnings, 55 testes, build concluído.

## [4.5.0] - 2026-11-24

Windows 11 nativo, decupagem agressiva, curadoria cross-process, preview
ultra-rápido e release unificado.

### Added — decupagem e áudio

- Perfis `tight`, `balanced` e `relaxed` com silêncio, pausa, pads e
  `qa_dead_air_ms` explícitos; overrides por tool.
- Agrupamento transitivo Union-Find de 2 a N regravações distantes em janela de
  25 sentenças / 420 s, com guardas de números, ordinais, preços, URLs e fatos
  únicos.
- Segundo passe sobre sentenças sobreviventes e teto de descarte em `0.75`.
- `TARGET_LUFS=-16.0`, `target_lufs` explícito com precedência e `audio.finalize`
  sobre a timeline editada; auto-finalize no delivery.
- `audio_source="mix"` por padrão nos exports.

### Added — preview e render

- `mode="preview"` em `vf_export`, `export.video`, `render_master` e delivery
  bundle: 540p/30 fps, NVENC `p1`/CQ28 ou x264 `ultrafast`/CRF30, AAC 128k,
  QA off e `preview_fast.mp4` sem tocar em `youtube_master.mp4`.
- Macro-blocos segmentados renderizados em paralelo, cache por encoder/modo/
  escala/filter hash e fallback runtime NVENC → x264 com `degraded=true`.

### Added — projetos, jobs e curadoria

- Projetos persistidos em SQLite com leitura direta entre processos e resolução
  por `project_id`, `slug` ou nome do diretório.
- Jobs MCP/API visíveis em tempo real na UI via SQLite WAL, incluindo
  `origin`, `pid` e recuperação de worker interrompido.
- Curadoria cross-process com board na porta real do processo ativo.
- Entrega consolidada em `VideoFlow_Output/{videos,exports,shorts,scenes}`.

### Added — MCP, Styles e Workflows

- Bundle JSON único para exportar/importar todos os styles e workflows com
  validação atômica, BOM UTF-8, IDs seguros e rejeição `422`.
- `pacing_profile`, `max_pause_ms`, pads e `second_pass` expostos em
  `vf_decupage`.
- `feature_matrix` no `doctor` para FFmpeg, filtro, CUDA, NVENC, ASR, Silero,
  YAMNet, OpenCV, MediaPipe, scene detection e tray.

### Added — Windows e release

- Tray, porta dinâmica com `active_server.json`, GPU local no router/UI e
  caminhos Windows nativos.
- FFmpeg 7/8/9 com script de filtro detectado, BOM de legenda, burn validado e
  tolerância AAC.
- `scripts/certify_windows_nvidia.py` com doctor, porta ocupada, UI, curadoria
  cross-process, ASR, decupagem e exports preview/final.
- CI em push/PR com job Windows; release com gate obrigatório, Linux `tar.zst`,
  CUDA zip, worker kit, SBOM, `SHA256SUMS` e `manifest.json` unificados.
- Smoke Windows cobre `/`, asset JS e um job sintético ponta a ponta.

### Validation

- `ruff check src packages tests scripts`: limpo.
- `pytest -q`: 3040 passed, 1 skipped, 1 xfailed; cobertura 96,79%.
- `pytest -m media`: 29 passed, 2 skipped.
- UI: `svelte-check` 0 erros/0 warnings, 55 testes, build concluído.
- `certify_windows_nvidia.py --help`: exit 0.

## [4.4.0] - 2026-11-23

Decupagem perfeita, Shorts publicáveis, ergonomia MCP e execução nativa no
Windows 11 com CUDA/NVENC local.

### Added — decupagem

- União `VAD ∪ ASR` em `build_safe_speech_spans()`: palavras transcritas com
  `probability >= 0.45` nunca são apagadas como silêncio.
- Guarda de cortes longos: todo vão removido acima de 15s aparece em
  `decupage/report.json` com RMS, contagem de palavras e `requires_review`.
- Piso de pads de 90ms/150ms após o snap acústico, quantizado em frames.
- `vf_decupage(action="run_full")` executa a ordem canônica
  `audio.vad → transcribe → speech.editorial_clean → retakes.cull →
  decupage.snap → edit.timeline`.
- `retakes.cull` sem VAD retorna `missing_prerequisite` com `fix_hint`.

### Added — Shorts e curadoria

- `shorts.select` honra `count`, calcula `speech_ratio` na janela editada e
  prefere `TALKING_HEAD` a `SCREEN_SHARE_FULL` em crops 9:16.
- `burn_subtitles=True` queima o `.ass` no MP4 e mantém o sidecar.
- `time_basis` `edited`/`source` com alias `timeline` e erro explícito fora da
  timeline.
- Clipes abaixo de 3s falham com `invalid_short_duration` antes do FFmpeg.
- Board de curadoria aceita `short` e `cut_review`, com player de vídeo.

### Changed — áudio e entrega

- `TARGET_LUFS=-16.0`, `LOUDNORM_TARGET_TP_DB=-2.0` e
  `QA_MAX_TRUE_PEAK_DBTP=-1.0` em uma única constante.
- `audio.finalize` roda automaticamente quando o export precisa do mix e
  `final_mix.wav` ainda não existe.
- Entrega sempre em `VideoFlow_Output/{project_slug}/{categoria}`.

### Changed — MCP

- `vf_style` entra no perfil `core`: **18 core / 22 full**.
- `vf_project` aceita `create`/`new`, `output` opcional em
  `$VF_WORKSPACE_ROOT/projects/{slug}` e retorna `project_id` + `uuid`.
- Slugs, UUIDs e nomes de projeto são resolvidos no boundary de **todas** as
  tools e recursos.
- `vf_run` aceita `step_params` e distribui `params` plano apenas para os campos
  válidos de cada step; chaves desconhecidas retornam `invalid_params`.
- `vf_jobs(action="wait")` retorna `{ok, job_id, status, result, error,
  artifacts}` e nunca `{}`.
- `ValidationError` inclui `expected_fields` e `fix_hint` com os campos
  esperados.
- `vf_export` sempre retorna payload estruturado.

### Added — Windows nativo e GPU local

- Escape único `escape_ffmpeg_filter_path()` para `C\:/...`, usado em `ass=`,
  `subtitles=`, `fontsdir=`, `fontfile=` e `lut3d=`.
- Fontes nativas de `%WINDIR%\Fonts`, sem depender de `fc-match`.
- Serviços no Windows usam PID file, `netstat`/`tasklist`, `ctypes` e
  `taskkill`, sem `/proc`, `killpg` ou `resource`.
- Render gate usa `msvcrt`/`fcntl` via `FileLock` compartilhado.
- Detecção automática de CUDA local via CTranslate2/`nvidia-smi`; Faster-Whisper
  usa `float16` e FFmpeg usa `h264_nvenc` com `yuv420p` (sem NVDEC em 10-bit).
- `doctor` reporta `local_gpu`, `nvenc` e fontes.

### Added — release Windows

- Bundle `onedir` + onefile opcional, zip stored rápido e launcher
  `VideoFlow.cmd`.
- `hiddenimports` de curadoria, `vf_shared` e lock compartilhado.
- `scripts/smoke_windows.py` valida `version`, `doctor`, `mcp --profile core
  --list-tools` e `serve` (`/health` e `/api/v1/curation/boards`) com `PATH`
  limpo, encerrando o servidor em `finally`.
- Workflow Windows roda o smoke e publica o zip CUDA como artifact.

### Validation

- `ruff check src packages tests scripts`: limpo.
- `pytest -q`: 2960 passed, 1 skipped, 1 xfailed; cobertura 96,78%.
- `pytest -m media`: 29 passed, 2 skipped.
- UI: `svelte-check` 0 erros/0 warnings, 53 testes, build concluído.
- `scripts/smoke_windows.py --help` e execução real do smoke: OK.

## [4.3.1] - 2026-11-23

Correção do portable Windows e publicação do build CUDA com Whisper.

### Fixed — Windows

- `fcntl` removido do caminho de inicialização; `project_lock` e o lock de
  instância agora usam `fcntl` no POSIX e `msvcrt` no Windows.
- `resource` deixou de ser importado obrigatoriamente; `peak_rss_mb` retorna
  `null` quando não há `resource`.
- Encerramento de processos usa `taskkill`/`Popen.terminate` no Windows e
  `os.killpg` no POSIX, cobrindo `stop`, `cleanup`, tray, FFmpeg e serviços.
- Descoberta de serviços no Windows via `netstat -ano` e `tasklist`, incluindo
  PID dono da porta e `status` com serviço encontrado.
- `stop` e `tray` conseguem encerrar uma instância antiga que esteja segurando a
  porta 8765.
- CI Windows agora inicia `serve --mcp-only`, consulta `/health`, executa
  `status` e `stop`; o build falha se o servidor não subir.

### Added — Windows CUDA ASR

- Novo build `VideoFlow-<versao>-windows-x64-cuda.zip` com Faster-Whisper,
  CTranslate2, cuBLAS, cuDNN, CUDA Runtime e NVRTC.
- Modelo `faster-whisper-large-v3-turbo` fora do executável, baixado no primeiro
  uso pelo `VideoFlow.cmd` em `videoflow-data/models`.
- Modelo com revisão fixa do Hugging Face e SHA-256 do `model.bin`.
- Default CUDA `int8_float16`, com override por
  `VIDEOWFLOW_ASR_DEVICE`/`VIDEOWFLOW_ASR_COMPUTE_TYPE`.
- `doctor` reporta `cuda.build`, `cuda.devices`, modelo ASR e runtime.

### Validation

- `ruff check src packages tests scripts` limpo.
- `pytest -q`: 2.911 testes verdes, 1 skipped, 1 xfailed; cobertura 96,8%.
- `pytest -m media`: 29 passed, 2 skipped.
- Windows CI: `version`, `doctor`, `models list`, `mcp --help`, `serve`,
  `/health`, `status` e `stop`.

## [4.3.0] - 2026-11-23

Release MCP-First: curadoria visual em dois turnos, offload total para o Worker
Windows e remoção dos subsistemas fora do escopo de edição.

### Added — curadoria visual

- Board persistente em `curation/board.json` e `curation/decisions.json`, com
  validação de itens, rejeição de duplicatas e auto-seleção determinística por
  categoria e cena.
- Tool `vf_curation` (`publish`, `read`, `auto_select`) no perfil MCP `core`,
  com retorno imediato de `board_url` e `_next_step`.
- API REST `/api/v1/curation/*`, incluindo mídia com validação por
  `resolve_allowed` e suporte a `Range`.
- Tela **Curation** com player, seleção de estilo, música, SFX e B-roll, botão
  **IA escolhe** e o modal local **Needs you**.

### Added — offload total

- `HEAD /artifacts/{sha256}` no Worker Windows e cache de upload por conteúdo;
  o mesmo arquivo não trafega duas vezes.
- Handlers remotos `ingest_pcm`, `audio_finalize` e `shorts_render` com NVENC e
  fallback FFmpeg no Windows.
- Capabilities pesadas são forçadas no Worker saudável, ignorando fila, VRAM e
  utilização. `compute_policy="remote"` segue fail-closed; fallback local só com
  `allow_slow_cpu_fallback=True` e `degraded=true` explícito.
- Probe de `/health` em 1.5 s e `worker_source` (`settings`, `mdns`, `env`).

### Changed — MCP e OpenCode

- Perfis estritos: `core` com 17 tools (`vf_jobs` + `vf_curation`) e `full` com
  22.
- Toda resposta MCP bem-sucedida inclui `_next_step`; listas acima de 30 itens
  são truncadas com `total_count` e `next_offset`, exceto `capabilities`.
- Quatro alvos de exportação explícitos: `mp4`, `resolve`, `premiere` e
  `kdenlive`; FX avançados ficam opt-in no perfil `full`.
- Template `AGENTS.md` com 80 linhas e workflows com modos `curation` e
  `autonomous`.

### Changed — UI

- Navegação reduzida a três telas: **Curation**, **Jobs** e **Setup**.
- Painéis obsoletos removidos; configuração, GPU, estilos e bootstrap do
  OpenCode consolidados em Setup.
- HITL local preservado em Jobs, incluindo aprovações, perguntas, arquivos e
  respostas.

### Removed

- Publishing/webhooks, plugins e sandbox, live source, pesquisa web, canais
  externos de HITL (Slack, e-mail IMAP e Signal) e receitas legadas lâmera,
  OpusClip, Full AI Editor e Synthetic.
- Rotas, telas, scripts e documentação histórica correspondentes.
- `assert_public_url` foi preservado em `application/url_safety.py`; analytics
  e avaliação de experimentos continuam disponíveis.

### Fixed

- Favoritos padrão apontam para receitas existentes (`deepseek_full_edit`,
  `autonomous_studio_master`, `footage_intelligence_edit`).
- Cliente da UI não chama mais rotas removidas de canais HITL.
- Links e referências a módulos, receitas e docs removidos foram eliminados.

### Performance

- Manifesto de capabilities com cache curto e invalidação em mudanças de GPU,
  evitando um probe de descoberta a cada chamada.
- Leitura de JSON compartilhada em steps de motion, storyboard, cenas e
  entidades, reduzindo helpers duplicados.

### Validation

- `ruff check src packages tests scripts` limpo.
- `pytest -q`: 2.905 testes verdes, 1 skipped, 1 xfailed; cobertura 96,8%.
- `pytest -m media`: 29 passed, 2 skipped.
- Svelte check sem erros; Vitest 53 passed; Playwright E2E 2 passed; build OK.

## [4.2.0] - 2026-11-23

Release de hardening estrutural sobre a v4.1.0. Sem mudança de contrato de
estilos ou de timeline.

### Fixed — tray desktop

- Os builds portáteis Linux e Windows agora instalam o extra `tray` e passam
  `--with-tray` ao PyInstaller, incluindo `pystray`, Pillow e, no Linux,
  `python-xlib` no AppImage e no executável.
- O AppImage volta a iniciar o ícone de tray ao abrir, com backend AppIndicator
  ou GTK quando o sistema oferece `python3-gi`.

### Fixed — core silencioso

- WAV 24-bit agora calcula RMS real; `sampwidth` fora de `{2,3}` falha com
  `ValueError` em vez de retornar `0`.
- Buffers PCM incompletos são truncados sem `IndexError`.
- `qa_artifacts()` lê `work/qa/` e `exports/qa/`, com JSON inválido marcado como
  `{"error": "unreadable"}`.
- SSE de jobs non-bloqueante (`async def` + `await asyncio.sleep`).
- Sete códigos HTTP v4 adicionados ao mapeamento estável.
- Retakes usam a constante central de sample rate.

### Fixed — LLM e inteligência

- Budget e circuit breaker aplicados antes de qualquer chamada HTTP.
- Status do OpenCode em cache de 30 s com probe de 1.5 s.
- DeepSeek só é registrado com `allow_network` e API key.
- Parser JSON único para OpenAI, OpenCode, LLM e vision.
- Vision aceita `bytes` e delega ao provider canônico.

### Fixed — GPU worker e roteamento

- Registro único de handlers GPU; `handlers_gpu.py` removido.
- Preflight relê `gpu.json` a cada chamada e reporta `worker_source`.
- `compute_policy="remote"` falha com `gpu_worker_offline`; `auto` registra
  `windows_gpu_offline_fallback_cpu`.
- `render_nvenc` anexa fontes e converte 10-bit 4:2:2 para `yuv420p` em CPU.
- Escrita SMB atômica com `.part`, `fsync` e `os.replace`.

### Changed — MCP e ergonomia

- Guard único em `mcp_server/guard.py` com `invalid_params`,
  `invalid_keys` e `did_you_mean`.
- Perfis estritos: `core` com 16 tools e `full` com 21.
- Entrada única `videoflow` no OpenCode; entradas legadas são removidas no
  merge.
- `AGENTS.md` gerado com 84 linhas.

### Changed — desduplicação e faxina

- Pipelines de Shorts têm uma fonte única; módulos singulares são shims de
  17 linhas.
- Brand kit absorveu channel kit e brand templates; domínio renomeado para
  `BrandKit` com migração de rulebooks antigos.
- Estilos lidos somente de `src/videoflow/styles/` (22 estilos).
- `presets/*.md` e recipes legadas removidos.
- Wheels 3.17.x, 3.18.0 e 4.0.0 removidos; kit usa 4.2.0.
- Scripts históricos e testes exclusivos removidos; arquitetura reescrita.

### Validation

- `ruff check src packages scripts`: 0 erros.
- `pytest -q`: 2.992 passed, 1 skipped, 1 xfailed.
- `pytest -q -m media --no-cov`: verde.
- MCP: `core` = 16, `full` = 21; `AGENTS.md` = 84 linhas.

## [4.1.0] - 2026-11-22

Release de estabilidade sobre a arquitetura 4.0.

### Added — GPU e render remoto

- Guarda de carga externa: `max_gpu_utilization_pct` (default 70, `0` desliga)
  evita job remoto quando o `nvidia-smi` indica GPU ocupada, com exposição em
  `vf_capabilities` e slider no painel GPU.
- Fontes sincronizadas para render remoto: `render_nvenc` e `short_render`
  enviam `font_paths`, o worker materializa `work/fonts` e aplica `fontsdir`
  no filtro ASS. O render local de Shorts também usa o diretório portátil.

### Fixed — entrega e Shorts

- `audio.finalize` é obrigatório em **todas** as receitas de entrega, inclusive
  `synthetic_code_studio` sem `ingest`; alvos unificados em -15.5 LUFS e
  `audio.qa` falha explicitamente fora de especificação.
- Master final com duração sample-exact (correção do tail raspado pelo
  `loudnorm`).
- MP4 segmentado força 48 kHz estéreo e o master WAV padrão também é 48 kHz.
- `crossfade_ms=0` deixa de ser sobrescrito; o offset do `xfade` usa a duração
  real da saída anterior e o áudio final é alinhado ao vídeo.
- Shorts que falham no gate de duração/mídia agora propagam `ExportError` em vez
  de desaparecer do manifesto.
- XMEML e Kdenlive exportam a quarentena **V2/A2** (track desabilitada/markers e
  guides nativos), em paridade com o FCPXML.

### Changed — performance e manutenção

- `rembg` processa o diretório de frames uma vez por clipe e MediaPipe entra no
  extra `vision`; o gate de depth caiu de ~442 s para ~24 s neste host.
- `gpu_worker` refatorado: `app.py` 227 linhas, routers de admin/uploads/jobs,
  store/handlers/scene em módulos ≤400.
- `core_tools` virou pacote por domínio (44 tools preservadas).
- Exporters FCPXML, XMEML e Kdenlive divididos em módulos ≤400; helpers públicos
  preservados.
- `vf_shared.compute` e exporters têm todos os módulos refatorados ≤400 linhas.

### Validation

- 90 s e 420 s micro gates: PASS, 7/7 deliverables, loudness entre -16.8 e
  -15.4 LUFS e drift de duração abaixo de 1 frame.
- Cycle 2: PASS.
- Unit/contract, media, MCP gate, UI e módulos verdes.
- Cycle 1/NVENC e throughput de cena em CPU continuam dependentes do worker
  Windows (documentado em `docs/qa-evidence`).

## [4.0.0] - 2026-11-22

Primeira release estável da arquitetura unificada.

### Added — núcleo unificado

- `videoflow.domains.media`, `.audio`, `.asr`, `.vision` e `.toolkit` substituem
  os antigos pacotes satélites e os módulos monolíticos de `application/`.
- Um único servidor MCP com **44 tools**: stock media, TTS/stems/mix, captions,
  mattes, upscale, motion, captura web e B-roll agora vivem no core.
- `vf_audio`, `vf_vision` e as novas ações de `vf_media`
  (`fetch_stock_broll`, `rip_video_segment`, `fetch_sfx`).
- `packages/mcp-fetch`, `packages/mcp-audio` e `packages/mcp-vision` foram
  removidos, junto com os subcomandos `videoflow mcp-*`.
- `vf-shared` absorveu `vf-compute`, `vf-contracts` e `scene-rules`; nenhum
  módulo refatorado passa de 400 linhas.
- `state.json` leve com sidecars SHA-256; `media_contract` 4.0 com validação de
  áudio, alfa, CFR e duração.

### Added — GPU worker e compute

- Descoberta LAN do worker (UDP + mDNS + scan TCP) sem reiniciar o processo.
- ASR remoto sobrevive a `onnxruntime` incompleto, com retry sem VAD.
- Doctor profundo do worker, comando `gpu_worker.repair` e reparo no Start do
  kit Windows.
- `GPUWorkerClient` e `ComputeRouter` fatiados em módulos pequenos; transporte
  compartilhado, retomada de upload e `download_all`.

### Fixed — decupagem, áudio e export

- `assert_audio_duration` no master e preservação de artefatos em
  `exports/_failed/<timestamp>/` com `ffprobe.json`.
- Loudness canônico `-15.5 ± 1.5 LUFS` e piso de pads da decupagem
  (110 ms antes / 190 ms depois) sem invadir cortes ou ruído.
- `second_pass` sobre o fluxo de palavras editado e centralização de áudio
  unilateral.
- FCPXML marca a lane de quarentena como **V2/A2**.
- Caches de entrega migrados para `pipeline_schema_version = "4.0"`.

### Known limitations

- O hardening completo do worker Windows/UI (1.6b: Job Objects, VRAM guard,
  SMB atômico e painel de benchmark) segue no backlog; o worker atual mantém as
  proteções já documentadas em `docs/gpu-worker.md`.
- Os fixtures E2E de 90 s/7 min (`videoflow test-e2e`) não foram executados
  nesta validação; a suíte Playwright de UI passou.

## [3.18.0] - 2026-11-22

### Added — arquitetura v4.0 (alpha)

- `packages/vf-shared/` consolida `vf-compute`, `vf-contracts` e
  `scene-rules`, usado pelo core e pelo `gpu-worker`.
- `media_contract` 4.0 em módulos pequenos, com validação de áudio, alfa, CFR e
  `assert_pcm_buffer`/`assert_audio_duration`.
- `@mcp_tool_guard` com envelope único de erro e telemetria de execução.
- `state.json` leve com sidecars `transcript_raw`, `transcript_clean`,
  `timeline`, `pipeline` e ponteiros SHA-256.
- `ffmpeg.py` fatiado em mixins (`probe`, `audio`, `frames`, `render`, `run` e
  `shorts`).

### Fixed

- Worker remoto sobrevive a `onnxruntime` incompleto: retry de ASR sem VAD,
  doctor profundo (`SessionOptions`/`InferenceSession`), comando
  `gpu_worker.repair` e reparo automático no Start do kit.
- Export valida a duração do áudio contra a timeline e preserva segmentos +
  `ffprobe.json` em `exports/_failed/<timestamp>/` quando o gate falha.
- Áudio unilateral (um canal mudo) é centralizado no mix da timeline.
- Decupagem ganhou `second_pass=True` sobre o fluxo de palavras editado.
- Rotas do kit Windows absorvidas pelo router de GPU.
- Caches de entrega passam a usar `pipeline_schema_version = "4.0"`.

### Known limitations

- Release de **prévia**: Fases 1–2 do plano v4.0 estão parciais.
- `routes_outputs.py` ainda é monolítico; domínios `media`, `audio`, `vision`
  ainda não foram migrados; MCP ainda não tem o catálogo de 16 tools.
- Gate 1/2/3/4 reais e o `release_kit` completo ainda não foram executados.

## [3.17.4] - 2026-11-21

### Fixed — Windows GPU Worker

- O kit Windows agora exige o wheel `videoflow_gpu_worker` da mesma versão e
  falha no build quando ele não existe, em vez de empacotar silenciosamente um
  wheel antigo. O kit 3.17.3 saiu com wheel 3.9.2 e os usuários recebiam
  `E_WORKER_VERSION`; use o kit 3.17.4.
- `VideoFlowGPU.ps1` valida a versão do wheel em `wheels\` antes de instalar e
  mostra `E_WORKER_WHEEL_VERSION` com os arquivos encontrados.
- O build de release gera os wheels do worker e do scene-rules antes de montar
  o bundle.

## [3.17.3] - 2026-11-21

### Fixed — decupagem

- Repetições curtas, stopwords e repetições entre frases são detectadas no
  fluxo de palavras, sem depender da LLM, mantendo a última ocorrência.
- O padding do timeline não devolve mais áudio de retakes, repetições, ruído ou
  marca d'água; o corte forçado é aplicado antes da regra de gap curto.
- `decupage.snap` não reabsorve mais cortes deliberados abaixo de 180 ms.
- Removido o limite de quantidade de cortes; `max_cut_ratio` fica apenas como
  teto de segurança contra remoção catastrófica.
- `decupage.prefilter` e `decupage.apply` geram cortes determinísticos e expõem
  casos ambíguos (pontuação, baixa confiança, números e ênfase) para a LLM.
- Palavras de conteúdo isoladas não são mais descartadas como ruído.
- `build_plan` usa `bisect` para localizar vizinhos e não reabsorve cortes.

### Added — QA

- `qa_final` compara o WER com as palavras realmente mantidas na timeline.
- Repetição de palavra de conteúdo no áudio final marca `needs_review`.
- `cut_leak` acima de 50 ms no timeline ou na decupagem marca `needs_review`.
- Fidelidade de palavras indisponível gera aviso explícito.

## [3.17.2] - 2026-11-20

### Added — remote placement

- `vf_export` bundles and `build_delivery_bundle` can render the social master
  with worker NVENC (`compute_policy="auto"`), with local fallback and
  `placement`/`encoder`/`degraded_reason` telemetry.
- `qa_final` full word fidelity can reuse the worker ASR instead of requiring a
  local faster-whisper model.
- `shorts.reframe` can offload face tracking to the worker `face_track`
  capability, filtering only the selected pieces.
- `image_to_broll_motion` can offload zoom/pan encoding to the new worker
  `ffmpeg_transcode` capability.
- Worker `face_track` accepts sample pieces and reports only selected ranges.
- `ffmpeg_transcode` added to worker capabilities, compute VRAM table, settings,
  registry, and the GPU dashboard.

### Fixed

- `ComputeRouter.submit` accepts the historical `input` key as a single input,
  repairing existing mcp-vision remote calls.
- QA word fidelity keeps early “backend unavailable” behaviour and only extracts
  PCM after a backend is actually available.

## [3.17.1] - 2026-11-20

### Fixed

- Windows kit now ships `setuptools==80.9.0`; setuptools 81+ removed
  `pkg_resources`, which CTranslate2 4.5 still imports. This restores
  Faster-Whisper, forced alignment, and CTranslate2 CUDA detection.
- NVENC and ONNX runtime pins are deterministic: `onnxruntime-gpu==1.20.2` is
  no longer upgraded to an arbitrary latest version during repair.
- Worker startup is tolerant of broken optional handlers: a failing ASR, matte,
  or capability registration cannot abort the HTTP server.
- Dependency detection imports modules for real and reports the exact failure
  instead of claiming “not installed”.
- `/health` and `/probe` expose `asr_ready`, `asr_error`, and a dependency
  report; `/api/doctor` forces a fresh diagnosis.
- Dashboard shows ASR dependency errors and warmup errors with detail.

### Fixed — lifecycle

- `Stop` now kills the supervisor tree, waits for port 8766 to be released, and
  reports a clear error if a foreign process owns it.
- `Start` reuses a healthy supervisor, validates PID ownership, and stops only
  VideoFlow processes when a stale listener owns the port.
- Supervisor mutex is scoped per installation instead of global.
- Menu option 0 stops this worker before exiting; option 14 keeps it running.
- Added `stop -All`, menu option 13, and clear port-owner diagnostics.

## [3.17.0] - 2026-11-20

### Added

- Advanced FX MCP tools: `vf_fx_depth`, `vf_fx_parallax`, `vf_fx_motion`,
  `vf_fx_capture`, `vf_media`, `vf_font`, and `vf_preview`.
- Real-alpha validation for depth and parallax intermediates with a hard
  `alpha_channel_missing` failure instead of a black rectangle.
- Keyless Wikimedia Commons and Openverse image search with license and
  attribution metadata; `approve_license` clears the timeline audit gate.
- Fontconfig discovery and virtual metric aliases through `vf_font`.
- Release-kit titles generated from `transcript_clean`.

### Fixed

- NVENC probing now performs a real 640x360 `yuv420p` MP4 encode and tries six
  preset/rate-control profiles; the worker only advertises NVENC when bytes are
  produced. The benchmark forces a fresh probe and returns actionable advice.
- Worker renders reuse the encoder flags proven by the probe rather than
  hard-coded options that some drivers reject with `Invalid argument`.
- Windows installer NVENC checks no longer use the fragile `-f null` probe.
- Local exporter and Short renderer validate a real NVENC encode before
  selecting hardware encoding.
- Depth/parallax CPU budgets: matte downsample, MediaPipe selfie reuse, draft
  graphics, pre-blurred parallax backdrop, and JPEG frame capture.
- HTML motion graphics invalidate cache on in-place edits via content and
  `mtime` hashing; capture uses CDP frame timing with a 10 s hard timeout.
- Short batches merge overlapping source pieces, tolerate AAC frame rounding,
  and re-render stale invalid outputs.
- QA reports are stored per deliverable instead of overwriting `final_qa.json`.
- Caption previews preserve `before < during < after` ordering.
- Overlay QA accepts `visual`/`bbox` alpha bounds and marks intentional
  `top_center` top-chrome overlap.

### Performance

- Scene analysis uses a 3 fps 360p keyframe proxy and at most three visual
  samples per scene.
- Depth and parallax render in 18.2 s and 14.7 s on CPU for the 3 s/6 s cases.
- Cycle 4 micro gate completes in 164.7 s with 7/7 deliverables passing.

### Changed

- `bump_version.py` now updates all workspace package manifests.
- NVENC probing is a dedicated worker module (`gpu_worker.nvenc`) with the
  historical `handlers_gpu` surface preserved.

## [3.16.0] - 2026-11-20

### Fixed

- MCP servers now share the app's `settings.json` and `gpu.json`; they no longer
  override `VIDEOWFLOW_HOME`, so a connected worker is visible to the agent.
- Packaged MCP commands use a stable launcher instead of the disposable
  AppImage `/tmp/.mount_*` executable.
- Workspace MCP installation is local-only by default, with an explicit cleanup
  action for stale global VideoFlow entries.
- Worker ASR/matte models register in `ModelRegistry` instead of the handler
  registry; warmup no longer fails with duplicate `capability`.
- Worker runtime includes `setuptools`, fixing `pkg_resources` failures.
- Worker `/health` reports the real package version instead of `2.90.0`.
- OpenCode generated configs use 120 s MCP startup/catalog timeouts.

### Added

- `selftest` worker capability and `POST /api/v1/gpu/selftest` plus a
  “Test execution” button.
- MCP health route and global cleanup endpoint.
- Onedir AppImage builds, avoiding onefile extraction on every MCP launch.
- Shell launcher for packaged MCP commands and a Windows `.cmd` wrapper.

## [3.15.0] - 2026-11-20

### Changed

- Split `handlers_gpu.py` into `gpu_worker/gpu_handlers/` modules for common
  helpers, ASR, matte, render, vision, scene, and registration; the historical
  facade remains import-compatible.
- Extracted worker client classification and telemetry helpers from `app.py`.
- Split the embedded worker dashboard into `index.html`, `app.css`, and
  `app.js`; added local token rotation.
- Made the CPU-pool concurrency test deterministic with a barrier.

### Performance

- Short micro-clips render in a bounded parallel pool locally and on the worker
  (`VF_SHORT_SEGMENT_WORKERS`, default 2).
- `download_all` fetches independent artifacts with a bounded pool of three
  while preserving manifest order.

## [3.14.0] - 2026-11-20

### Changed

- Extracted `packages/scene-rules` as the single portable source of scene
  sampling, layout classification, editing hints, and protected-layout rules
  shared by the application and the GPU worker; the Windows kit ships it.
- Centralized Short plan/manifest/supercontext/cues/export readers in
  `short_composition/io.py` and migrated all Short steps.
- Linked styles to output formats with `format_id`; linked formats provide
  aspect ratio, safe zones, and caption preset, and unknown ids are rejected.
- Made `WorkerHealth` the canonical status model with disk, uptime, retention,
  LAN URLs, NVENC error, warmup, current job, allowlist, and token-only fields;
  a contract test guards the TypeScript interface.
- Added SSR component tests for Styles, Formats, Help, and GPU panels.

### Added

- Worker dashboard GPU/VRAM/queue history, connected clients, firewall state,
  audit decision, searchable logs, and local restart.
- mDNS advertisement/discovery when `zeroconf` is installed, real-prefix and
  multi-subnet scanning, `VF_GPU_SCAN_CIDRS`, scan cache, and deduplication.
- `VF_GPU_ALLOWED_CLIENTS`, `VF_GPU_TOKEN_ONLY`, token rotation, auth audit,
  and local-only security endpoints.
- Per-job metrics in SQLite with `/api/history`, artifact garbage collection,
  metrics pruning, and log rotation.

## [3.13.0] - 2026-11-20

### Performance

- Jobs expose monotonic `stage` and `progress`; handlers report ASR, matte,
  scene, Short render, face tracking and NVENC stages.
- Worker queues are priority queues (`-100..100`) with position, ETA and
  per-capability average elapsed time in `/api/overview`.
- Submissions are rejected with HTTP 507 when free disk drops below
  `VF_GPU_MIN_FREE_DISK_MB`.
- `POST /api/warmup`, dashboard warmup button, and `VF_GPU_WARMUP` preload
  faster-whisper and rembg; rembg sessions are cached between jobs.
- Automatic shared-mount inputs from `VF_GPU_SHARED_LOCAL_ROOT` plus worker
  `shared_root`, avoiding uploads for files already on the mount.
- Bounded parallel input uploads (`VF_GPU_UPLOAD_WORKERS`) and per-request
  transfer metrics with MB/s and dedup counters.
- Scene proxy is 360p/10 fps and visual sampling uses one sequential decode
  pass instead of random seeks; `visual_max_frames` bounds analysis.
- Finished jobs are cleaned hourly according to `VF_GPU_JOB_RETENTION_HOURS`.

## [3.12.0] - 2026-11-20

### Performance

- Persistent Short segment cache keyed by source fingerprint, crop, filter,
  FPS, and encoder; local and worker renders reuse previous micro-clips.
- Worker upload init now returns an existing content-addressed artifact instead
  of re-uploading identical inputs.
- Windows/public kit and CI remain part of the release flow.

### Changed

- Short segment cache lives under `work/shorts/<id>/segment_cache` locally and
  under `short_segment_cache` on the worker.

## [3.11.0] - 2026-11-20

### Added

- Public tokenless Windows GPU worker kit attached to releases:
  `VideoFlow-Windows-GPU-Worker-<version>.zip`, with scripts, worker wheel,
  runtime wheels, expected version, checksums, and no pairing token. The
  installer creates `worker.env` on first run.
- `scripts/build_windows_kit.py` and release/CI integration.
- Windows workflow builds and validates the tokenless kit; release workflow
  publishes it.
- GPU smoke supports LAN auto-discovery and overview/dashboard checks without a
  token (`--discover`, `--skip-jobs`).
- GPU acceptance supports discovery and `--require-nvenc`.

### Changed

- Public Windows kit uses LAN-open discovery by default; personal kits still
  include a token and warn not to publish.

## [3.10.0] - 2026-11-20

### Performance

- Worker scheduler split into one exclusive GPU lane and a bounded CPU pool
  (`VF_GPU_CPU_WORKERS`); CPU scene analysis no longer reserves VRAM or blocks
  GPU render.
- Input artifacts use hardlinks into job directories when possible, with copy
  fallback, removing duplicate large-file copies.
- Runner exposes queue wait, elapsed time, status, errors, current and recent
  jobs through `/api/overview`.
- NVENC final encode adds HQ tune, spatial/temporal AQ and lookahead 20.
- Remote micro-clips use NVENC p4/CQ20 when the worker reports NVENC.
- Parallel worker keyframe extraction.
- faster-whisper exposes CPU threads and worker count tuning.
- Windows install sets high-performance power plan, Defender exclusions when
  admin, CPU worker default, and keeps all-profile firewall rules.
- Performance documentation and worker lane metrics.

## [3.9.2] - 2026-11-20

### Changed

- Worker health and dashboard use compact job summaries instead of embedding
  full job params and inputs; `/jobs/{id}` remains the detailed endpoint.
- Built-in format presets are read-only in the Formats UI; duplicate to edit.
- Platforms and export targets are editable in the Formats UI.
- Worker status prints each LAN URL correctly on Windows.
- Help/i18n coverage and tooltips updated.

## [3.9.1] - 2026-11-20

### Fixed

- Linux GPU panel refreshes worker status every 5 seconds and retries the saved
  URL before scanning the subnet.
- Auto-discovery retries every 10 seconds instead of every 5 seconds, reducing
  LAN scan load when the worker is offline.
- Worker dashboard ignores its own polling paths when recording the last real
  request.
- Windows worker env records `VF_GPU_LOG_FILE`; “Open logs” falls back to the log
  folder when the file has not been created yet.
- Worker dashboard adds a benchmark action and keeps the NVENC error visible.

## [3.9.0] - 2026-11-20

### Added

- Windows worker dashboard embedded in the wheel at `http://127.0.0.1:8766/`,
  with connection details, LAN URLs, auth mode, firewall/discovery state,
  GPU/NVENC diagnostics, current job, recent jobs, logs, and copy/open actions.
- Worker `/api/overview`, `/api/jobs`, `/api/logs`, and local-only
  `/api/open-logs`; health now reports uptime, current job, last request,
  LAN URLs, NVENC error, and driver version.
- Active worker discovery: UDP beacon plus TCP subnet scan, merged results and
  diagnostics in `/api/v1/gpu/discovery`.
- Linux GPU panel connection card, discovery diagnostics, and live worker
  activity polling.
- `vf_format` MCP tool and format preset catalog with 9:16, 4:5, 1:1, and 16:9
  seeds, safe zones, caption presets, platforms, export targets, and CRUD.
- Formats UI with visual safe-zone preview, create, edit, duplicate, and delete.
- `vf_style` actions `create`, `duplicate`, and `restore`; Styles UI now creates
  styles and restores seeds.
- Expandable help center with search, worker/style/format/scenes/Shorts/export
  documentation, troubleshooting, and copyable prompt.

### Changed

- Windows worker menu adds “Abrir painel do worker” and status prints auth,
  encoder, LAN URLs, and dashboard URL.
- Discovered worker payloads include `auth_mode`, `nvenc`, and `encoder`.
- MCP surface is now 35 tools; resources remain 16.

## [3.8.0] - 2026-11-19

### Added

- Zero-config Windows GPU worker: LAN-open mode for private networks, automatic
  LAN discovery and reconnect, and firewall rules covering Public, Private, and
  Domain profiles.
- Worker health exposes `auth_mode`, `nvenc`, and the preferred encoder; the
  client selects NVENC only when the worker reports it, otherwise it uses
  libx264 on the worker.
- Clear NVENC diagnostics with the FFmpeg error tail; remote rendering remains
  available without NVENC.
- Setup → Workspace: native folder picker, allowed-root registration, style and
  workflow sync, and one-click OpenCode MCP installation.
- Setup → Styles, Formats, and Help panels for editing the Markdown catalog,
  reviewing aspect ratios and safe zones, and reading MCP workflow prompts and
  troubleshooting.
- Restored style, workflow, and preset API routes used by those panels.

### Changed

- Advanced worker host/token pairing is hidden under “Advanced pairing”;
  discovery and connection are automatic on the normal path.
- Windows kit defaults `VF_GPU_DISCOVERY=1` and `VF_GPU_ALLOW_LAN_OPEN=1`.
- `short.render` negotiates the worker encoder from health instead of assuming
  NVENC.

### Security

- LAN-open accepts only loopback or RFC1918 private clients. Public clients
  still require the token.
- Token-only mode remains available by setting `VF_GPU_ALLOW_LAN_OPEN=0`.

## [3.7.0] - 2026-11-19

### Added

- Decupage acoustic phase: `audio.events` with optional YAMNet ONNX,
  heuristic/AST fallback, and explicit event reports.
- Silero VAD hysteresis with `neg_threshold` plus a 10 ms RMS envelope at the
  project audio rate.
- ASR anti-hallucination profile, remote worker routing with local fallback,
  configurable `compute_policy`, and `RemoteAsrClient`.
- Forced alignment over the existing transcript with WhisperX, stable-ts,
  faster-whisper, and a remote worker fallback.
- `speech.asu` Atomic Speech Units with pauses, RMS, word probabilities, speech
  rate, and indexed words.
- `decupage.prefilter` deterministic retake grouping, stutter candidates, noise
  quarantine, and protected CTA/link/price content.
- `decupage.llm` with explicit `caller`, `videoflow`, and `none` policies,
  sliding windows, ID-only prompts, and a caller request/apply handshake.
- `decupage.apply` for validated remove/trim/restore/review decisions.
- `decupage.snap` with RMS valley snap, asymmetric pads, micro-cut merge, frame
  quantisation, and crossfade intent.
- `decupage.timeline` with revision guard, inactive segments, quarantine
  sidecar, and colored NLE markers.
- Worker capabilities `forced_align` and `vision_blur`, plus capability maps,
  settings, and GPU panel entries for the decupage workloads.
- `vf_preflight_plan(operation="decupage")` now reports per-stage compute
  placement and degradation.
- Deterministic decupage benchmark harness, synthetic evidence, and golden
  video procedure.
- `scene.analyze` Module A: 360p analysis proxy, PySceneDetect adaptive cuts
  fused with decupage jumps, MediaPipe/Haar face metrics, Canny/Laplacian
  layout classification, deterministic editing hints, 544 px keyframes, and a
  SHA-256 cache with `scenes_manifest.json` plus `timeline_supercontext.json`.
- `vf_scenes` MCP tool with `analyze`, `manifest`, `keyframe`, `supercontext`,
  and `cache` actions, plus read-only scene and keyframe resources.
- `short.plan` with scene-anchored drafts, deterministic `llm_policy=none`
  planning, caller/videoflow LLM contracts, gap/overlap resolution, minimum
  segment merging, safe-zone geometry, scene-median crops, and B-roll/upscale
  fallbacks.
- `short.validate` rejects gaps, short segments, protected B-roll, missing
  assets, unsafe captions, and excessive split-screen upscale before render.
- `short.captions` generates 3–4 word ASS blocks per layout, sanitizes overlaps,
  snaps layout cuts to caption/ASU boundaries, emits layout-change SFX cues, and
  computes 350 ms end padding plus an 80 ms fade.
- `short.render` composes per-segment filter scripts, micro-clips, concat,
  ASS burn, SFX mix, loudness normalization, NVENC on the worker, and local
  libx264 fallback with explicit degradation.
- `short.export` writes FCPXML with V1 base, V2 face panels, A1 voice, A2 SFX,
  editable captions, layout markers, and offline-media validation.
- `short.qa` audits the final Short and FCPXML; `qa.safezone` now uses the exact
  380 px bottom and 140 px right Shorts masks.
- Phase 7 `scripts/shorts_benchmark.py` with synthetic 10-minute scene F1,
  detection throughput, left/right crop accuracy, plan composition, caption
  safe zones, padding/fade, and evidence JSON/Markdown.
- Batched keyframe extraction, parallel visual sampling, FPS-proportional scene
  frame skipping, and cached scene timings.
- `delivery.collect` optionally groups final videos, exports, Shorts, and scene
  assets under `VideoFlow_Output/`; custom output paths remain fully valid.

### Changed

- `transcribe` and `alignment.forced` can run remotely or locally according to
  availability and explicit policy.
- The worker ASR handler now forwards no-speech, compression, repetition, and
  previous-text controls.
- Benchmark self-test is part of the MCP gate and enforces recall/false-positive
  thresholds.

### Fixed

- Prevented acoustic padding from crossing noise/cough boundaries.
- Prevented remote ASR from silently continuing after `remote_only` failures.
- Preserved prior pass-1 decisions when applying the continuity audit.
- Normalized remote ASR model names before submitting worker jobs.
- Added missing export/API cleanup fixes from the MCP-first transition.

### Known limitations

- Physical Windows/NVIDIA ASR, NVENC, and matte certification is pending; no
  speedup is claimed.
- `audio_events` remains local until a YAMNet worker handler is configured.
- FCPXML/OTIO V2/A2 quarantine tracks are represented by markers and
  `quarantine.json`; dedicated tracks remain future work.
- Legacy MCP aliases remain registered until the next cleanup.

## [3.6.0] - 2026-11-19

### Changed

- VideoFlow is now MCP-first. The local UI is a control panel for jobs and
  setup only: models, providers, services, extensions, connections, GPU, and
  runtime settings. The recipe studio, canvas timeline, Lamera workspace,
  assistant, schedules, media library, brand/publish screens, and their tests
  were removed.
- Removed the REST routes that only served those screens: recipes, batches,
  copilot, discovery extras, library, media, presets, publishing, schedules,
  styles, timeline, workflows, and assets.
- Removed the copilot, assistant, and schedule application modules after their
  routes and screens were deleted.
- The MCP runtime no longer depends on `BatchManager`; `ToolContext` carries
  only the job manager. The unused legacy `vf_wait_job` and
  `vf_get_transcript` helpers were removed.
- `./scripts/gate_mcp.sh` now enforces **80% coverage** on
  `src/videoflow/mcp_server` (current: 85%).

### Removed

- Legacy UI components and their Vitest/Playwright suites.
- API contract suites for the removed REST domains.

## [3.5.0] - 2026-11-19

## [3.5.0] - 2026-11-19

### Added

- Media contract for 48 kHz/24-bit audio, alpha overlays, exact rational frame
  rates, color metadata, and one-frame duration checks.
- `audio.finalize` with two-pass linear loudness, mono repair, music ducking,
  Foley mix, and 48 kHz/24-bit output.
- Immutable per-artifact QA reports and `vf_qa_compare`.
- `gpu.json` cross-process GPU configuration, `vf_gpu_preflight`, and a real
  worker `/probe` for CUDA/NVENC/ASR/matte.
- Multi-source ingest, source-aware Shorts, strict `ShortsClipSpec`, intro/outro
  validation, CFR FPS, and duration checks.
- OpenCode ergonomics: `session_brief`, named checkpoints,
  `vf_transcript_query`, `vf_glossary`, `vf_storyboard_strip`, and
  `vf_preflight_plan`.
- HTTP-first resumable uploads/downloads with SHA-256, range resume, artifact
  manifests, and automatic shared-mount fallback.
- Real NVENC probe in the worker kit, offline worker dependency wheels, full
  traceback capture, and a never-closing Windows menu.
- Overlay update/remove/list, system font discovery, transcript-derived release
  titles, alpha/color validation, and semantic retake delegation.
- Export disk estimate plus 2 GB safety margin and `.alpha`/segment cleanup.
- Eight short contract documents under `docs/contracts/`, exposed as
  `vf://docs/contracts/*`.

### Changed

- The core MCP surface is consolidated from 43 to 33 tools. Style wrappers,
  `vf_jobs`, `vf_render`, `vf_exports`, `vf_qa`, `vf_crop_preview`, and
  `vf_font` now live behind `vf_style`, `vf_job`, `vf_export`, and `vf_assets`
  actions.
- `vf_export` now owns `bundle`, `render`, `validate`, and `roundtrip`;
  `vf_job` owns `list`, `status`, `cancel`, `logs`, and `qa`; `vf_assets` owns
  font listing and registration; `vf_overlay_preview` owns `action="crop"`.
- `qa_mode="fast"` now always checks loudness and caption syntax in addition to
  duration/frames.
- `opencode.json` no longer stores literal GPU URL/token placeholders.
- Windows kit installs the worker from bundled wheels before downloading the
  CUDA runtime.

### Known limitations

- Physical ASR/NVENC/matte speed certification on Windows/NVIDIA hardware is
  still pending; no speedup is claimed without that evidence.

## [3.4.1] - 2026-11-19

### Fixed

- Windows kit now installs the worker from the local `worker\` directory or a
  bundled wheel instead of the ambiguous `uv pip install worker`.
- Replaced the fragile batch actions with one `VideoFlowGPU.bat` entry point and
  `VideoFlowGPU.ps1` menu: install/repair, start, stop, status, doctor, logs,
  autostart, and uninstall.
- Bootstrap now repairs a broken Python/venv, reinstalls the expected worker
  version, verifies CUDA/PyTorch/dependencies, downloads an NVENC FFmpeg when
  missing, validates the shared mount, and restores `worker.env` from a backup.
- Added a supervisor with exponential backoff and a private-profile firewall
  check.
- Bundled `videoflow_gpu_worker-3.4.1` wheel and Windows scripts inside the
  packaged VideoFlow data so kit generation works outside the source tree.

## [3.4.0] - 2026-11-19

GPU offload is opt-in. The automated gate is green; physical ASR/NVENC/matte
speed certification on Windows/NVIDIA hardware is still pending and is not
claimed by this release.

### Added

- Hybrid `ComputeRouter` placements with per-capability VRAM estimates,
  1-second health caching, a 2-second circuit breaker, `execute()` fallback,
  and `execution_node` labels.
- Optional GPU worker handlers for `asr` (faster-whisper), `render_nvenc`
  (FFmpeg NVENC with ASS), `segment_matte` (rembg), and `face_track` (OpenCV),
  enabled with `VF_GPU_BUILTIN_HANDLERS=1`.
- Worker health now reports `worker_id`, hostname, LAN address, platform, VRAM
  used, GPU utilization, and temperature.
- `vf_capabilities` exposes a `compute` status object and `compute_router`
  manifest entry.
- Job payloads persist an optional `execution` block.
- VRAM budget with LRU model eviction, `POST /models/unload`, and budget
  telemetry.
- Shared-mount outputs (`shared_outputs`) with atomic writes and path
  validation, plus chunked HTTP uploads instead of `read_bytes()`.
- UDP discovery beacon and a TTL-scoped peer listener (`ComputeRouter.discover`).
- Personal Windows worker kit generator with `worker.env`, bootstrap,
  autostart, stop/status scripts, optional FFmpeg/wheel payloads, API download,
  and `videoflow export-win-worker`.
- GPU settings (`GpuSettings`) persisted with the app settings; worker tokens
  stay in the secret store.
- Setup → GPU acceleration tab with pairing, LAN discovery, per-capability
  toggles, shared-mount validation, VRAM/fallback controls, benchmark, and
  memory release.
- GPU status routes and a header pill for ready, busy, local, and offline
  states.
- `scripts/gpu_acceptance.py` and the 3.4.0 acceptance/performance docs. The
  release remains blocked until real Windows/NVIDIA ASR, NVENC, and matte
  measurements pass.

## [3.3.0] - 2026-11-19

### Added

- `speech.editorial_clean`: deterministic stutter, false-start, fuzzy retake,
  optional semantic retake, energy-snap, and 15 ms micro-fade pipeline with
  `transcript_clean.json` and an auditable cut report.
- Short thought-boundary enforcement with terminal punctuation and pause
  validation.
- `vf_assets` for listing, approving, and quarantining project assets.
- `vf_depth_composite`, `vf_pip`, `vf_parallax`, and `vf_style_preview`
  compositors with explicit anchors and `z` layers.
- `vf_export` `fps`, `preset`, and `qa_mode` controls; full QA can run as a
  background job.
- `vf_qa_final` short-aware windows, configurable WER, and alpha-based overlay
  collision detection.
- Font metric aliases (`Arial` → `Liberation Sans`, and equivalents).
- Project slug ids with deterministic UUIDv5 state ids and clone targets.
- B-roll aspect/width/height parity and project-canvas inheritance.
- Structured MCP errors with `error_code`, `failed_command`, `stderr_tail`, and
  `fix_hint`.

### Changed

- Social MP4 deliveries default to **30 fps** and `veryfast`; NLE targets keep
  the source cadence. `fps="source"` opts out.
- Export QA defaults to fast checks; `qa_mode="full"` dispatches background QA
  and `off` skips it. `vf_qa_final` remains complete.
- Word-fidelity WER defaults to `0.12`, with a `0.06–0.12` warning band.
- Licensing is scoped to assets referenced by the timeline, overlays, B-roll,
  and audio plan; unused ledger records no longer block delivery.
- `audio.compose` follows the timeline duration and no longer caps music at
  120 seconds.
- The core MCP surface now has **37 tools**.

### Fixed

- ASS captions resolve metric-compatible fonts and avoid overlap.
- Crop expressions escape safely and collapse static keyframes.
- Alpha WebM overlays force the `libvpx-vp9` decoder; rounded PiP writes WebM
  with a real alpha channel.
- HTML/Chromium capture uses bounded waits and even output dimensions.

## [3.2.1] - 2026-11-18

### Added

- Four cinematic/retention styles in the central catalog:
  `lf-depth-title-cinema`, `lf-3d-web-showcase`, `lf-parallax-25d-doc`, and
  `sr-depth-3d-viral`.
- NLE overlay transforms and z-order lanes for FCPXML, XMEML, and Kdenlive.
- Automatic `layout.json` beside every MP4 deliverable.
- `qa.overlay_bounds`, `qa.caption_effect`, `qa.final`, `curation.prepare`,
  `transcript.dedupe`, and `shorts.tighten` step coverage.
- Curation previews with ducked music candidates, B-roll contact sheet, 10 s
  SFX demo, and one-minute sample.
- Channel brand kits under `brands/{channel_id}/`, auto-created on project init.
- `effect_fallback` and 4–6 word stable caption blocks.
- 15 ms Short join crossfades and word-boundary guard.
- `needs_review` rerender autofix using cached video groups.

### Changed

- `vf_export` applies a brand-kit LUT when no explicit LUT is supplied.
- `vf_qa_autofix` can re-render the master and run final QA.
- Master recipes now run `qa.final` after `export.video`.
- `AGENTS.md` documents the advanced depth/3D/parallax recipes and the
  `videoflow/templates/opencode/AGENTS.md` bootstrap template mirrors it.

## [3.2.0] - 2026-11-18

### Added

- Overlay geometry with explicit anchors, pixel margins, z-index, real asset
  dimensions, collision detection, auto-packing, `vf_overlay_preview`,
  `vf_layout`, `vf_caption_preview`, and `vf_qa_autofix`.
- Caption `effect` model (`static`, `karaoke_switch`, `karaoke_sweep`, `pop`),
  stable 4-6 word blocks, proportional word fallback, caption QA, and
  before/during/after visual previews.
- Strict MP4 integrity gate (±1 frame, frame count, last-sentence guard),
  explicit `-t` muxing, and a 500 ms tail guard persisted in the timeline.
- `needs_review` job status, granular step progress/ETA, heartbeat renewal,
  and real queued `vf_shorts_batch` jobs.
- `transcript.dedupe`, low-confidence word flags, `transcript_clean.json`, and
  word-level slicing.
- `shorts.tighten` with VAD edge trimming, internal-silence removal, and
  speech-density rejection.
- Final MP4 QA with loudness/true-peak policy, audio silence detection,
  overlay/caption collisions, word fidelity via Faster-Whisper, contact sheet,
  and waveform. `publish.release_kit` and channel brand kits.
- 32-tool core MCP surface.

### Changed

- Project state schema is 4. Legacy schemas and deprecated fields are rejected.
- Caption `animation`, beatmap `cuts`, overlay `position_x/position_y`, and
  isolated final `-shortest` muxing were removed.
- `vf_shorts_batch` now returns a job and supports `wait=True`.
- Unknown caption effects, layouts, presets, and fonts fail explicitly.

## [3.1.0] - 2026-11-18

### Added

- Stateful tools-only MCP runs: `vf_run`, a complete `PipelineContext` inside
  `project_state.json`, per-step checkpoints, `resume`, and `through`.
- Unified SQLite job queue for MCP, REST, and the tray, with WAL, busy timeout,
  cross-process cancellation, and `vf_jobs`.
- Bidirectional source/timeline time mapping, `keep_ranges`/`remove_ranges`,
  `dry_run`, destructive-edit guard, and revision history/undo/restore.
- Normalized crop math, `vf_crop_preview`, ASS smart wrapping, single-slash
  override tags, caption dedup, word timing, intro offset, and mandatory
  `fontsdir`.
- Duration gate (`ffprobe`, 100 ms), CFR repair, one `master_export` engine for
  `export.video`/`vf_export`/delivery bundle, and PCM 24-bit sidecars.
- Cached rounded-window masks, hard-cut macro-blocks, and
  `-filter_complex_script` for large graphs.
- Content-addressed analysis cache, hardlinked media pool, disk preflight, and
  render-segment pruning.
- Model discovery in `~/.videoflow/models`, expanded capabilities, style
  validation/compilation, beat-map planning, overlays, Shorts batch, final MP4
  QA, and font management.
- New MCP tools: `vf_run`, `vf_jobs`, `vf_export`, `vf_crop_preview`,
  `vf_style_validate`, `vf_style_apply`, `vf_beatmap_plan`, `vf_overlay`,
  `vf_shorts_batch`, `vf_qa_final`, and `vf_font`.

### Changed

- Project state schema v3 adds the `pipeline` block; workspace `state.json` is
  a mirror of `project_state.json`.
- `cut`-style beatmap `cuts` is deprecated in favor of `keep_ranges` and
  `remove_ranges`.
- Caption default is `word_timing="word"` with an explicit fallback warning.
- Unknown caption presets fail explicitly instead of silently falling back.
- `vf_ingest` returns normalized mode, step type, duration, CFR fps, PCM path,
  and audio offset.
- Audio three-act mixing uses timeline duration, and `audio.compose` reports
  generated/loop metadata.

### Fixed

- Static crop no longer interprets a normalized focus as a pixel offset.
- Segment concat duration drift is detected and repaired before delivery.
- Intro prepends no longer desynchronize burned captions.
- `VF_WORKSPACE_ROOT`/`VF_PROJECTS_ROOT` no longer produce
  `projects/projects/{id}`.
- Repeated Short analysis reads scene/energy data from the content cache.

## [3.0.4] - 2026-11-18

### Added

- CSS-selector element capture for `capture_web_or_screen`: the screenshot or
  clip is clipped to the selected DOM element via Chromium CDP.

### Changed

- Scroll capture and element capture share one CDP session.

## [3.0.3] - 2026-11-18

### Added

- Real browser scroll capture for `capture_web_or_screen` via Chromium CDP
  (`scroll_animation` for screenshot and clip modes).
- `websocket-client` dependency for the vision MCP package.

### Changed

- Documented B-roll Ken Burns/transformative crop and browser scroll capture.

## [3.0.2] - 2026-11-18

### Changed

- B-roll overlays persist `ken_burns`, `transformative_crop`, and `layout`.
- Export overlays apply transformative crop and a slow Ken Burns zoom before
  scaling, while preserving the existing overlay positioning.
- Schema exports refreshed for the new overlay fields.

## [3.0.1] - 2026-11-18

### Added

- `analyze_reference_style` MCP tool and `vf_style(action="analyze")` candidate
  analysis without saving.
- `vf_style_list`, `vf_style_save`, and `vf_style_learn_rule` MCP aliases.
- Style duplicate and restore-seed APIs/UI.
- `capture_web_or_screen(mode="video_clip")` alias.

### Fixed

- Style API exposes the v2 platform, beatmap, sound, hook, and intro fields.
- OpenCode Studio exposes style duplicate/restore actions.

## [3.0.0] - 2026-11-18

### Added

- Workflow Markdown catalog with five seeds and CRUD/sync APIs.
- OpenCode Studio Manager UI with AGENTS.md, Workflows, and Styles tabs.
- OpenCode `opencode` MCP profile; prompts are off by default.
- Style schema v2: platforms, beatmap defaults, sound design, hook/intro
  strategy, new layout/motion enums.
- Five Longform and ten Shorts/Reels seed styles for YouTube, Shorts, Reels,
  Instagram, X, and Facebook.
- `apply_beatmap` v2: transitions (`wipe_left`, `wipe_right`, `slide_up`,
  `zoom_in`, `whip_pan`, `glitch`), linked SFX, graphics, B-roll layouts, and
  beatmap captions.
- `render_motion_graphic(draft=true)` shorthand and
  `capture_web_or_screen(css_selector, scroll_animation)`.
- v3.0.0 export names: `youtube_master.mp4`, `resolve_timeline.fcpxml`,
  `premiere_timeline.xml`, `kdenlive_project.mlt`.

### Changed

- Bootstrap defaults to `opencode`, copies workflows, and generates the six
  Diretor Lego commands.
- AGENTS.md requires choosing both a Style and a Workflow before editing.
- Delivery bundle and NLE validation accept v2 names plus legacy aliases.

### Fixed

- Style frontmatter round-trips the v2 fields.
- Bootstrap reports `copied_workflows` in API/UI.
- Beatmap transitions preserve typed `Transition` models and linked SFX.

## [2.91.9] - 2026-11-17

### Added

- `videoflow tray --check` and a `doctor` tray section report the display,
  backend, menu availability, PyGObject, and AppIndicator status.
- Release builds bundle `pystray`, Pillow, and `python-xlib` through
  `--with-tray`.

### Fixed

- The AppImage now includes the tray dependencies, so the icon is created
  instead of silently falling back to `serve`.
- Tray startup requires a menu-capable backend; xorg-only sessions get an
  explicit explanation instead of an icon without Restart/Quit.
- Open/Restart wait for the local health check; browser opening falls back to
  `xdg-open`/`gio open`.
- Stop/Quit force the owned Uvicorn thread to exit and remove the PID file.

## [2.91.8] - 2026-11-17

### Changed

- Video export and delivery bundle share one subtitle-track resolver.
- Audio-master timeline/source branching and caption timeline typing were
  simplified without changing behavior.

### Fixed

- MCP job payloads also strip nested recipe variants and relabel internal recipe
  jobs as step jobs, so no DAG metadata reaches the tools-only surface.

## [2.91.7] - 2026-11-17

### Fixed

- Step-state handoff only persists artifacts inside the project output or a
  configured allowed root.
- README documents the tools-only MCP surface accurately.

## [2.91.6] - 2026-11-17

### Changed

- The MCP surface is tools-only: recipes are no longer listed, read, validated,
  run, or accepted as DAG payloads. Use the node catalog and individual steps.
- Added `vf://docs/steps` with the complete node catalog and paginated
  `vf_catalog_search` results.
- Added a project-level step-state ledger so artifacts and metadata survive
  between `vf_exec(action="step")` jobs.
- Step jobs now expose `vf_job` payloads without recipe documents or variables.

### Fixed

- Channel-kit merge no longer hashes list/dict placeholders.
- `vf_project(init)` validates `channel_id` as a shipped/operator kit and keeps
  `style_id` separate.
- AppImage/MCP data directories fall back to a writable home instead of the
  read-only mount; `opencode.json` now sets `VIDEOWFLOW_HOME`.
- Long-form captions map source transcript timing through the active timeline.
- `audio.compose`/`audio.mix` share the `audio_music` artifact and support
  explicit paths for standalone step calls.
- `audio.master` renders the active timeline when available.
- Punch-in/scale paths normalize to square pixels (`setsar=1`) before concat.
- Delivery bundles burn `subtitles.ass` by default.
- `mix_and_master_track` writes to the project root, not a doubled project path,
  and generated assets use the `ai_generated` license so bundles are not blocked.

## [2.91.5] - 2026-11-17

### Changed

- Focus-gap filling is linear instead of rescanning the list for every sample.
- Motion centroids are computed in one vectorized pass instead of a Python
  loop per frame.
- YOLO models load once per path and process instead of once per Short.
- Forced alignment uses binary search for ordered ASR words, with the linear
  filter kept as a fallback for unordered input.
- Reframe hoists per-run settings, source path, sample rate, and sentence-id
  sets out of the clip loop.
- MCP audio/vision cache writer signature introspection.

## [2.91.4] - 2026-11-17

### Added

- MediaPipe Tasks face detection for reframe tracking, alongside the legacy
  Solutions API. Recent MediaPipe wheels are Tasks-only, so tracking now accepts
  `mediapipe_model_path` / `VIDEOWFLOW_MEDIAPIPE_MODEL` or the
  `mediapipe-face-detector` model catalog entry.
- Tracking samples RGB frames for MediaPipe and converts to BGR for YOLO.
- Regression coverage for divergent `VF_PROJECT_OUTPUT` and workspace roots.
- Tests for color motion fallback, MediaPipe Tasks detection, and catalog model
  resolution.

### Fixed

- Motion tracking now reduces color frames to one channel when a face backend
  falls back, instead of failing on a broadcast error.
- OpenCV Haar tracking samples 256x144 gray frames instead of 64x36, where a
  face is too small to detect.
- MCP audio/vision storage resolves a relative `vf_contracts` result against the
  contract workspace, so `VF_PROJECT_OUTPUT` overrides work without
  `OutputNotProducedError`.
- Eye-contact analysis skips Tasks-only MediaPipe wheels and falls back to
  YOLO/OpenCV instead of raising on `mediapipe.solutions`.
- Tracking extra pins `mediapipe<1` and `opencv-contrib-python<5` so MediaPipe
  cannot replace the OpenCV 4 Haar cascade build with OpenCV 5.

## [2.91.3] - 2026-11-17

### Added

- Shared optional vision backend discovery for MediaPipe, YOLO, OpenCV, and motion.
- Automatic reframe tracking resolution: MediaPipe → local YOLO → OpenCV Haar → motion.
- Focus-gap interpolation, smoothing, and `vision/tracking.json` with the concrete
  backend, detections, frames, and fallback reason.
- `settings.vision` with tracking backend, YOLO model/confidence, MediaPipe model,
  smoothing, and sample FPS.
- Optional `tracking` and `alignment` extras.
- Auto language detection for Faster-Whisper, whisper.cpp, and HTTP ASR, with a
  `langdetect`/stopword fallback for SRT.
- Detected language persisted in `ProjectState`, pipeline context, metadata, and
  `transcript/language.json`; translation reuses it.
- Forced alignment reports detected language/confidence and reuses the project language.
- `docs/upscale.md` and expanded tracking/language/parity documentation.

### Fixed

- Remote image upscale now uses the source extension instead of `upscaled.mp4`.
- Real-ESRGAN video upscale extracts frames, preserves original audio, and
  re-encodes H.264/AAC with faststart.
- Upscale cache keys include the concrete backend, so Lanczos cannot shadow
  Real-ESRGAN or remote results.
- Upscale output is limited to 8192px and metadata records dimensions/fallback.
- FFmpeg video upscale preserves audio and adds `+faststart`.

## [2.91.2] - 2026-11-17

### Changed

- NLE validation parses each export once and can skip formats the bundle did not request.
- The delivery bundle validates only requested NLE formats and hashes each
  artifact with one stat call.
- OpenCode packaged detection and project-root lookup are cached.
- Style saves are no-ops when the rendered Markdown is unchanged; style sync
  skips manifest writes when nothing changed.
- The bootstrap `AGENTS.md` writer reports `unchanged` instead of rewriting the
  same managed block.
- Removed the unused bundle `basename` option now that bundle names are fixed.

## [2.91.1] - 2026-11-17

### Added

- Canonical Markdown style catalog under `{data}/styles` with YAML frontmatter,
  Pydantic validation, SQLite index, mtime cache, three shipped seeds, and
  workspace sync with SHA-256 manifests.
- `vf_style` core MCP tool with `list`, `get`, `save`, `learn_rule`, `sync`, and
  `delete`; resources `vf://styles` and `vf://styles/{style_id}`.
- `vf_project(style_id=...)` binds a style to the project record and
  `project_state.json`; recipes apply the style-derived channel kit.
- `videoflow style list|save|learn|sync`, plus REST `/api/v1/styles*`.
- OpenCode workspace bootstrap (`videoflow init-opencode` and
  `POST /api/v1/system/bootstrap/opencode`) generating `opencode.json`,
  managed `AGENTS.md`, skills, slash commands, `presets/`, `references/`,
  `projects/`, global config merge, backups, and an optional 10s sample.
- `Setup → Connect → OpenCode Studio Bootstrap` card with folder picker, profile,
  style preview, options, result summary, and copyable launch command.
- Packaged domain MCP servers: `videoflow mcp-fetch`, `mcp-audio`, `mcp-vision`.
- Delivery bundle fixed names: `final_youtube.mp4`, `timeline_resolve.fcpxml`,
  `timeline_premiere.xml`, `timeline_kdenlive.kdenlive`, and
  `timeline_kdenlive.mlt`.
- Style `export_targets` drives `vf_exports(bundle)` and `delivery.package` when
  targets are omitted.

### Changed

- Captions, music ducking envelopes, and dedicated caption tracks are exported
  in all three NLE dialects.
- Manual clip timing edits in an NLE shift transcript/ducking even without
  explicit `vf:` markers.
- Kdenlive roundtrip reads only the two video playlists.
- `vf_exports` validation recognizes both bundle names and legacy names.

### Fixed

- Premiere XMEML now carries center/position keyframes for reframe.
- `clone_style` samples video frames and estimates cut rhythm.
- `delivery.package` works for long-form projects without a Shorts render.
- AppImage and portable binary include all four MCP servers.

## [2.91.0] - 2026-11-16

### Added

- `vf_exports(action="bundle")` and `application/delivery_bundle.py` export the
  same validated timeline to MP4, Resolve FCPXML, Premiere XMEML, and native
  Kdenlive MLT in one call, with SHA-256 hashes and `exports/bundle.json`.
- `delivery.package` accepts `targets` and forwards them to the bundle.
- YouTube/social MP4 profile: H.264 High, AAC 320 kbps, CFR, `+faststart`, and a
  configurable `-16.5`/`-14 LUFS` target when no mastered audio exists.
- Kdenlive multi-source export creates one native MLT chain per source.
- FCPXML 1.10 is now the default; 1.9 remains opt-in.
- Cross-validation checks referenced media, timeline duration, and blocked
  licenses for FCPXML, XMEML, and Kdenlive.
- XMEML/Premiere roundtrip through `nle.sync_back`.
- `vf_timeline(action="apply_beatmap")` applies cuts, B-roll, overlays, zoom
  keyframes, SFX, and music atomically with revision checks.
- Music tracks with ducking envelopes in FCPXML, XMEML, and Kdenlive.
- GPU worker `asr` and `diarize` handlers and remote ASR fallback in
  `transcribe_word_aligned`.
- `render_motion_graphic` engines `html`, `hyperframes`, and `ffmpeg`, with alpha,
  draft scale, and SHA-256 source caching.
- `capture_web_or_screen` as the sixth vision tool.
- `vf_project(action="clone_style")` and `vf_project(action="learn_rule")`.
- `--no-prompts` / `VF_MCP_PROMPTS=0` for the core and generated `mcp.json`.
- `scripts/nle_multi_smoke.py` and `scripts/gpu_worker_smoke.py`; the GPU smoke
  supports `--local` for a real loopback worker run without the Windows host.
- `clone_style` samples video frames and estimates cut rhythm, not only one
  screenshot.
- NLE sync regenerates long-form captions and ASS after transcript shifts.
- XMEML Basic Motion now carries center/position keyframes for Premiere reframe.

### Changed

- `vf_exec` documentation now prioritizes recipes and Shorts; `step` remains an
  internal power path.
- `deliver` prompt targets the multi-NLE bundle.

### Fixed

- MP4 delivery reuses `audio/master.wav` instead of remastering twice.
- Multi-source Kdenlive no longer references a single hardcoded chain.
- Kdenlive roundtrip reads only the video playlists instead of counting audio,
  music, and overlay entries as clips.
- `delivery.package` can bundle a long-form project without a Shorts render.

## [2.90.1] - 2026-11-16

### Changed

- Cached the static 124-step catalog for MCP searches.
- Optimized workspace asset lookup to a single pass over project assets.
- Removed dead imports and tightened the core MCP surface.
- Kept the 12-tool core profile and modular domain servers unchanged.

## [2.90.0] - 2026-11-16

### Added

- **Modular MCP topology.** Core MCP with 12 tools plus isolated
  `mcp-vf-media-fetch`, `mcp-vf-audio-studio`, `mcp-vf-vision-fx`, and
  `videoflow-gpu-worker` packages.
- **Shared Workspace Contract.** `vf-contracts` creates the canonical project
  tree, content-addressed asset cache, license sidecars, and path-safe access.
- **Hybrid GPU routing.** `vf-compute` provides `ComputeRouter` with
  `auto|local_only|remote_preferred`, health caching, circuit breaker, VRAM
  and queue checks, and a token-authenticated worker client.
- **Windows GPU worker.** FastAPI daemon with content-addressed artifacts,
  async jobs, allowlisted capability handlers, model TTL, queueing, and
  artifact download.
- **Domain media tools.** Stock/URL/SFX fetch, TTS, cleanup, stems, music/SFX,
  word-aligned captions, rembg, upscale, Remotion/Manim motion, and Ken Burns.
- **Multicam angle planning.** `multicam.plan` and `multicam.apply` support
  manual, speaker, and alternating angle cuts on multi-source projects.
- **Resolve smoke evidence.** `scripts/resolve_smoke.py` and the manual Resolve
  gate documented in `docs/resolve.md`.
- **MCP profiles.** `scripts/generate_mcp_config.py` and
  `scripts/install_mcp_servers.sh` for OpenCode profiles.

## [2.85.1] - 2026-11-16

### Changed

- **Agent MCP refactor.** Shared project/job/resource helpers moved out of the
  900-line tool module; `ToolContext` now contains only the job manager and
  batch manager. Legacy process-global context helpers were removed.
- **Project state v2 hardening.** Version 1 project states migrate to the
  multi-source schema on load.
- **Scene cache.** Playwright scene renders are content-addressed.
- **Draft previews.** Cutout and storyboard previews respect `draft_scale`.

## [2.85.0] - 2026-11-16

### Added

- **Production OpenCode MCP profile.** The public MCP surface is now 22
  project-scoped `vf_*` tools with explicit `project_id` values, per-project
  resources, optimistic revision checks, and no process-global active project.
- **Multi-source projects.** `ProjectState` carries multiple sources and every
  video/audio segment references a `source_id`. `session.ingest` orders,
  normalizes, and builds a packed multi-source timeline; `session.cull` applies
  retakes across file boundaries.
- **Multicam sync.** `sync.multicam_audio` reports audio offset, drift, and
  confidence from normalized cross-correlation.
- **Observability.** `vf_get_step_logs` returns bounded logs, commands, stage
  timings, and peak RSS. `vf_get_qa_artifacts` returns failed frames as MCP image
  content for VLM inspection.
- **Async render contract.** `vf_render_start`, `vf_wait_job`, and
  `vf_get_artifact` replace blocking render calls.
- **Preset schema v2.** Hard constraints are separate from learned rules
  (maximum 15), and channel kits bundle fonts, LUT, music, SFX, captions, and
  intro/outro assets.
- **Resolve bridge.** Optional DaVinci Resolve Studio scripting for push, pull,
  and sync-back with FCPXML fallback.

## [2.80.0] - 2026-11-15

### Added

- **Headless MCP edition foundation.** `videoflow serve --mcp-only` runs the
  API/MCP daemon without the Svelte UI or tray. The new `vf_*` tools cover
  beat maps, archetype previews, web-scene preview, audio line patches, NLE
  roundtrip, 10 FPS QA windows, channel rulebooks, and style cloning.
- **14 headless steps** for web motion, cutout layouts, visual/safe-zone QA,
  pacing audits, gaze, screen capture, reference boards, transformative
  guards, procedural SFX, style reverse-engineering, preset rules, NLE sync
  back, intros, and structured self-heal.
- **Core media reliability.** VFR-to-CFR normalisation, optional ingest proxy,
  onset/drift diagnostics, a serialized render gate, and optional model entries
  for Silero, MediaPipe, and Tesseract.
- **Four OpenCode recipes** and four `vf://` MCP resources.
- Model update support in the API and Models UI.
- A headless/hybrid MCP callout in the Integrations interface.

## [2.72.4] - 2026-11-14

### Fixed

- **Tray menu now opens on click.** Linux uses AppIndicator/GTK when PyGObject
  is available instead of forcing the xorg backend, which has no menu support.
  The menu shows the version, service/job status, open/restart/start/stop
  actions, and **Quit VideoFlow** (stops the service and exits).
- Tray status refreshes every five seconds through `icon.update_menu()`.

## [2.72.3] - 2026-11-14

### Changed

- **Fast release workflow.** `./scripts/release_fast.sh X.Y.Z` now bumps the
  version, runs the fast gate, overlays the source on a prebuilt onedir
  runtime, and stages `VideoFlow-X.Y.Z-linux-x86_64.tar.zst`. A warm release
  takes about 40 seconds instead of ~25 minutes.
- `./scripts/gate_local.sh` is fast by default: ruff, changed Python tests, and
  UI unit/static checks. Use `--full` for fault injection, media, one coverage
  run, Playwright, and the perf check.
- The PyInstaller spec excludes test-only packages (`pytest`, `sqlalchemy`,
  `alembic`, `scipy`, `pandas`, `sklearn`, `torchaudio`, `lightning`,
  `tensorflow`, `grpc`, `mako`) while keeping the runtime dependencies.
- `release_local.sh` keeps the complete onefile + AppImage + SBOM path and now
  reuses the UI build instead of running Vite twice.
- Build caches are preserved between releases (`build/`, `dist/`, `vendor/`,
  `ui/build`, and `build/videoflow-base`). Cold builds are explicit via
  `--clean`; the fast runtime can be rebuilt with `--refresh-runtime`.

## [2.72.2] - 2026-11-13

### Added

- **Adaptive ASR profiles.** `balanced` (large-v3-turbo, greedy, VAD, physical
  cores) is the default; `fast`, `quality`, `vulkan`, `remote`, and `custom`
  cover the other speed/quality trade-offs. Beam, CPU threads, word timestamps,
  VAD, and condition-on-previous-text are configurable per run.
- **Vulkan whisper.cpp build.** `scripts/fetch_whisper.py --vulkan` and
  `build_portable.py --whisper-vulkan` compile the Vulkan backend when `glslc`
  is available. The profile falls back when Vulkan only reports llvmpipe.
- **Remote ASR profile.** Settings and a per-step `remote` profile use the
  existing HTTP adapter for a LAN/Tailscale GPU host.
- **ASR benchmark.** `scripts/benchmark_asr.py` reports elapsed time, RTF,
  model, beam, threads, and word count for one sample.

### Changed

- **Notifications are off by default.** New installations show no in-app toasts,
  desktop pop-ups, or external channel messages. Settings → Notifications now
  has a master switch, separate in-app and desktop levels (`off`, `required`,
  `important`, `all`), per-event checkboxes, local log/desktop toggles, and an
  explicit test action.
- Routine job finished/cancelled, pause/resume, retry, copy, and theme notices
  were removed. HITL requests and actionable job failures remain available when
  notifications are enabled.
- `VIDEOWFLOW_NOTIFICATIONS=off` and `VIDEOWFLOW_DESKTOP_NOTIFICATIONS=0`
  override delivery. The test suite disables both globally.
- `word_timestamps=off` is supported without a second alignment pass; sentence
  timings remain available when word-level editing is not required.
- Faster-Whisper now uses physical cores by default and logs the selected
  profile/model/beam/threads.

## [2.72.1] - 2026-11-13

### Fixed

- **AppImage now starts the tray.** The no-argument `AppRun` and desktop entry
  launch `videoflow tray`, so the icon appears and controls the service instead
  of starting a terminal-only `serve` process.
- **Frozen tray backend.** The portable build forces the XEmbed (`xorg`)
  backend on Linux/X11, bundles `Xlib`/`six`/pystray backends explicitly, and
  records the chosen backend in the server log.
- Added `scripts/tray_smoke.py`, which verifies the XEmbed icon and the
  pause/resume/cancel-all controls against a built binary.

## [2.72.0] - 2026-11-13

### Added

- **Tray execution controls.** The desktop tray now shows running, queued,
  paused, and waiting counts, opens the Runs area directly, and can pause,
  resume, or cancel all jobs through new `pause_all`/`resume_all` endpoints.
- **Recipe preflight.** A structured report covers graph, ports, parameters,
  paths, variables, FFmpeg, transcription, providers/secrets, optional OCR,
  Playwright, vision, isolation, yt-dlp, and disk space. Errors block the run;
  warnings describe fallbacks.
- **Deeper HITL.** Expiration is enforced, answers/comments/artifact reviews are
  kept as per-interaction drafts, uploads show progress, and the inbox can
  approve selected gates in bulk with independent resume.
- **Mobile timeline fallback.** Below 1024 px the timeline becomes a selectable
  clip list with seek, activate/deactivate, and inspector-based trim/move.
- **Scene and callout editors.** Synthetic and Footage workspaces can edit the
  scene/callout JSON plan and save it through an allowlisted, atomic artifact
  endpoint with an edit audit log.
- **QA evidence harness.** `scripts/qa_evidence.py` records NLE structure,
  Kdenlive/Flatpak version, an MLT `melt` render, Orca/display availability, and
  the visual baselines without fabricating human sign-off.

### Changed

- Extracted recipe and timeline panels into focused components while keeping
  testids, markup, and behavior.
- Added Playwright visual baselines for shell desktop/mobile, mobile builder,
  mobile timeline, HITL inbox, Synthetic, and Footage workspaces.
- Full-tree coverage moved above the 95% target while new modules landed.

### Fixed

- Audio composition creates its output directory before writing the music plan.
- Stabilized job-store tests that raced the worker's final JSON write.

## [2.71.0] - 2026-11-13

### Added

- **Produce overview.** A favorites-first home with pending gates, recent runs,
  setup health, a searchable recipe library, and a two-step run composer with
  source/workspace pickers, variables, and preflight checks.
- **HITL inbox and run workspace.** A global pending-gates drawer, a generic
  `#run/<job_id>` workspace with phase progress, artifacts, logs, and history,
  plus recipe-specific panels for Synthetic Code Studio, Footage Intelligence
  Edit, Lamera, Full AI Editor, and DeepSeek.
- **Richer HITL requests.** Gates now carry summary, checklist, severity, next
  step, and group metadata; required questions are validated before submission.
- **Setup health, media/library summaries, assistant suggestions, and a mobile
  step-list fallback** for the recipe builder.
- **Script-first recipes can run without source media.** The runner gets a
  deterministic placeholder source and a workspace default.

### Changed

- New design foundation: tokens, readability floor, rail/sidebar shell, active
  run bar, larger shared controls, and the decorative grid removed.
- The default Produce tab is now Overview; `#recipes` keeps the graph builder.
- Runs show a needs-you summary and can open the run workspace directly.

### Fixed

- Direct video export can use the final mixed audio and merged subtitles.
- Workspace polling pauses in hidden tabs, avoids overlap, and does not reload
  logs and history when the run status has not changed.

## [2.70.0] - 2026-11-12

### Added

- **Synthetic Code Studio.** A 43-node, six-phase recipe for script-first
  video: research, fact-check, narration synthesis/alignment, timed storyboard,
  HTML/CSS scene codegen, headless rendering with an FFmpeg fallback, procedural
  audio with ducking/LUFS, captions, QA, and master export.
- **Footage Intelligence Edit.** A 54-node, six-phase recipe for real footage:
  decoupage, entities, style, OCR, subject masks, all three vision anchors,
  tracked callouts, licensed media, direct MP4 with the final mix, NLE/EDL
  export, and QA.
- **New pipeline steps.** `narration.synthesize`, `narration.align`,
  `storyboard.timed`, `scene.codegen`, `scene.render`, `scene.assemble`,
  `export.master`, `captions.plan`, `vision.ocr`, `vision.segment`,
  `vision.track`, `motion.callout`, `motion.attach`, `composite.matte`,
  `qa.frames`, `qa.transcript`, `qa.repair`, and a live `qa.vision`.
- **Multimodal QA.** `qa.vision` sends sampled frames to a configured
  OpenAI-compatible vision provider, with deterministic frame, transcript, and
  loudness checks as the fallback.
- **Optional Three.js.** `scene.codegen.three_js_path` adds a WebGL camera and
  3D plane to the generated scene document.
- **Tray extras in the portable build.** Pillow, pystray, and pytesseract are
  collected when installed; the tray icon and callout cards no longer depend on
  source-only files.

### Changed

- `audio.mix` supports sidechain ducking and an optional target LUFS.
- `audio.compose`, `audio.qa`, and `storyboard.preview` no longer require ingest
  state, so the synthetic recipe can run without source footage.
- `export.video` accepts `audio_source="mix"` and burns the merged
  `subtitles.ass` when present.
- `synthetic_code_studio` and `footage_intelligence_edit` are built-in
  favorites.

## [2.69.0] - 2026-11-12

### Changed

- **Eye-contact analyzers extracted.** MediaPipe, YOLO, OpenCV, cascade loading,
  and interval merging now live in `application/eye_contact.py`; the step keeps
  the orchestration and the legacy underscore imports as aliases.
- **Parallel research reuses run state.** Research groups share the parent's
  source stamp and Intelligence instance instead of recomputing them for every
  nested agent runner.
- **Adaptive Lamera polling.** The workspace polls quickly while a run is active,
  backs off while queued or waiting on a human gate, pauses in hidden tabs, and
  never starts a second request while one is in flight.

## [2.68.0] - 2026-11-12

### Added

- **Optional voice cloning.** The voice-clone provider supports ElevenLabs when
  `VIDEOWFLOW_VOICE_CLONE_PROVIDER=elevenlabs` and `ELEVENLABS_API_KEY` are
  configured. Profiles upload server-local reference samples, store the consent
  reference and provider voice id, and can synthesize audio.
- **`voice.clone` step.** It consumes the fact-check repair text and an approved
  profile, writes `audio/voice-patch.mp3`, and `voice.patch` prefers a human WAV,
  then the cloned MP3, then TTS.
- **Lamera voice repair path.** The fact-check form accepts a clone profile id;
  the recipe adds the clone step before the repair splice.

## [2.67.0] - 2026-11-12

### Added

- **YOLO eye-contact backend.** `vision.face_contact` accepts `backend=yolo`
  with a local `yolo_model` path and `yolo_confidence`, using the largest
  detected face box and the same center/size checks. MediaPipe remains the
  preferred automatic backend; OpenCV and the HILT audit remain fallbacks.

## [2.66.0] - 2026-11-12

### Added

- **MediaPipe eye-contact backend.** `vision.face_contact` now prefers MediaPipe
  Face Mesh when installed, using eye aspect ratio and face centering, then
  falls back to the OpenCV Haar path. `backend` accepts `mediapipe`, `opencv`,
  `auto`, or `none`; the HILT audit remains the fallback.

## [2.65.0] - 2026-11-12

### Added

- **Concurrent scoped research.** Research steps that share the same dependency
  set now execute as one parallel group. Each agent keeps its own context and
  checkpoint; the parent merges dossiers, hashes, ports, warnings, and the
  aggregate agent manifest under a lock. Lamera's four scopes use this path.

## [2.64.0] - 2026-11-12

### Added

- **Transcription resume.** The transcribe step checkpoints complete segments
  keyed by the PCM digest. A restart trims the WAV tail and resumes from the
  absolute sample offset instead of redoing the whole recording.
- **Entity extraction quality.** `entities.extract` resolves single-word names
  from the edition script, captures quoted event/object phrases, and accepts
  `known_entities` hints alongside the existing phonetic corrections.
- **Style-guide audio direction.** Compose, Foley, and mix read the approved
  style guide for BPM, key, Foley kinds, and the SFX notch.
- **License expiry blockers.** `AssetCandidate.expires_at` is preserved in the
  ledger, and expired clearances block audit, review, and export.
- **Transcription ETA.** The transcribe log estimates runtime from duration,
  model, and device before the Whisper pass starts.

## [2.63.0] - 2026-11-11

### Added

- **Lamera workspace.** A dedicated Produce tab with recent runs, six phase
  progress bars, the current HITL gate, gate history, logs, and run controls.
- **HITL inbox and previews.** Pending gates are listed across Lamera runs, and
  gate artifacts with video or image media render inline.
- **Canvas group editor.** Recipe settings can create a group from the current
  node selection, add selected nodes, edit label/description/colour, and remove
  groups.
- **Recipe-filtered jobs.** `GET /api/v1/jobs?recipe_id=` filters the run list
  used by task workspaces.
- **Unit target merge.** `storyboard.units` accepts `target_units`; Lamera
  merges the script sections into 225 units.

### Fixed

- A terminal job finalizer can no longer rewrite a store entry that was already
  pruned, which removes a race in history pruning.

## [2.62.0] - 2026-11-11

### Added

- **Lamera Video Edit.** A new built-in, favorite long-form recipe with four
  scoped research nodes, presenter profiling, separate narration and edition
  approvals, decoupage and entity audits, placeholder previews, licensed asset
  harvesting, motion/Foley, fact-check, voice repair, and final NLE export.
- **Recipe canvas groups.** Recipes can store colored group areas with a label
  and description. The new recipe is organized into six production phases.
- **Split narrative steps.** `transcript.blocks` now owns context chunking and
  `entities.extract` owns people, objects/locations/events, and metric
  extraction. `narrative.beats` remains available for existing recipes.
- **Placeholder previews.** `storyboard.preview` renders four representative
  clips for composition review before the expensive media pass.

### Changed

- Research agents merge the aggregate manifest, so four independent research
  nodes keep one complete `research/agents.json`.
- `presenter.profile` accepts sample paths from the HILT brief.
- `style.guide` records the audio direction, and `audio.mix` supports the
  configurable SFX notch used by the Lamera audio profile.

## [2.61.3] - 2026-11-11

### Fixed

- **Provider connection tests.** The provider editor now shows validation and
  connection errors inline instead of silently stopping when the request fails.
- **Actionable provider failures.** HTTP 401/403, 404, 429, 5xx, and network
  failures now explain what happened and what to check. The raw provider
  response stays available in a details block.
- **Transient test keys.** A key pasted in Secret value can be tested without
  saving it. The result says whether the key came from the form, the
  environment, or the saved secret.
- **Input validation.** Base URL, secret environment name, and the chat model
  are checked before the test call.

## [2.61.2] - 2026-11-11

### Fixed

- **Transcription progress.** Faster-Whisper reports progress per segment, so
  the job bar and node progress move during long transcriptions instead of
  staying at 30% until the step ends.
- **Cancellation and orphaned runs.** Cancelling or removing a running job now
  stops the transcription at the next segment. Previously the worker kept
  running and consumed CPU after the job was gone.
- **Job heartbeat and persistence.** Running jobs renew their lease and persist
  status, stage, and progress during long steps, so a restart no longer sees a
  queued/0% job after a long transcription.
- **Duplicate runs.** A second job for the same source and output is rejected
  while another one is running, queued, or paused.
- **Stale job polling.** The UI treats a missing job as no longer available
  instead of showing a backend 404, and background polling no longer raises a
  notification.
- **CPU model guidance.** Transcribe warns when a large Whisper model is
  selected on CPU.

## [2.61.1] - 2026-11-11

### Changed

- **Internal refactors.** Split `application/retakes.py` and
  `steps/research.py` into packages with unchanged public APIs, prompts,
  artifacts, and behavior.
- **Notifications.** The default UI level is `minimal`: HITL, finished jobs,
  and blockers only.

## [2.61.0] - 2026-11-11

### Added

- **Unified intelligence layer.** OpenCode V2, DeepSeek, and any
  OpenAI-compatible provider behind one task router, with JSON validation,
  fallback, telemetry, budgets, and deterministic fallbacks.
- **LLM virality scoring.** `shorts.score` supports heuristic, LLM, and hybrid
  modes with score, arc, and justification.
- **LLM social metadata.** Titles, descriptions, and hashtags per platform with
  deterministic fallback.
- **OpusClip-style recipes.** `opusclip_auto_shorts`, `opusclip_auto_broll`,
  and `opusclip_nle_bridge` map the OpusClip workflow onto native VideoFlow
  steps, with a parity matrix in `docs/opusclip-parity.md`.
- **Curation controls.** `virality_threshold`, per-Short hook/development/
  climax/CTA arc labels, and curation provenance in `shorts.json`.
- **Voice isolation.** Optional `audio.isolate` step with RNNoise,
  DeepFilterNet, and Demucs backends, plus `transcribe.audio_source`.
- **Dynamic reframe.** Smoothed crop keyframes, backend selection, and
  split-screen/PiP layout parameters in `shorts.reframe`.
- **Caption presets.** Hormozi, Beast, clean-white, and podcast-speaker
  presets, with preset application in captions and render steps.
- **Synthetic B-roll.** `broll.generate` writes generated images to the asset
  library and to the license ledger.
- **EDL and social metadata.** CMX 3600 export and
  `delivery/social_descriptions.json` per platform.
- **Forced alignment and dynamic crop.** Optional WhisperX/faster-whisper word
  alignment, per-frame FFmpeg crop expressions, and optional MediaPipe/YOLO
  face centers with motion fallback.
- **LLM chapter titles and caption presets.** `chapters.plan` can name
  chapters, and the caption preset gallery gained Hormozi/Beast/clean styles.
- **Notification levels.** UI notifications default to HILT, finished jobs,
  and blockers; `minimal`, `standard`, and `verbose` are configurable.
- **Refactors.** Caption building moved to `application/captions.py`; the
  intelligence provider logic is centralized in `application/intelligence/`.

All notable changes are recorded here. Format follows Keep a Changelog; versions
follow semantic versioning once the project reaches 1.0.

## [2.60.0] - 2026-11-09

### Added

- **Human-in-the-loop (HILT).** Durable interactions under
  `output/hilt/<interaction_id>/`, typed questions, file handoffs, review
  artifacts, local notifications, and new `human.input` / `human.files` steps.
- **HILT API and job state.** `waiting_input` jobs, interaction inspection,
  answer/upload endpoints, artifact downloads, and a pending-interaction feed.
- **Full AI Editor recipe.** `full_ai_editor` is built in and favorited by
  default; it pauses for the brief, research, script, decoupage, entity, style,
  sample, fact-check, and final gates.
- **Studio HILT panel.** The recipe and job views render questions, file
  uploads, review artifacts, and approve/reject actions without leaving the app.
- **External HILT channels.** E-mail (SMTP/IMAP), Slack (webhook/bot + polling
  and optional Events API), and Signal (signal-cli REST) send requests, accept
  replies and attachments, enforce sender allowlists, and record per-channel
  delivery failures without failing the job.
- **MCP HILT tools.** `videoflow_list_interactions`,
  `videoflow_get_interaction`, and `videoflow_respond_to_interaction` (74 tools).
- **Research and dual-script engine.** Local/SearXNG/Wikipedia/Internet Archive
  providers, citation manifests, scoped `research.multi_agent`,
  `research.consolidate`, `presenter.profile`, and `script.dual_output`; the
  Full AI Editor now generates research and script before the ingest phase and
  keeps optional human correction gates.
- **Vision and decoupage.** `vision.face_contact` green labels (optional OpenCV),
  XMEML/FCPXML reference calibration, frame-accurate `speech-map.json`, and
  human entity corrections applied by `entities.apply`.
- **Art direction and licensed assets.** `style.guide`, `storyboard.units`,
  `assets.discover`, `assets.harvest`, `assets.license_audit`, and
  `assets.assign`; Pexels/Pixabay/Openverse/Wikimedia/Internet Archive and
  short fair-use YouTube excerpts; explicit `assets/licenses.json` ledger and
  export blocking until the review gate approves.
- **Motion, audio, and intro.** `motion.codegen`/`motion.render` with an FFmpeg
  backend, NLE overlay manifests, procedural music and Foley with a final
  dialogue/music/SFX mix, and `intro.compile` for the high-retention opening.
- **Fact-check and voice repair.** `factcheck.audit` with citation validation,
  a HILT correction gate, optional TTS or uploaded voice patches, and the final
  approval/export checkpoint.

### Verified

- 1,780 Python tests, 87 Vitest, 90 Playwright; configured gate coverage 98%.
- Full-tree coverage 93.52% line (27,042/28,916), 91.41% with branches.
- Local gate green: `ruff`, unit/contract, fault injection, media, layer
  coverage, UI unit/static, E2E, and packaging smoke.

## [2.59.4] - 2026-11-09

### Changed

- **Central typed-error handling.** `api/errors.py` owns the HTTP status map and
  the app installs one `VideoFlowError` handler. Removed 120 repeated
  `try/except VideoFlowError` blocks from `routes.py` (5,289 → 4,717 lines).
- **Asset, discovery, preset, job, timeline, recipe, and system routes extracted.**
  `api/routes_assets.py` owns music, SFX, image, and font upload/list/delete;
  `api/routes_discovery.py` owns node options, capabilities, steps, and the
  recipe list; `api/routes_presets.py` owns node presets and global presets;
  `api/routes_jobs.py` owns the 16 job lifecycle, query, event, variant, DAG,
  and log routes; `api/routes_timeline.py` owns the 26 timeline edit, metadata,
  snapshot, overlay, comment, track, and waveform routes plus the shared
  timeline helpers; `api/routes_recipes.py` owns recipe CRUD, validation,
  history, dry-run, and run routes; `api/routes_system.py` owns system status,
  doctor, support bundle, backup, restore, metrics, and maintenance routes.
  `routes.py` drops from 5,289 to 2,761 lines and the `register_*` pattern is
  established for the remaining domains.
- **UI API client extracted.** `ui/src/lib/api/client.ts` owns `ApiError`,
  `request`, and error formatting; `api.ts` drops from 2,984 to 2,833 lines
  while preserving every public import.
- **MCP surface hardened.** The registry is now the single source of truth for
  tool names and descriptions; annotations are passed through the public
  `@mcp.tool(annotations=...)` API instead of mutating the SDK's private tool
  manager. Corrected 20+ public descriptions, including provider readiness
  versus secret presence, and added contract tests that every registered tool
  matches its registry description and carries annotations.
- `videoflow_list_jobs` now returns `total` and clamps `limit`/`offset` like the
  other paginated list tools.
- **Complete status mapping.** Added the missing codes for transcription,
  retakes, approval, schema migration, capability, rendering, and external
  policy failures so they no longer fall back to 400.
- **Documentation reconciliation.** README, testing, blockers, MCP, exporters,
  ingest, UI spec, voice clone, and the historical PRD now match 2.59.4:
  current test counts, 71 MCP tools/5 resources, FCPXML markers, the manual
  GitHub Actions fallback, and the ignored ingest/proxy knobs.
- **Concurrent history writes.** `engine/history.py` uses a per-process,
  per-thread temporary file, so two jobs writing run history cannot delete each
  other's temp file.
- **History write failures.** A job whose output is unwritable still fails
  cleanly; the history write is logged instead of raising on the worker thread.

### Removed

- **Legacy job execution path.** Removed `POST /api/v1/jobs`, the 127-field
  `NewJobRequest`, `application/portable.py`, `JobManager._run_legacy`, and the
  `runner` injection. Recipe jobs are the only execution path.
- **Legacy CLI demo.** Removed `videoflow demo`, which existed only to exercise
  the portable pipeline.
- **Legacy staged MCP tools.** Removed `videoflow_run_vad`,
  `videoflow_transcribe`, `videoflow_cull_retakes`,
  `videoflow_configure_zooms`, `videoflow_apply_jcuts`,
  `videoflow_generate_shorts`, and `videoflow_run_pipeline`. The MCP surface is
  now 71 tools; `videoflow_run_recipe`, `videoflow_run_recipe_inline`, and
  `videoflow_run_step` are the supported execution tools.
- Removed the legacy-specific tests and adapted the remaining job tests to
  recipe jobs through `tests/recipe_jobs.py`.

### Verified

- 1,685 Python tests, 87 Vitest, 90 Playwright; gate coverage 98%.
- Full-tree coverage 95.14% line (23,429/24,627), 93.45% with branches.

## [2.59.3] - 2026-11-09

### Changed

- **Premium shell.** A branded logo and app icon, PWA manifest, theme-color and
  social metadata, an ambient studio backdrop, a live document title, and a
  service status dot.
- **First-run and empty states.** The guide modal gained a progress rail, step
  icons, a local-only badge, and a skip action; empty states gained a branded
  icon and an optional shortcut hint.
- **Status and startup feedback.** Running jobs pulse in the header, status
  badges carry a colored dot, and the startup card shows unpack/FFmpeg/API
  progress.
- The AppImage now ships `packaging/videoflow.png` as its default icon.
- **Compact mobile shell.** Area tabs keep their labels, header actions become
  icon-first, the service restart/stop controls move to the command palette,
  and the recipe toolbar folds secondary actions into More on narrow screens.
- **Mobile builder height.** The recipe canvas uses a shorter viewport on
  phones, so the graph and footer are reachable without a long scroll.
- Media empty state now uses the shared branded empty state.
- Changing tabs scrolls to the workspace top and announces the new area/tab
  through a polite live region.

### Fixed

- **Mobile navigation overflow.** Sub-tabs now scroll inside their own row
  instead of widening the page; the page no longer gains a horizontal
  scrollbar on Setup.
- **Settings resilience.** A partial settings payload no longer crashes the
  panel while reading `allowed_roots`.

### Verified

- 1,704 Python tests, 87 Vitest, 90 Playwright, and 0 svelte-check errors.
- Gate coverage 98% (application 94.26%); media and fault-injection tests pass.
- `SHA256SUMS` verified; both Linux artifacts report `videoflow 2.59.3`.
- AppImage 2.59.3 serves the studio at `127.0.0.1:8765` with the
  `videoflow-data` copied from 2.59.2.

## [2.59.2] - 2026-11-08

### Changed

- **Job lifecycle unified.** `JobExecutor` owns running/retry/cancel/approval,
  persistence, finalizer, and queue draining; the legacy pipeline and recipe
  runner are adapters. `jobs.py` drops from 1263 to 1081 lines.
- **Shared text helpers.** `application/text.py` now owns normalization,
  tokenization, token sets, and content tokens for retakes and takes.
- **Shared file stores.** `application/asset_store.py` owns music/SFX listing
  and saving; limits and suffixes stay local.
- **Shared primitives.** `clock.py`, `spans.py`, `files.py`, and
  `retake_spans.py` replace duplicated helpers.
- **Content steps split.** `steps/content.py` is 308 lines; audio and visual
  steps live in `content_audio.py` and `content_visual.py`.

### Verified

- 1,690 Python tests, 87 Vitest, gate green, full-tree line coverage 98%.
- New modules: `job_executor` 99%, `asset_store` 100%, `text` 100%,
  `spans` 100%, `files` 100%, `content_audio` 100%, `content_visual` 100%.

## [2.59.1] - 2026-11-07

### Fixed

- `autonomous_studio_master` now defaults `drift_offset_ms` to 0 and exposes it
  as a recipe variable. The 200 ms value remains available for sources with a
  real camera/audio buffer latency; applying it blindly shifted every cut.
- Narrative beats run after retakes and cleanup, so duplicated takes no longer
  appear in the context blocks.

## [2.59.0] - 2026-11-07

### Added

- **Autonomous studio master recipe** (`autonomous_studio_master`): drift
  correction, deterministic de-talking, narrative beats and entities, local
  B-roll planning, audio mastering and ducking, XML/MP4 export, and QA.
- **`edit.drift`**: subtracts the camera/audio buffer offset from every word and
  sentence, with zero-clamping and a drift report.
- **`narrative.beats`**: splits the cleaned transcript into 100–300-word context
  blocks, assigns Hook/Context/Conflict/Turning Point/Proof/Payoff, and extracts
  people, objects, metrics, and locations. LLM is optional and off by default.
- **`broll.plan_master`**: matches local assets to narrative blocks for the
  long-form master, without changing the Shorts B-roll flow.
- **`audio.duck`**: FFmpeg sidechain ducking for a music bed, with a safe no-op
  when no music is configured.
- **`rules.memory`**: appends and consolidates `agents.md`/`claude.md` rules.
- **Phase-2 shells**: `motion.render` and `qa.vision` are registered and
  bypassed, so the recipe shape is ready for the renderer and vision QA.
- `export.nle` now tolerates empty artifact entries.

### Verified

- `autonomous_studio_master` ran end-to-end on a 2-minute alertaClaude clip and
  produced MP4 + FCPXML + Premiere XML + Kdenlive, narrative beats, drift
  report, B-roll plan, audio master/QA, and rulebooks.
- Gate: 1,682 Python tests, 87 Vitest, line coverage above 95%.

## [2.58.9] - 2026-11-05

### Added

- **Audio-event classifier infrastructure.** `application/audio_events.py`
  extracts 38 features (duration, RMS, ZCR, flatness, harmonicity, spectral
  centroid/rolloff/flux, low-band ratio, onset, and 26 MFCC statistics), trains
  a pure-numpy logistic-regression model, and scores candidate bursts. A model
  is only used when its recorded precision and recall are at least 0.5.
- **Weak-label training script.** `scripts/train_audio_events.py` builds
  positives from short internal cuts in the human EDL and negatives from kept
  regions.
- **Reference EDLs** for alertaClaude, brave, and gpt6.2astra, in addition to
  Kimi.
- **Optional filler removal** (`remove_fillers`, default off) for isolated
  non-lexical fillers.

### Changed

- The default recipe keeps `use_audio_event_model=false` and
  `remove_fillers=false`: the weak labels available today are not separable
  enough to beat the heuristic, and removing fillers reduced audio F1 by
  2.2 points on Kimi.
- Default timeline behaviour is unchanged from 2.58.8.

### Verified

- 2.58.8 reference results remain the best: Kimi 0.8091, alertaClaude 0.8152,
  brave 0.7997, gpt6.2astra 0.8393 (mean 0.8158).
- Weak-label classifier on the four cases: test precision 0.10, recall 0.44;
  correctly rejected by the quality gate.
- Gate: 1,675 Python tests, 87 Vitest, line coverage above 95%.

## [2.58.8] - 2026-11-05

### Added

- **Word-timing refinement.** `application/alignment.py` clamps every word to
  the VAD speech region that contains its midpoint, caps tokens stamped across
  seconds of audio to a believable duration, and snaps adjusted edges to nearby
  low-energy valleys. This runs after transcript normalization and before
  retakes, so every downstream decision sees usable word boundaries.
- The refinement reports how many words were clamped, snapped, and how many
  implausible timings remain.

### Verified

- Four reference cases: Kimi 0.8091, alertaClaude 0.8152, brave 0.7997,
  gpt6.2astra 0.8393 audio F1 (mean 0.8158, up from 0.8054 in 2.58.7).
- Max word duration on Kimi dropped from 18.2 s to 1.57 s.
- Word cuts: Kimi 6, alerta 6, brave 5, gpt 32.
- Gate: 1,673 Python tests, 87 Vitest, line coverage above 95%.
- The 98% target still needs a trained audio event classifier and a learned
  take scorer; timing is no longer the main blocker.

## [2.58.7] - 2026-11-05

### Added

- **Take-level selection.** `application/takes.py` segments consecutive
  sentences into takes at pauses and restarts, groups duplicate takes, and
  discards an earlier attempt only when the later take preserves its numbers,
  URLs, and most content words. The deterministic take engine is now the
  primary retake decision; the LLM remains an optional tie-breaker.
- **Word-integrity invariant.** `application/boundaries.py` checks that every
  kept word is fully inside one kept span. A split word is merged when the gap
  is small; unfixable cases are reported in `metadata["word_integrity"]`.
- **Voicing-aware noise detector.** Impulsive noise classification now also
  measures harmonicity, so a low-frequency throat clear is removed while a
  voiced syllable is preserved.
- **Reproducible LLM calls.** OpenAI-compatible requests send `seed=42` when the
  endpoint supports it.

### Changed

- Near-duplicate clustering now looks across 300 s instead of 90 s, which
  catches restarted passages later in the recording.
- The builtin recipe keeps `provider_id=""` for retakes: deterministic take
  selection is the default, and the LLM can still be enabled per recipe.

### Verified

- Four reference cases, deterministic take engine: Kimi 0.7847,
  alertaClaude 0.8000, brave 0.7968, gpt6.2astra 0.8402 audio F1 (mean
  0.8054, stable across repeated runs; 2.58.6 mean was 0.8093 but varied by
  up to 4 points between identical LLM runs).
- Word cuts: Kimi 7, alerta 4, brave 8, gpt 29 (2.58.6: 11/6/11/35).
- Word-integrity violations after repair: 8/0/3/0 in the four cases.
- Gate: 1,669 Python tests, 87 Vitest, line coverage above 95%.
- The 98% target still requires forced alignment and a trained audio event
  classifier; this release removes LLM variance and protects word boundaries.

## [2.58.6] - 2026-11-05

### Added

- **ASR loop removal.** An identical line repeated four or more times at a
  regular interval is treated as a Whisper hallucination loop and removed
  entirely instead of keeping one copy.
- **Watermark credit removal.** Subtitle credits such as "Legendas pela
  comunidade de Amara.org" are dropped when they carry no other content; a
  sentence that also contains real words is preserved.
- **Opt-in word-tail repair.** `repair_word_tails` extends capped spans back to
  the end of a plausible word (default off because it adds low-energy tails).

### Changed

- Silence capping is unchanged; the word-tail repair is available per recipe
  and disabled by default to keep the silence profile tight.

### Verified

- Four reference cases re-rendered with the 2.58.6 recipe: Kimi 0.7752,
  alertaClaude 0.7958, brave 0.8174, gpt6.2astra 0.8487 audio F1 (mean
  0.8093 vs 0.8041 for 2.58.5; brave +2.8 points).
- Gate: 1,659 Python tests, 87 Vitest, line coverage above 95%.
- The 98% target still requires take-level selection and a trained audio event
  classifier; this release removes two concrete transcript-noise classes.

## [2.58.5] - 2026-11-05

### Added

- **Head/tail energy guard.** Kept spans now extend to the nearest low-energy
  valley (80 ms head, 160 ms tail, speech-like threshold) instead of stopping
  at the ASR word timestamp. This protects word onsets and tails without
  adding a blanket pad to every clip.
- **Impulsive non-speech detector.** Short high-energy broadband bursts
  outside every kept word (coughs, throat clears, clicks) are removed; bursts
  that overlap a word with an 80 ms margin are preserved.
- **Unique-content retake guard.** A discarded sentence is restored when it is
  not a near-duplicate of the keeper and contains content words that appear
  nowhere in the kept transcript.
- **Longer/phrase stutters.** Repeated words with up to 900 ms inside the same
  sentence and 2–3 word phrase stutters are cut; stutters are exempt from the
  20% word-cut budget.
- **Optional untranscribed recall.** `keep_untranscribed` can add long
  speech-like VAD regions missing from the transcript; it is off by default
  because it can also keep non-speech.

### Changed

- Hard-cut audio fades/crossfades are 10 ms and the timeline keeps the 60/120
  ms pads plus the new energy guard.
- The saved cut recipe keeps `keep_untranscribed=false` for precision; the
  recall mode remains available per recipe.

### Verified

- Four reference cases re-rendered: Kimi 0.7876, alertaClaude 0.7964,
  brave 0.7894, gpt6.2astra 0.8430 audio F1.
- Impulsive events removed: Kimi 9, alerta 7, brave 5, gpt 0.
- Word-tail median 123–133 ms; non-speech and content-preservation fixes are
  in place, but the 98% target still needs take-level editing and forced
  alignment.
- Gate: 1,631 Python tests, 87 Vitest, 95.01% line coverage.

## [2.58.4] - 2026-11-05

### Added

- **Timestamped export names.** `export.nle` and `export.video` now default to
  `filename_mode="source_timestamp"`, producing
  `<source>_VideoFlow_Edited_<yymmddhhmmss>.<ext>`. Collisions add `_1`, `_2`
  before the extension. Fixed names remain available with
  `filename_mode="fixed"` plus `basename`/`filename`.
- UI fields `Naming`, `Fixed base name`, and `Fixed filename` for both export
  nodes.

### Changed

- Timestamped exports bypass checkpoint reuse so each run writes a new file;
  fixed-name exports remain cacheable.
- NLE validation and `/api/v1/exports/validate` discover timestamped exports in
  addition to the legacy `timeline.*` names.
- The exported NLE files share one timestamped basename across
  `.fcpxml`, `.xml`, and `.kdenlive`.

### Verified

- Gate: 1,624 Python tests, 87 Vitest, 95.03% line coverage.
- Four reference outputs kept for review with the new naming convention:
  Kimi, alertaClaude, brave, and gpt6.2astra.

## [2.58.3] - 2026-11-05

### Added

- **Word-level repeat cuts.** Stutters (1–3 words), prefix/tail retakes,
  fuzzy restatements, and local 5–8 word n-grams now cut only the duplicated
  words and keep the last complete occurrence. Unique words, numbers, and URLs
  are protected; the pass is capped at 20% of the kept words.
- **Offline calibration tools.** `scripts/build_reference_edl.py` builds an
  audio-aligned reference EDL from a raw/edited pair, and
  `scripts/cut_eval.py` measures final-audio similarity, cut/word agreement,
  word-tail safety, silence, loudness, spectral balance, clicks, and sponsor
  recall. Both are offline only.
- **`cut_eval --reference-video`** for audio-only comparison when no EDL is
  available.

### Changed

- **Default ASR is faster-whisper large-v3.** The recipe uses
  `faster-whisper-large-v3` when installed, with the small model as fallback.
  Weights live in `~/.videoflow/models` and survive release upgrades even when
  a portable home is configured.
- **Large-v3 catalog fixed.** Downloads use `vocabulary.json` and
  `preprocessor_config.json` (128 mel bins); the old `vocabulary.txt` URL does
  not exist for this model.
- **Timeline pads are 60/120 ms** and the local repeat window is 120 s. The
  word-tail median rose from 46.7 ms to ~123–127 ms.
- The doctor now creates the portable home before checking disk usage.

### Verified

- Reference pairs: Kimi, alertaClaude, brave, gpt6.2astra.
- large-v3 vs small: alerta 0.7945 vs 0.8059; brave **0.7868 vs 0.6959**;
  gpt **0.8559 vs 0.5543**. Kimi small improved from 0.7749 to 0.7816 with the
  word-level pass.
- Word-tail cuts (<60 ms) fell from 177 on the old Kimi small run to 3–35 on
  the new videos.
- Gate: 1.632 Python tests, 87 Vitest, 95.02% line coverage.

## [2.58.2] - 2026-11-04

### Added

- **Audio silence cap.** The timeline now measures silence on the PCM (10 ms
  frames, -35 dB, 100 ms minimum) and caps runs above `max_silence_ms` while
  retaining `keep_silence_ms` of natural pause. Defaults: 500 ms / 300 ms,
  matching the human reference. This removes silence hidden inside broad word
  timestamps, not just gaps between words.
- **Context cleanup node (`llm.cleanup`).** A conservative pass removes only
  clear out-of-context asides such as a remark about a fly, with before/after
  context. Sponsor, pricing, links, CTAs, sign-offs, and unique content are
  protected deterministically.
- **Repeated-passage cuts.** Exact repeated 5+ word passages keep the last
  occurrence and remove only the earlier occurrences, preserving content
  between them. Repeats further apart than the configured window are treated
  as callbacks and kept.
- **Safer retake keeper.** Chooses the most complete, clean sentence instead of
  the last tail. Sponsor/CTA, unique numbers, and proper names in a discarded
  sentence are restored. Exact repeats are resolved deterministically.

### Changed

- The cut-first DeepSeek recipe is
  `retakes → llm_cleanup → timeline → export`; `llm.zoom` and `llm.style`
  remain separate nodes and are disabled until the cut phase is finished.
- Retake/timeline checkpoints bumped for the new keeper and silence logic.

### Verified

- Real Kimi.mp4 run: **14:42**, **188.9 s silence** vs **189.8 s** in the human
  reference, maximum silence 0.62 s vs 0.51 s, 238 clips, zero no-word clips.
- The 24 s aborted phrase is split into the prefix plus the final take.
- 44 retake discards, 3 cleanup removals, 8 repeated-passage cuts, 18 unique
  sentences restored.

## [2.58.1] - 2026-11-04

### Fixed

- **Internal silence and repeated restatements.** Transcript normalisation now
  prefers the later occurrence when consecutive ASR segments overlap, so a
  restated phrase keeps the final take instead of the aborted one.
- Kept sentences are split into word runs. Gaps above `max_internal_gap_ms`
  are removed, including coughs, throat clearing, and pauses inside a sentence.
  The default is 150 ms; `internal_gap_mode` can remove all no-word gaps or only
  low-energy silence.
- Default pads are tighter: 20 ms before and 40 ms after speech, configurable
  per timeline.
- Isolated word runs that are not part of a complete passage are dropped as
  fragments, with a report entry.

## [2.58.0] - 2026-11-04

### Added

- **Retakes v2.** The transcript is normalised into complete sentences, the
  LLM receives the full context in one request, and it returns keep/discard
  groups instead of a flat list. Deterministic guards restore unique content,
  reject oversized groups, and fall back to fuzzy near-duplicate clustering
  when no LLM is configured.
- **`llm.zoom` and `llm.style` nodes.** Zoom and style now have focused prompts
  and separate reports. The DeepSeek recipe uses `llm_zoom → llm_style` and no
  longer lets one node cut, zoom, and style at the same time.
- **Transcript-span timeline.** Kept sentences become the edit units, so VAD
  tails and fragments of discarded takes no longer reach the render.
- **Noise filter.** VAD intervals or sentences without speech words, subtitle
  watermarks, and (optionally) ellipsis-only material are removed as
  non-destructive `noise` segments.
- **Retake review panel.** The step-output viewer renders each retake group
  with the kept and discarded text, timestamps, and reason.

### Changed

- `llm.timeline` now defaults to style/zoom only; cut actions require
  `allow_cuts=true`.
- Retake cuts are snapped into nearby silence, and timeline pads are clamped to
  the midpoint between sentences so joined words never overlap.
- The zoom renderer oversamples before `zoompan`, aligns crop pixels, supports
  intermediate keyframes, and uses stable `scale`+`crop` for punch-ins.
- Provider `api_key_env` must be a variable name, and per-provider tests resolve
  that provider's saved secret.

### Verified

- Real Kimi.mp4 run: **123 complete sentences, 20:51**, zero active noise
  segments, 24 retake discards, and 12 content-aware zooms.

## [2.57.1] - 2026-11-04

### Fixed

- **`llm.timeline` now produces an exportable timeline.** Edits are applied
  against the original timeline and gaps left by `delete`, head/tail `trim`,
  and `move` are closed once at the end. The step reports `normalized`,
  `gaps_closed`, `closed_frames`, and `closed_seconds`, and emits a warning.
  This fixes the `Video timeline is not packed from frame zero` failure at the
  MP4 export.
- LLM `trim`/`crop_in`/`crop_out` ranges outside the target clip are rejected
  instead of cutting a neighbouring clip or extending the source.
- The MP4/NLE exporter error now names the first gap, for example
  `first gap at frames 0-24`.
- Provider `api_key_env` accepts only an environment variable name. Pasting a
  literal API key into that field is rejected with an actionable message.
- A saved provider's **test** action now resolves that provider's own secret
  variable; previously it looked up the generic `VIDEOWFLOW_LLM_API_KEY`.
- `deepseek_full_edit` no longer leaves 66 ripple gaps after deleting filler.

### Notes

- With the same DeepSeek response that failed before, the edited timeline
  re-packs to 196 clips and 885.48 s (14:45), contiguous from frame zero.
- Rotate any API key that was previously pasted into the `api_key_env` field;
  that field is not secret storage.

## [2.57.0] - 2026-11-04

### Added

- **`llm.timeline` recipe step.** The configured LLM can propose and the engine
  can apply trim/crop in/out, move, split, delete, ripple, slip, slide,
  duplicate, transitions, fades, scale, position, zoom, and zoom keyframes.
  Unsupported or invalid actions are rejected and reported.
- **`deepseek_full_edit` built-in recipe**, marked favorite. It transcribes,
  removes retakes with DeepSeek, applies timeline edits with DeepSeek, and
  exports NLE plus MP4.
- Provider presets for DeepSeek, OpenAI, Ollama, and OpenRouter.
- Provider connection testing now supports both model listing and a real chat
  completion, with latency and secret status.

### Changed

- Provider setup is clearer: the editor opens on **edit**, the ID is locked while
  editing, secrets can be set inside the editor, readiness and missing fields are
  visible, and each saved provider has a test action.
- Timeline checkpoint fingerprints now include a manual state revision above 1,
  so a newer manual timeline invalidates the cache and the rebuild is written.
- The `deepseek_full_edit` recipe uses explicit per-port wiring with the
  `llm.timeline` node.

### Verified

- Real Kimi.mp4 test:
  - with retakes: **17:07**, 340 clips;
  - without retakes: **19:05**, 312 clips.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.56.0] - 2026-11-03

### Fixed

- Every input and output port now renders its own connection handle. Nodes can
  receive multiple inputs on different ports and expose multiple outputs, and
  edges carry the exact `sourceHandle`/`targetHandle`.
- Recipe rebuilds now replace a newer manual timeline explicitly:
  `edit.timeline` bumps above the current revision, persists the new state, and
  records a warning. The **Replace manual timeline edits** toggle can disable
  this behavior.
- The legacy `requires_by_type` check no longer rejects explicitly wired steps
  (for example Retakes fed through a junction); port validation remains the
  source of truth.

### Verified

- Real test with `/home/rafael/Desktop/Kimi.mp4`:
  - **with Retakes:** 340 clips, **17:07**;
  - **without Retakes:** 312 clips, **19:05**;
  - retake inactive segments: 97, discarded sentence ids: 399;
  - the result is written to `project_state.json`, not only to the step output.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.55.0] - 2026-11-03

### Fixed

- Recipe edges are now created per port instead of one aggregated edge per
  source/target pair. `retakes.speech → timeline.speech` and
  `retakes.retakes → timeline.retakes` appear and open independently.
- Connecting a new source to an occupied input replaces the old edge, so two
  green edges can no longer claim the same input while only one is applied.
- The wire dialog lists the target's current input bindings and can disconnect
  a single binding.
- Added a regression test proving Retakes changes the final timeline compared
  with the same recipe without Retakes.

### Added

- `flow.junction`, a concentrator node with eight `any` inputs and one `any`
  output. It can pass a selected input, merge lists, or merge dictionaries.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.54.0] - 2026-11-03

### Added

- The Transcribe node now exposes an **ASR model** selector populated from models
  installed in Setup → AI models. Only installed ASR models are listed, with a
  direct setup link when none exists.
- `model_id` resolves to the installed model path. Faster-Whisper models use the
  Faster-Whisper adapter; whisper.cpp models use the CLI adapter.
- Automatic mode now considers every installed Faster-Whisper size and installed
  whisper.cpp models instead of only `small`.
- Selecting an ASR provider forces HTTP transcription, and settings defaults can
  seed the installed model automatically.

### Changed

- Provider-specific fields are now conditional. In Transcribe, HTTP fields only
  show for HTTP without a provider; whisper.cpp paths only for that mode; model
  size/device/compute/VAD only for local Faster-Whisper; SRT path only for SRT.
- Speaker turns only shows pyannote fields for `method=pyannote`, and heuristic
  fields otherwise.
- Dubbing hides manual TTS endpoint fields when a configured provider is chosen.
- When an explicit ASR model is selected, `model_size` remains visible but
  disabled.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.53.0] - 2026-11-03

### Changed

- The inspector's **Effects** tab now owns the clip effect controls:
  transitions, duration, scale, position, fades, copy/paste style, batch
  style, reset transform, and the selected-clip summary.
- **Inspect** keeps the selected clip identity, trim/move, inactive segments,
  captions, markers, comments, and overlays.
- The Effects tab still reserves space for future colour, blur, crop, and mask
  effects.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.52.0] - 2026-11-03

### Added

- Every node's Outputs panel now has an **Inspect** button that opens its
  persisted step outputs directly.
- The step-output viewer can copy the selected port as JSON.
- The viewer can open a second step side by side with an independent port
  selector, so two steps can be compared without leaving the builder.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.51.0] - 2026-11-03

### Added

- **Retakes can use a configured LLM per node.** The node now has an optional
  LLM provider selector; without one it keeps the recipe-level LLM and falls
  back to exact-repeat culling. The node explains that it needs a transcript and
  that no LLM means heuristic-only removal.
- Provider-backed node fields show only enabled, configured providers. When a
  capability has no configured provider, the field shows a setup message and a
  link to Setup → Providers instead of an empty list. Incomplete providers are
  reported with their missing fields.
- Per-step outputs are persisted to `work/steps/<step>/outputs.json` for
  executed, cached, and bypassed steps. The API lists ports, returns one port's
  JSON, downloads files, and saves a copy to a chosen folder. The recipe builder
  has an **Outputs** viewer with port tabs and save/download actions.
- The timeline preview shows **Source total**, **Edited**, and **Removed**
  durations.
- A persisted **Follow** toggle scrolls the timeline with the playing cursor.
  When disabled, playback leaves the scroll position untouched.
- The preview can be resized horizontally and vertically, with persisted sizes
  and a reset action.
- The right-side timeline panels now live in a separate inspector widget with
  **Inspect** and **Effects** tabs. Effects is reserved for future clip effects;
  existing transitions, scale, position and fades remain in Inspect.

### Changed

- `doctor` and model metadata continue to use the external model home.
- Recipe LLM settings warn when no configured LLM is available.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.50.0] - 2026-11-03

### Fixed

- **Long timelines no longer render blank.** The Konva stage was as wide as the
  whole timeline, and timelines longer than the browser canvas limit (about
  32k px) rendered a white/empty canvas. The stage is now viewport-sized with a
  sticky drawing surface and a full-width scroll spacer.
- **Seeking no longer rewinds the live player.** The player reset effect ran on
  ordinary parent updates and restored the first segment, so the labels stayed
  at 0 after a seek. It now resets only when the job, source, or segment
  structure changes.
- Segment boundaries now map to the next active segment instead of the previous
  end, so Next segment lands on the correct source time.
- Seeks force a playhead report, so the timeline timecode follows immediately
  even inside the normal 80 ms report throttle.

### Added

- Tests for long-timeline canvas limits, cursor persistence across parent
  updates, boundary mapping, and seek reporting.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.49.0] - 2026-11-03

### Fixed

- **Run to here and scoped validation no longer inspect later nodes.** A broken
  or disabled export after the target step cannot block running to an earlier
  node, and the validate endpoint accepts `?through=<step>`.
- Unknown step ids are reported as `Unknown or disabled step` before port
  validation, instead of surfacing as a generic recipe error.
- Local model registrations and model-download metadata now live in the
  external data home, with a read fallback to the portable `videoflow-data`
  copy. Replacing a release keeps local model definitions and download state.

### Added

- Tests for scoped recipe validation, scoped HTTP and MCP validation, and the
  scoped validate client.
- The MCP `videoflow_validate_recipe` tool accepts an optional `through` step.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.48.0] - 2026-11-03

### Fixed

- **Disabled export nodes no longer block a recipe.** Port validation skipped
  disabled steps, so a disabled `export.video` reported the misleading
  `source timeline must run earlier` error and made MP4 export feel mandatory.
  Disabled steps are now ignored until they are enabled.
- Built-in recipes no longer inject an MP4 export automatically. Add or enable
  `export.video` only when an MP4 is actually wanted.
- Cycle wiring now names the edge that creates the cycle instead of only
  reporting `must run earlier`.
- Timeline edit endpoints accept a JSON string body as well as an object, so a
  stale client that double-encoded `activate`/`deactivate` no longer fails with
  `request_invalid`.
- Split works from the official playhead in Normal and Recut. If the playhead
  is outside a clip, it moves to the middle of the target clip before splitting.
- The Recut cursor and the Normal playhead are one official cursor. Seeking the
  Recut canvas maps source time to output time, and Play always starts from the
  official playhead in both live and rendered previews.
- Fit and Fit selection use the real scroller width and the correct fixed-header
  offset for each view instead of a hardcoded 1200 px.
- The Normal timeline shows a loading skeleton instead of a blank area, and the
  Konva canvas rebuilds when its container size changes.
- Track visible/mute/solo/lock controls now live in the fixed left header in
  front of the tracks, not in the toolbar above the timeline.

### Added

- Optional models are resolved from the external data home, the portable home,
  sibling release folders, and the bundle. New downloads go to the external
  home, so replacing a release no longer requires downloading them again.
- `doctor` reports the preferred models directory and every search path.
- Tests for disabled recipe steps, double-encoded timeline bodies, source/output
  cursor mapping, fit math, model search paths, split in both views, playback
  from a seeked playhead, and track controls.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.47.0] - 2026-11-03

### Fixed

- **Reset transform** now resets only scale and position. It no longer also
  applies the current transition and fade values to the selection.
- Batch style, paste style, and reset transform share one code path, so
  precondition conflicts reload the latest revision instead of leaving a stale
  editor state.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.46.0] - 2026-11-03

### Changed

- Batch style edits now go through one `PATCH /timeline/clips` request instead
  of one request per clip. A batch creates a single revision and a single undo
  entry, and the editor keeps the current selection and playhead after the
  update.
- Unknown clip ids are rejected before any change is written, and duplicate ids
  are de-duplicated.

### Added

- Contract tests for the batch style route covering single-revision undo,
  unknown clip rejection, and empty-selection validation.
- A UI test asserting the batch client sends one PATCH with `clip_ids`.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.45.0] - 2026-11-02

### Fixed

- **Play now actually starts.** The initial Svelte reset effect could run after a
  Play click and pause the video immediately. The reset effect now ignores an
  already-playing source unless the job or source URL changes.
- Added a real WebM playback E2E test that generates a short fixture and asserts
  the playhead advances and Pause takes effect.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.44.0] - 2026-11-02

### Fixed

- `export.nle.targets` exposes its enum again, so the node renders a real
  multi-select with Resolve/Premiere/Kdenlive options.
- When a live proxy is preparing or fails and a rendered preview exists, the
  preview stays playable instead of being replaced by a status panel.
- Request validation errors retain body, endpoint, and field location details.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.43.0] - 2026-11-02

### Fixed

- Live source eligibility now checks the container as well as codecs. H.264 inside
  MKV is sent through the proxy instead of being marked browser-safe.
- Request validation errors now include the endpoint, method, body, and the
  exact Pydantic field location, making `request_invalid` actionable.
- Stabilized the live-source proxy test against the build completing quickly.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.42.0] - 2026-11-02

### Added

- Timeline snapshots can be downloaded as JSON and imported back into the
  library from the Timeline versions dialog.
- Imported timelines are validated as project state and receive a new snapshot
  id, so they can be loaded or used by `timeline.load` immediately.
- API routes for snapshot download and import.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.41.0] - 2026-11-02

### Added

- Preview moved back above the transport and timeline, with a persisted
  vertical resize handle between preview and timeline.
- One shared zoom control for Normal and Recut.
- Dropdowns for all node enums and checkbox multi-select for option arrays,
  including timeline export targets.
- Clear timeline-empty diagnostics and richer backend request errors with
  endpoint, method, and request body.
- Play waits for `canplay`; next/previous segment now derive from the current
  output time instead of a stale index.

### Fixed

- Split now keeps the playhead inside the selected clip or moves it to the
  clip midpoint before sending the edit.
- Activate/deactivate preserve the playhead and selection across the reload.
- Preview order no longer places the timeline above the video.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.40.0] - 2026-11-02

### Added

- Multi-selection batch editing now includes scale and X/Y position.
- Reset transform applies scale 1 and centered position to every selected clip.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.39.0] - 2026-11-02

### Added

- Multi-selection inspector now edits transition type, duration, fade-in, and
  fade-out for every selected clip in one action.
- Batch style application keeps the existing copy/paste and deactivate actions.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.38.0] - 2026-11-02

### Added

- Fixed timeline track headers that stay visible while the canvas scrolls.
- Previous/next marker navigation from the transport and `Alt+Left/Right`.
- Frame thumbnails with source-time labels while hovering the Recut canvas.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.37.0] - 2026-11-02

### Added

- Timeline hover thumbnails with a debounced frame preview and source time.
- Waveforms in the Recut audio lane, using the same peaks as the Normal canvas.
- Multi-selection inspector with Fit selection, Deactivate selected, and Paste
  style actions.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.36.0] - 2026-11-02

### Added

- In/out marks with `I`/`O`, a visible range overlay, and Clear marks.
- Fit selection (`Shift+F`) alongside Fit all.
- Copy/paste clip style for transition, scale, position, fades, and transition
  length, including multi-selection.
- The shortcuts reference now lists timeline in/out, activation, and fit
  selection commands.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.35.0] - 2026-11-02

### Added

- One preview surface for Normal and Recut, driven by the same transport.
- Timeline cursor seeks the preview; play/pause, segment navigation, speed, and
  click-to-seek work across live and rendered preview modes.
- Waveform fallback and signal filtering keep the audio track visible even when
  peaks are missing or all-zero.
- Zoom down to 2 px/s with adaptive ruler steps; horizontal wheel/Shift+wheel
  scrolls, vertical wheel zooms.
- Quick `X` toggle for active/inactive segments and an inactive-segment list in
  Normal view.
- **Use in recipe** from a timeline snapshot opens the builder with a configured
  `timeline.load` node.
- Activity, notifications, command palette, and shortcuts are portalled above
  the workspace navigation.

### Fixed

- Recipes with wired inputs but missing `needs` are repaired automatically,
  fixing `source timeline must run earlier` errors.
- Legacy `export.nle` configurations with `mp4` migrate to timeline-only targets.
- Activity/notification overlays no longer render behind the Produce/Edit/Runs/
  Library/Setup bar.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.34.0] - 2026-11-02

### Added

- **Separate timeline and video export nodes.** `export.nle` now writes only
  Resolve/FCPXML, Premiere/XMEML, and Kdenlive timelines. New `export.video`
  renders the direct video file.
- `export.video` presets: `ultrafast` (default, libx264 ultrafast/CRF 30),
  `fast`, `balanced`, and `quality`, plus configurable output folder and
  filename.
- All built-in recipes with a timeline now end with both `export.nle` and
  `export.video`.
- Quick node enable/disable from the node header and the inspector. Disabled
  nodes are omitted from the recipe run without deleting their configuration.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.33.1] - 2026-11-02

### Added

- **Browser-safe live source proxy.** The timeline reports a `live_source`
  status. Compatible H.264/AAC sources stream directly; other codecs or sources
  above 1080p are transcoded once to a cached 1280px H.264/AAC proxy.
- `POST /jobs/{id}/live-source`, `GET /jobs/{id}/live-source/status`, and
  `GET /jobs/{id}/live-source/file` build, report, and serve the proxy with
  Range support.
- The Recut player shows a fixed-height preparation state, then switches to the
  proxy URL when ready; failure falls back to the rendered preview.

### Notes

- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.33.0] - 2026-11-02

### Added

- **Editor-first timeline layout.** The timeline is pinned above a fixed-height
  preview and scrollable inspector, so selecting clips or showing messages no
  longer moves it.
- Icon transport with start/end, previous/next segment, play/pause, one-frame
  and one-second seeks, and 1.0x–3.0x playback speed in 0.5x steps.
- Click-to-seek on the ruler, empty tracks, clips, and Recut blocks. The playhead
  can be scrubbed, and the mouse wheel over the timeline zooms instead of
  scrolling the page.
- Timeline shortcuts for playback, navigation, cutting, zoom, speed, save, and
  open, documented in the shortcuts modal.
- **Saved timeline versions.** Save, list, load, and delete named snapshots.
  Loading increments revision and records undo.
- **`timeline.load` recipe step** loads a saved timeline and exposes its state
  and media ports for export or render without rerunning analysis.

### Fixed

- Live playback no longer captures the wrong video element after a seek, and an
  audio failure no longer prevents the video clock from running.
- Playback speed is applied to both crossfade layers and the separate audio
  elements.

### Notes

- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.32.2] - 2026-11-02

### Added

- **Stop all** in the Activity drawer, backed by
  `POST /api/v1/jobs/cancel_all`. It cancels every queued, running, paused, or
  approval-waiting job and immediately drains the queue.
- Bulk test coverage for stopping running and queued jobs together.

### Notes

- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.32.1] - 2026-11-02

### Fixed

- Portable jobs now receive the same cancelable FFmpeg adapter as recipes, so
  force stop also kills their running FFmpeg process.
- Portable export reports per-target progress and honours cancellation.
- MP4 is always written after the NLE targets, even in a custom recipe that
  lists it first.

### Notes

- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.32.0] - 2026-11-02

### Fixed

- **Recut no longer blocks on an MP4 render inside `export.nle`.** The Recut
  recipes write Resolve, Premiere, and Kdenlive timelines only. Render the MP4
  from the Edit tab when the cut is final.
- **The Edit tab opens as soon as `edit.timeline` finishes.** `project_state.json`
  is published atomically after the timeline step, and running jobs with
  `timeline_ready` appear in the timeline picker instead of waiting for the
  whole recipe to succeed.
- Newer manual edits are never overwritten by the runner's later state write.
- **Jobs can be cancelled or removed at any time.** Cancelling a running job
  sets the FFmpeg cancellation event, and force stop/remove deletes the job from
  the queue and store. The Activity drawer now has Cancel, Force stop, Dismiss,
  and Clear finished actions.
- Cancelling or removing a queued job drains the next worker immediately.
- Export steps report per-target progress and honour cancellation.

### Notes

- MP4 is still available through the render queue and the Edit tab, with its
  existing revision tracking and cancellation.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.31.0] - 2026-11-02

### Added

- **Live compositor for Recut playback.** Crossfades and fade-to-black now
  compose in the browser with paired video/audio layers, overlays render at
  their timeline position with their opacity and size, and structured title
  cards plus lower thirds appear in output time.
- Track mute/solo is honoured live: the audio gain drops to zero and a muted
  video track renders black.
- `GET /jobs/{id}/overlays/{overlay_id}/file` serves overlay assets with the
  same allowed-root validation as the rest of the API.
- The timeline payload now carries `titles` cues and each clip reports whether
  its transition includes audio.

### Notes

- FFmpeg colour/audio filters and clip transforms still fall back to the
  rendered preview because approximating them in CSS/Web Audio would be
  inaccurate.
- ASS files without `titles.json` also fall back; structured titles are live.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.30.0] - 2026-11-02

### Added

- **Editable Recut cut boundaries.** Inactive segments can be resized with edge
  handles in the Recut canvas or with Start/End controls in the Recut
  inspector. Adjacent active clips grow or shrink to match, the active timeline
  is repacked, and every change participates in undo/redo and the ETag revision
  path.
- The timeline API accepts `action: "recut"` with new source `start_sec` and
  `end_sec` for an inactive segment.

### Notes

- Edges without an adjacent active clip stay fixed, so a leading or trailing
  silent range cannot be extended into unassigned media.
- Inactive reasons are preserved when a cut is adjusted.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.29.0] - 2026-11-02

### Added

- **Recut recipes create inactive segments automatically.** The VAD node emits
  silence spans, the retake node emits retake and manual spans, and the timeline
  node turns the gaps around final padded speech into inactive segments with the
  matching reason. No separate approval flow is required.
- Typed `InactiveSpan` values and `inactive_spans` ports connect the nodes.
- The timeline payload now carries auto-generated `inactive` source ranges for
  the Recut view and the live player.

### Changed

- Portable runs use the same inactive-segment construction as recipes.
- Recut recipes wire silence and retake spans explicitly instead of relying on
  implicit context.

### Notes

- Inactive segments are derived from the complement of the final padded speech,
  so manual deactivation remains available for corrections.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.28.0] - 2026-11-02

### Added

- **Live Recut playback in the editor.** Hard-cut timelines play the source
  directly and jump over inactive ranges. The player shows source and output
  time, preloads through the source stream, and can advance to the next active
  segment.
- `GET /jobs/{id}/source/file` streams the source with Range support.
- The timeline payload reports `live_eligible` and `live_reason`; complex
  timelines fall back to the rendered preview instead of playing inaccurately.

### Notes

- Live eligibility requires hard cuts, paired audio (J/L offsets supported via a
  separate audio element), identity transforms, no transitions/overlays/ASS/
  filters, and no track mute/solo.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.27.0] - 2026-11-02

### Added

- **Non-destructive inactive segments.** Clips can be deactivated without
  losing their source ranges. `ProjectState.inactive_segments` keeps the paired
  video/audio payloads and the reason (`manual`, `silence`, `retake`).
- **Normal and Recut timeline views.** Normal keeps the compacted active
  timeline. Recut shows the source-time timeline with active clips in blue and
  inactive clips in red; the choice is remembered.
- `deactivate` and `activate` timeline actions participate in undo/redo,
  revision checks, and the ETag edit path.
- The timeline payload now includes `source_duration_sec`, source positions for
  video clips, and the inactive segment list.

### Notes

- The Recut view is visual and editable in this phase. Playback that skips
  inactive regions live is the next phase.
- MP4/NLE exports continue to use only active segments.
- Full-tree coverage is 96.2%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.26.0] - 2026-11-02

### Changed

- **One segmented MP4 renderer with a persistent cache.** The separate
  incremental renderer was removed. Long and crossfade timelines render video
  groups once, cache them atomically under `render/segments`, and reuse
  unchanged groups from both preview and final render.
- Preview and render now share the same audio/video filter and path inputs.
- Segment cache keys include the source file, clip ranges/transforms, encoder
  settings, scale, and cache version.

### Removed

- **Legacy CLI `videoflow run`.** Use `videoflow recipe run`.
- **Projects.** The unused project CRUD records, panel, client types, routes,
  assistant read tool, tests, and documentation were deleted; recipe jobs are
  the only project-producing path.
- The dead crossfade branch in the classic filter-graph builder; any crossfade
  timeline is routed through the segmented renderer.
- The unused timeline `preview_url` field.

### Notes

- Full-tree coverage is 96.2%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.25.3] - 2026-11-02

### Fixed

- **Broken settings no longer fail silently.** An unreadable
  `settings.json` still falls back to defaults, but reports
  `settings_error`, fails the doctor settings check, and raises a global
  warning in the UI.
- **Database failures are visible.** SQLite read/write errors set
  `database_error` in `GET /system`, feed the doctor check, and are logged
  instead of being swallowed.
- **Network and timeout failures reach the global error path.** API requests
  abort after ten minutes and emit the same notification event as HTTP errors.

### Changed

- **MCP job lists omit embedded recipes by default.**
  `videoflow_list_jobs(..., summary=true)` matches the API summary payload.
- Removed the remaining unused client helpers for job-first state, URL import,
  media probe, filesystem roots, model install, config transfer, project
  updates, B-roll reads, and Short LLM analysis. Every exported client function
  is now called by the UI.

### Notes

- Full-tree coverage is 96.2%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.25.2] - 2026-11-02

### Changed

- **Previews render once at proxy height.** The old full-resolution render plus
  a second transcode is gone; previews are encoded directly at the configured
  proxy height and written atomically.
- **Audio-only filters no longer re-encode video.** Long segmented timelines
  apply audio filters on the audio track and copy the video, skipping a whole
  video encode.
- **Timeline edits reload less.** Clip, style, overlay, undo, and redo changes
  no longer refetch assets or review/thumbnail data; the four deliverable calls
  run in parallel on initial load.
- **The job list can omit embedded recipes.** `GET /jobs?summary=true` keeps the
  fields the UI needs and drops the full recipe document from every row; the
  shell uses it for its eight-second poll.
- **SQLite initializes once per database.** Schema checks run on the first
  connection instead of every connection, and asset scans upsert in one
  transaction instead of one connection per file.
- **Maintenance prunes preview frames, render segments, legacy preview
  intermediates, and stale partial files** alongside checkpoints and B-roll.
- Repeated API errors are deduplicated, network failures reach the global
  notification path, and background polling pauses while the window is hidden.

### Notes

- Full-tree coverage is 96.2%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.25.1] - 2026-11-02

### Fixed

- **Rendered files are current or absent.** MP4 and preview outputs are written
  atomically and only become `ready` with a manifest matching the project
  state, filter files, titles, and proxy height. A failed, cancelled, or stale
  render can no longer be served as current after a restart.
- **Previews never hide newer edits.** The preview manifest records the timeline
  revision; the UI keeps the preview marked outdated and queues another pass
  when the timeline changed during rendering. `WaveformStrip` reloads when the
  preview URL changes.
- **Waveforms align after cuts.** The timeline asks for the clip's source range
  (`source_in_sec`/`source_out_sec`) instead of its timeline position.
- **Frame previews use the edited picture.** `/frame` now maps a timeline
  moment to the matching source frame, or reads the current preview, instead of
  rendering the raw source at the same timestamp.
- **Long renders no longer report a false timeout.** The UI follows render and
  preview status for up to two hours, matching the server's FFmpeg budget.
- **Concurrent tabs cannot overwrite each other.** Timeline edits send
  `If-Match`; the UI reloads on `412`. Batch edits now enforce the same check.
- **Batch and MCP step runs validate ports.** Invalid wiring is rejected before
  a batch or step starts.
- **Long crossfade timelines render in bounded groups.** Contiguous crossfades
  are rendered as cached groups with a separate audio graph, followed by the
  finishing pass. The monolithic graph is no longer used for long timelines.
- **Segment and group caches are atomic** and keyed by a cache version, so a
  crashed render cannot poison later renders.

### Changed

- Segment rendering seeks the source before decoding each clip, removing the
  quadratic prefix decode. Repeated renders reuse unchanged segments.
- Project pages are described as source/output bookmarks; the inert “Open run”
  action was removed.

### Notes

- Full-tree coverage is 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.25.0] - 2026-10-27

### Changed

- **Wiring lists every port.** The wire dialog shows all outputs and inputs;
  incompatible ports stay visible but disabled inside an accordion. The node
  inspector has a **Wiring** button that opens the same dialog.
- **The recipe owns its paths.** The optional run source and workspace fields
  are gone from the builder. The ingest node supplies the source, the job
  supplies the output, and NLE validation and run history open a workspace
  dialog seeded from the last job output.
- **Timeline preview sits above the canvas** so the player and waveform lead
  the edit surface instead of trailing the timeline.
- **The welcome guide moved to the header.** An inline onboarding card is
  replaced by a **Guide** button that opens the same four steps in a modal, and
  dismissal is remembered.
- **Modals render in a portal above the area navigation.** JSON editor, wire,
  library, config, history, and tour dialogs share one z-index ladder; the
  area navigation can no longer paint over the JSON editor.

### Fixed

- Stacking order is covered by tests: the JSON editor and wire dialog stay
  above the area navigation.
- Removed the dead job-first client helper and the stale project-to-recipes
  hand-off that wrote an unused `videoflow.project` localStorage key.
- A recipe run without a source now says to set the ingest node source instead
  of suggesting a run-source field that no longer exists.

### Notes

- Full-tree coverage is 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.24.0] - 2026-10-27

### Fixed

- **Long MP4 exports no longer run out of memory.** Timelines above 16 hard-cut
  segments render each video segment separately, concatenate the video, render
  the audio timeline, and apply finishing filters in one bounded final pass.
- **SIGKILL is explained instead of reported as "unknown error".** FFmpeg errors
  now carry the exit code, signal, command, and stderr; a kill without stderr
  says it was likely an out-of-memory termination.
- **Backend error details reach the UI.** API errors preserve status, code,
  command, stderr, and validation errors; a global notification shows every
  failed request with expandable details.
- Job cards, render status, and preview status now show structured error
  details, not just a one-line message.

### Added

- Real FFmpeg media tests for long MP4 timelines, J/L-cut-safe audio, global
  colour/audio filters, ASS titles, overlays, duration, and stream validation.

### Notes

- Full-tree coverage is 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.23.0] - 2026-10-26

### Added

- **Guided builder tour.** A three-step tour explains graph building, inspection,
  and multi-selection.
- **Mobile inspector drawer.** On narrow screens the inspector opens as a bottom
  sheet with a dismiss backdrop.
- **Icon consistency.** Library, assets, timeline markers, B-roll controls, and
  favorites use the shared SVG icon set.
- **Fit selected nodes.** Frame the current multi-selection in the viewport.

### Changed

- **Domain I/O isolation is complete.** Steps no longer leak `artifacts`,
  `metadata`, `shorts`, `selected_shorts`, `short_captions`, transcript changes,
  or speech spans through ambient context copies. Every domain value crosses a
  declared output port; only hashes, cache bookkeeping, and warnings remain as
  runner diagnostics.

### Notes

- Full-tree coverage is 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.
- Planned and partial steps remain documented limitations.

## [2.22.0] - 2026-10-26

### Added

- **Help metadata for every parameter.** Labels, descriptions, units, groups,
  and placeholders now ship in each step manifest, so every field has a tooltip
  in the node and inspector.
- **Local SVG icon system.** Areas, tabs, steps, toolbar actions, and inspector
  sections use representative icons instead of Unicode glyphs.
- **Hierarchical builder toolbar.** Primary Add/Run, secondary Save/Validate/
  Inspector, icon undo/redo, and a More menu for batch, NLE validation, config,
  layout, history, and export actions.
- **Builder command palette and shortcuts.** Recipe actions are searchable in
  the palette; Ctrl/Cmd+S, Ctrl/Cmd+Enter, Ctrl/Cmd+C/V, and Delete work in the
  graph.
- **Resizable inspector.** Drag the left edge to resize; width is remembered,
  sections collapse, and fields can be filtered.
- **Path picker recents and favorites.** Recent folders and starred folders are
  stored locally per machine.
- **Preset management.** Rename, duplicate, and see how many values differ from
  the current node.
- **Graph productivity.** Node search dims non-matches; multi-select can align,
  duplicate, or delete; copied nodes can be pasted; wiring can be disconnected.
- **Recipe version comparison.** Compare a saved version with the current graph
  without restoring it first.
- **Design primitives.** Shared Button, IconButton, and Section components.
- **Contextual onboarding.** A fourth onboarding step explains the inspector,
  autosave, and undo.

### Notes

- Full-tree coverage remains above the 95% gate at 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.
- No new planned step became available; `content.*`, `publish.webhook`, and the
  partial steps remain documented limitations.

## [2.21.0] - 2026-10-26

### Added

- **Full-tree coverage gate met.** 96.4% (19,347/20,069 statements) with 1,405
  unit/contract tests, including new coverage for adapters, CLI, MCP tools, API
  routes, step runners, services, and exporters.
- **Docked recipe inspector.** The inspector now sits beside the canvas on wide
  screens instead of covering the graph.

### Fixed

- Missing music/image/font assets return `404 asset_not_found` instead of a 500.
- Invalid config imports return `422 invalid_config`.
- A shadowed duplicate artifacts route was removed.
- Missing local models raise a domain error instead of `KeyError`.
- Duplicate entries in LLM Short rankings are ignored.
- Disabling Short captions no longer leaves a stale subtitle reference.
- Publishing and B-roll history tolerate non-object JSON stores.

### Notes

- Pure step I/O and the two manual QA sign-offs remain open for 3.0.
- Voice cloning stays shell-only by decision; synthesis reports
  `capability_unavailable`.

## [2.20.0] - 2026-10-26

### Added

- **Node presets library.** Built-in and operator-created presets per step type,
  with create, edit, delete, favorite, and update-from-current-values.
- **Node option catalogs.** `GET /api/v1/node-options` and provider pickers for
  ASR/TTS steps, populated from the configured providers.
- **Optional run roots.** Source and workspace are derived from the ingest node
  and source folder when the run form is left empty.
- **Port wiring shows every port.** Incompatible inputs remain visible but
  disabled, with type labels and reasons.
- **Navigation icons and field help.** Icons for areas/tabs and tooltips for
  node descriptions and every documented field.
- **Per-step context isolation.** Steps run against a scoped context copy; only
  declared ports and ambient compatibility state are merged back.

### Notes

- Full-tree coverage is 81.9%; the 95% gate remains open.
- Pure step I/O and Kdenlive/a11y manual QA remain open.

## [2.19.0] - 2026-10-26

### Added

- **Global recut presets:** Recut Podcast (J-cuts + retakes), Recut Lecture
  (hard cuts, wide handles), and Recut Social (L-cuts + retakes).
- Recipe presets are regular recipes, so they appear in Favorites/Recent/All,
  support branch wiring, and export MP4 + Resolve/Premiere/Kdenlive.

### Fixed

- Node output-folder copies deduplicate artifacts and preserve pipeline refs.
- Node media/output paths are validated against allowed roots during recipe
  validation, not only at execution.
## [2.18.0] - 2026-10-26

### Added

- **Node-native media input.** `ingest` owns a media picker; any node with a
  `media` input can choose a file when the port is unwired.
- **Node output destinations.** File-producing nodes can pass artifacts to the
  next node or save a copy to a chosen folder, validated against allowed roots.
- **Inputs / Config / Outputs node layout.** Ports, presets/schema fields, and
  destination policy are visually separated and color-coded.
- **Voice clone shell.** Provider contract, consent metadata, status/profiles
  API, and an AI providers UI card; synthesis returns `not_implemented`.
- **Recipe tags UI.** Tags are editable in the recipe library.
- **Kdenlive-only NLE plan.** Resolve and Premiere removed from installation/QA;
  Kdenlive Flatpak 26.08.2 is the manual target.

### Changed

- `RecipeStep` gained `media_override`, `output_mode`, and `output_dir`.
- Recipe validation and the runner enforce node-level media/output paths.
- Output folders copy the node's artifacts while preserving pipeline refs.

## [2.17.1] - 2026-10-25

### Added

- **Inspector port rewiring.** Every selected node lists its inputs with a
  compatible-output dropdown, including a "Not wired" option. Rewiring updates
  the dependency edge, label, undo stack, and serialized recipe.

### Fixed

- Port validation now requires the source node to be in the target's dependency
  ancestry, not merely earlier in the topological order.

## [2.17.0] - 2026-10-25

### Added

- **Typed data ports.** Every registered step declares typed inputs and outputs;
  recipes can bind `node.port` to `node.port` via `inputs`.
- **Port wiring in the UI.** Nodes show their ports, edge labels show the
  mapping, and the Wire ports dialog filters compatible types.
- **Branching recipes.** Two VADs or two timelines can run independently; cache
  fingerprints include wired input hashes.
- **Legacy compatibility.** Recipes without explicit `inputs` keep the existing
  implicit context behaviour.
- **Schema-driven controls.** Sliders with numeric companions, segmented
  controls/dropdowns, switches, chips, path/colour pickers, defaults, resets,
  field groups, and node presets.
- **Validation fix.** Recipe validation resolves variables before validating
  step parameters.

## [2.16.0] - 2026-10-25

### Changed

- **Recut configuration moved into the nodes.** `recut_replacement` and
  `recut_replacement_retakes` no longer expose node-local settings as recipe
  inputs; VAD, retake, timeline, and export defaults live in each step.
- **Recut wiring.** The built-in Recut recipes now use explicit ports for
  ingest→VAD→timeline→export and the retakes branch.
- **UI version and tooltips.** The UI version comes from the package at build
  time, and help tooltips are fixed-position portals with viewport collision.

## [2.15.1] - 2026-10-25

### Fixed

- **Recut padding is applied once.** The VAD step no longer pads spans before the
  timeline when the recipe exposes `pad_before_ms`/`pad_after_ms`; the timeline
  remains the single owner of handles, so cuts are not lengthened twice.

## [2.15.0] - 2026-10-25

### Added

- **Recut Replacement** built-in recipe with detailed VAD controls:
  noise/speech thresholds, minimum silence, minimum speech, left/right pads,
  short-spike suppression, and tiny-gap merging.
- **Recut Replacement + retakes** variant that adds transcription and retake
  culling before the cut.
- **Cut mode** `hard | j_cut | l_cut | custom` on the timeline step, with
  configurable offset, crossfade, fades, and handle checks.
- **Four outputs from one recut:** MP4, FCPXML (Resolve), XMEML (Premiere),
  and Kdenlive.
- **Recipe organization on the server:** favorites, recent runs, use counts,
  and tags in `<home>/recipe_meta.json`, exposed through the API and MCP.
- **Recipe library UI:** Favorites, Recent, All, search, and star toggles.
- **Tooltip portal:** help tooltips are fixed-position and no longer clipped by
  the recipe canvas container.
- **UI version injection:** the UI reads the package version at build time, so
  the version badge no longer drifts from the server.

### Changed

- `audio.vad` accepts `spike_suppression_ms` and `merge_gap_ms`.
- Recut recipes default to hard cuts and export all four targets.
## [2.14.1] - 2026-10-25

### Added

- **Incremental crossfade.** Adjacent clips joined by a crossfade render as a
  cached xfade group; unchanged groups are reused and the full graph remains the
  fallback for ineligible timelines.
- **Multi-process queue worker.** `queue_worker.run_once/serve` claims with a
  lease, keeps a heartbeat, and can start a manager with `load_store=False` so
  another process does not steal queued jobs.
- **Frame prefetch.** `GET /jobs/{id}/frames` serves a bounded batch with cache
  hit reporting; the timeline preloads the next frames while scrubbing.
- **Quality gates.** axe WCAG A/AA test, shell visual baseline, 1,000-clip UI
  performance guard, p95/p99/memory load metrics, and `scripts/gate_local.sh`.

### Changed

- Missing export/prune directories now return `404` instead of a generic `500`.
- Layer coverage: API 85.2%, jobs 90.8%, exporters 95.0%, MCP 80.3%; full tree
  81.7% (3.0 still blocked at 95%).

## [2.14.0] - 2026-10-25

### Added

- **Incremental render expansion.** Segment cache now keeps per-clip
  `fade_to_black` and overlays incremental; crossfades still use the full graph
  with a safe fallback.
- **Frame proxy cache.** `GET /jobs/{id}/frame?height=` caches per revision and
  height, so scrubbing invalidates automatically after an edit.
- **Multi-process queue claim.** Atomic SQLite claim with worker leases,
  heartbeat ownership checks, and expired-lease recovery (`queue_claim.py`).
- **Observability.** Every log line carries `job_id` for correlation.
- **Property tests.** Recipe parsing and timeline edits are fuzzed for invalid
  ranges and clean rejection.
- **Circuit breaker and cost budget** for LLM providers, with actionable errors.

## [2.13.0] - 2026-10-25

### Added

- **Projects.** `GET/POST/PATCH/DELETE /api/v1/projects` with local JSON records,
  Produce → Projects, and a "Use in Recipes" handoff.
- **Assistant tool-calling.** Allowlisted read/write tools, two-step approval,
  clip-level diff, per-turn tokens/cost, conversation history, and a single-use
  approval id.
- **Run graph.** Step nodes, edges, per-step duration, p50/p95 by recipe, retry
  policy, and previous-run comparison.
- **Variant comparison.** Recipe variants, Shorts, and thumbnail metrics in one
  list with a persisted winner.

## [2.12.0] - 2026-10-25

### Added

- **Complete EN/PT catalog.** Every visible static string in the Svelte panels has
  a PT-BR entry, enforced by a coverage test.
- **Onboarding.** Three-step first-run card with persisted dismissal.
- **MCP contract.** Behavior annotations on every tool, three prompts
  (`produce`, `review`, `deliver`), and paginated list tools.
- **OpenAPI contract.** Error envelope, examples for timeline/run/logs/projects,
  ETag/If-Match on timeline writes, and explicit API version.
- **Accessibility and responsiveness.** Arrow/Home/End tab navigation, narrow
  viewport and PT-BR locale E2E coverage, `docs/errors.md`.

## [2.11.0] - 2026-10-25

### Added

- **Five-area navigation.** Produce, Edit, Runs, Library, and Setup replace the
  flat 13-tab bar, with sub-tabs, breadcrumbs, persisted last tab, and legacy
  hash redirects (`#assets`, `#automation`, `#copilot`, `#library`, `#plugins`,
  `#integrations`).
- **Naming pass.** Runs, Schedules, Media, Brand library, Assistant, AI models,
  AI providers, Local services, Extensions, Connect.
- **Help system.** `HelpTip`, `FieldHint`, `EmptyState`, `StatusBadge`, units in
  labels, help tips on every Setup panel and the main editors.
- **Searchable settings** with section filtering, units, help tips, and
  discard-changes.
- **Keyboard navigation** for area and sub-tab tablists (arrows, Home, End).
- **Copy standards.** `docs/ui-copy.md` and `docs/settings.md`.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Remaining for 3.0: long help-text i18n, voice cloning, full-tree coverage,
  and manual NLE/assistive-technology QA.

## [2.10.0] - 2026-10-25

### Added

- **MCP surface finished.** 78 tools and 5 resources covering jobs, pause/
  priority, timeline read, overlays, clip comments, Copilot, cost, export
  validation, plugins, backup, and frame extraction. New resource
  `videoflow://docs/integrations`.
- **Integration area.** New Integrations tab and `docs/integrations.md` with
  copy-ready OpenCode stdio/HTTP setup, `opencode.jsonc` examples, DeepSeek
  model/provider setup, Paperclip DeepSeek agent + MCP/REST workflow, prompts,
  security notes, and troubleshooting.
- **API docs.** Copilot endpoints, frame/overlays/comments, pause/priority,
  cost metrics, and MCP tool counts documented.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Remaining: long help-text i18n, voice cloning, full-tree coverage, and manual
  NLE/assistive-technology QA.

## [2.9.0] - 2026-10-24

### Added

- **Segment-cached timeline render.** Simple cut timelines render each clip to a
  cached segment, reuse unchanged segments, and concatenate without re-encoding
  everything. Timelines with transitions, overlays, titles, filters, or
  non-aligned audio fall back to the full exporter.
- **Frame progress.** `FFmpegAdapter.render` parses `-progress` and the render
  queue maps frame counts to the job percentage.
- **Frame preview.** Scrubbing debounces a cached JPEG and an async video seek;
  the playhead shows the exact frame.
- **Resource-aware parallelism.** `flow.map` caps workers by CPU, available
  memory, and `VIDEOWFLOW_PROVIDER_CONCURRENCY`.
- **Copilot.** `POST /api/v1/copilot/recipe` drafts and validates recipes;
  `POST /api/v1/jobs/{id}/copilot/timeline` proposes or applies validated
  timeline edits. Provider/service setup is documented in `docs/copilot.md`.
- Copilot tab with recipe draft/save and timeline apply.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Remaining: long help-text i18n, voice cloning, full-tree coverage, and manual
  NLE/assistive-technology QA.

## [2.8.0] - 2026-10-24

### Added

- **Typed job rows and retries.** The `jobs` table gains status, priority,
  attempts, next_run, lease, progress, source/output/recipe/variables, and
  timestamps. Jobs can opt into retry with `max_attempts` and
  `retry_backoff_seconds`; a retry loop re-drains when due. Scheduled runs use
  an automatic idempotency key from schedule, source, size, and mtime.
- **Frame preview.** `GET /jobs/{id}/frame?time=` extracts a cached JPEG at the
  playhead; the timeline debounces a frame image while scrubbing.
- **Resource-aware map.** `flow.map` caps workers by available CPUs and warns
  when the requested parallelism is clamped.
- **Per-service log rotation.** Service logs rotate to two generations before a
  new process appends.
- **Optimistic rollback.** Pause/resume and priority update the card, then
  revert on error.
- **More PT-BR glossary.** Additional panel labels and headings.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Remaining: long help-text i18n, voice cloning, per-clip incremental render,
  full-tree coverage, and manual NLE/assistive-technology QA.

## [2.7.0] - 2026-10-24

### Added

- **True Kdenlive cross-dissolve.** Video is written to two alternating tracks;
  a crossfade extends the outgoing clip's source tail by the transition length
  and animates affine opacity on the incoming (or outgoing) top track, with two
  `qtblend` composites in the sequence tractor. Fade-to-black keeps the
  single-clip opacity ramps.
- The Kdenlive validator and tests now read both video playlists and assert the
  two-track structure and opacity keyframes.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Long help-text i18n, voice cloning, full-tree coverage, and the manual
  NLE/assistive-technology gates remain open.

## [2.6.0] - 2026-10-24

### Added

- **NLE overlays and drag e2e.** Timeline overlays join the B-roll lane in all
  three documents (XMEML still frames, Kdenlive `qimage`), with a Playwright
  drag test.
- **Semantic B-roll option.** Local sentence-transformers model via
  `VIDEOWFLOW_EMBEDDING_MODEL`; TF-IDF remains the fallback.
- **Dubbing hardening.** Duration alignment retry, translation review files, and
  ordered TTS provider fallback.
- **Hook and duration A/B.** `shorts.ab` plus the `hook_duration_ab` recipe.
- **Video-track mute.** Render and preview draw black frames when V1 is muted.
- **Parallel map everywhere.** `flow.map` runs any collection in parallel, with
  isolated child contexts.
- **Assets pagination.** SQL `LIMIT/OFFSET` and filtered asset queries.
- **Plugin write policy.** `filesystem` permission and rejection of absolute
  paths outside the plugin folder.
- **Job DAG and confirmations.** Stage pills in the dashboard; confirmation for
  plugin enable and managed service start/stop.
- **Embedded plugin panels.** Panels open inside the shell in a sandboxed iframe.
- **Cost estimate and expanded golden set.** Token prices for known models,
  approval-rate metric, and seven golden cases including multi-speaker, gaps,
  and scene changes.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- True Kdenlive cross-dissolve, full long-text i18n, voice cloning, full-tree
  coverage, and the manual NLE/assistive-technology gates remain open.

## [2.5.0] - 2026-10-24

### Added

- **Plugin SDK for exporters and providers.** `videoflow/plugin_api.py` exposes
  `register_exporter`, `register_provider`, and `register_panel`.
  `export_timeline` dispatches unknown targets to a plugin exporter and
  `first_provider` falls back to a plugin provider.
- **Static plugin sandbox.** `application/plugin_sandbox.py` parses the entry
  module before import and blocks shell/network imports and exec-style calls
  unless the manifest grants `shell` or `network`. Blocked plugins report the
  violations instead of loading.
- **Fault-injection suite.** Corrupt database, corrupt migration input,
  non-writable output, and corrupt project state all fail with typed errors and
  never produce a success record.
- **Log rotation and scheduled backups.** `rotate_log` retains two generations;
  `scheduled_backup` writes timestamped ZIPs and prunes to `keep`. Opt in with
  `VIDEOWFLOW_BACKUP_ON_START=1` or `POST /api/v1/maintenance/backup`.
- **Accessibility pass.** `:focus-visible`, focus traps in every dialog, focus
  restoration in the palette, `prefers-reduced-motion`, and keyboard-only
  Playwright flows.
- **Large-timeline stress test.** 1,000 clips exported through all three NLE
  writers under a ten-second budget.
- **Schema 1.x migration test.** A version-1 database migrates to version 2 with
  rows and defaults preserved.
- `docs/plugins.md` and `docs/hardening.md`.

- **Execution control.** Jobs can be paused and resumed; priority is editable
  and reorders the queue.
- **Timeline editing.** Slide, duplicate, per-clip comments, and a right-click
  context menu for split, duplicate, delete, ripple delete, slide, markers, and
  comments.
- **Incremental Shorts.** `shorts.render` writes `render-manifest.json` and
  reuses an unchanged Short; the MP4 render queue reuses an unchanged timeline.
- **Native chapters.** `chapters.json` becomes NLE markers in all three
  documents.
- **Theme and density.** Light, dark, and high-contrast themes through tokens;
  compact density; AA focus, focus traps, reduced motion.
- **Crash reports and token metrics.** Unhandled API errors write a minimal
  JSON report; LLM usage is accumulated at `GET /api/v1/metrics/cost`.
- **Plugin panels.** The Plugins tab lists sandbox status and links registered
  panels.
- **Assets on the timeline.** Drag an image or video from the timeline asset
  rail; the overlay is stored in `ProjectState.overlays` with `asset_id`,
  frame timing, position, size, and opacity, and is composited by the MP4
  exporter.

- **Optional semantic B-roll.** A local sentence-transformers directory enables
  embedding matching; TF-IDF remains the automatic fallback.
- **Dubbing hardening.** Duration drift triggers one speed-corrected retry,
  each dub writes a translation-review file, and the step tries every configured
  TTS provider before warning.
- **Hook and duration A/B.** `shorts.ab` clones selected Shorts into hook and
  duration variants, and the `hook_duration_ab` recipe renders them.
- **Overlays in the NLEs.** Timeline overlays join the B-roll lane; XMEML marks
  still frames and Kdenlive uses `qimage` producers.
- **Panel glossary.** A runtime PT-BR glossary translates the dense panels'
  headings, actions, and common labels without rewriting every template.

### Changed

- `RecipeSchedule`, `PluginManifest`, settings, providers, and schedules gain
  versioned migration helpers with default filling.
- Version bumped to 2.5.0 for the server and UI bundle.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums. No GitHub Actions,
  no publishing, no multiuser.
- The plugin sandbox is a static allowlist, not an OS sandbox: a plugin with the
  `shell` permission runs as the service user.
- Manual NLE import checks and manual screen-reader/200% zoom checks remain on
  the checklist; the host lacks the NLEs.
- Kept releases: v2.5.0, v2.4.0, v2.0.0. v1.0.0 is pruned by the three-release
  retention rule.

## [2.4.0] - 2026-10-24

### Added

- **Native NLE finishing.** FCPXML, XMEML, and Kdenlive exports now carry
  titles, sequence markers, colour filters, B-roll, and the audio master,
  driven by `exporters/extras.py` and `application/nle_extras.py`.
- **FCPXML** writes native `title` elements, `marker` elements,
  `filter-video` colour filters, B-roll on lane 2, and the master stem on
  lane 4.
- **XMEML** writes `generatoritem` titles, sequence markers, colour filters, a
  second video track for B-roll, and a second audio track for the master.
- **Kdenlive** writes `kdenlivetitle` producers, guides in the document
  properties, an overlay playlist with `qtblend`, a stem playlist with `mix`,
  and `lift_gamma_gain` colour filters.
- **`scripts/qa_nle.py`** compares an export directory with the job output and
  fails on missing native elements; the validator also reports titles, markers,
  colour filters, B-roll, stems, and join warnings.
- Tests cover all three documents and the QA comparison.

### Changed

- `export_timeline` accepts `extras`; `export.nle` builds them from the job
  output (markers, ASS titles, B-roll plan, colour and audio filter files,
  `master.wav`).
- The sidecar manifest now says the native timeline is the primary finishing
  path and the sidecars are the interchange copy.
- Version bumped to 2.4.0 for the server and UI bundle.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums. No GitHub Actions,
  no publishing, no multiuser.
- Manual import validation in Resolve, Premiere, and Kdenlive remains pending:
  the three NLEs are not installed on this host. The checklist and the
  automated structural checks are in `docs/nle-qa.md`.
- Kept releases: v2.4.0, v2.0.0, v1.0.0. v0.95.0 was pruned by the three-release
  retention rule.

## [2.3.0] - 2026-10-24

### Added

- **Golden set and calibration.** `tests/golden/shorts.json`, a pure
  `application/scoring.py` module, six channel profiles (`default`, `hook`,
  `education`, `podcast`, `tiktok`, `youtube`), and
  `scripts/shorts_golden.py`. The calibrated profiles reach precision@1 1.00
  against a 0.75 baseline, with zero duplicates and 100% coverage.
- **Profile before selection.** `shorts.select` accepts `profile` (also
  `shorts_profile` in job options), so weights influence which windows are
  selected, not only how they are re-ranked afterwards.
- **Shot-aware B-roll.** `assets.match` scores assets per detected shot, sets
  the cutaway `start_sec` inside the Short, records `shot_id`, and writes
  `broll-licenses.json` with attribution and license for every used asset.
- **SFX library.** `GET/POST/DELETE /api/v1/assets/sfx`, storage under
  `assets/sfx`, and an upload/delete section in the Library tab.
- **Delivery package.** `delivery.package` copies the winning thumbnail to
  `delivery/thumbnail.png` and writes a manifest with Shorts, metadata, music,
  SFX, B-roll, and licenses.
- **Localized recipe.** `localized_shorts` runs `localization.dub` after the
  Short render, with a mirrored `recipes/localized_shorts.json`.
- Media test renders a Short with music and SFX in the same pass.

### Changed

- `shorts.score` now shares `rerank`, `profile_weights`, and duplicate
  similarity with the golden evaluator instead of keeping a second copy.
- Portuguese hook detection accepts unaccented `voce`, fixing a real miss in
  the quality bonus.
- Recipe, preset, and project-state schemas are regenerated for the additive
  `profile` field.
- Version bumped to 2.3.0 for the server and UI bundle.

### Notes

- Local-only development build. No release artifact was produced for 2.3.0.
- Embedding-based B-roll and local clone dubbing remain provider work; TF-IDF,
  shot matching, and the configured TTS path are what 2.3.0 ships.

## [2.2.0] - 2026-10-24

### Added

- **Real clip waveforms.** `GET /api/v1/jobs/{id}/timeline/waveform` decodes
  the source once, computes normalised RMS peaks at 50 ms resolution, caches
  them under `<home>/waveforms`, and slices any timeline range. The canvas draws
  the real peaks and falls back to synthetic bars when the source is missing.
- **Slip edit.** `action: "slip"` shifts the source in/out of a clip without
  moving it on the timeline, for video and audio, bounded by the media length.
- **Group trim and ripple trim in the canvas.** Dragging an edge with several
  clips selected trims them together; `Shift` + edge drag ripples the trim.
  `Alt` + drag slips the clip.
- **Timeline virtualization.** Only clips, captions, and audio bars inside the
  visible window (plus a three-second margin) are drawn, and the canvas redraws
  on scroll. A synthetic 1,000-clip timeline stays responsive.
- **Preview scheduler.** The preview is marked `outdated` after every edit and
  rebuilt automatically after a 1.2 s debounce when `Auto preview` is on.
- **Track enforcement.** Locked video/audio tracks reject clip edits with
  `409 state_not_ready`; muted audio tracks render and preview with
  `volume=0`, and `solo` overrides mute.

### Changed

- Timeline DTO exposes `audio[].source_in_sec`, `audio[].source_out_sec`, and
  `media {source_path, audio_sample_rate}` for waveform requests.
- Caption drawing no longer caps at 500 entries; visibility decides what is
  drawn.
- Version bumped to 2.2.0 for the server and UI bundle.

### Notes

- Local-only development build. No release artifact was produced for 2.2.0.
- Dragging library assets onto the timeline needs a clip/overlay state model
  and is scheduled with the NLE work, not this phase.

## [2.1.0] - 2026-10-24

### Added

- **Professional shell.** Command palette (`Ctrl/Cmd+K`), keyboard shortcut
  reference (`?`), activity drawer (`U`), notification center (`N`), and
  `g`-prefixed tab jumps.
- **Job dashboard.** New Jobs tab with status buckets, text search, progress,
  next-action guidance, inline errors, guarded cancel, and retry.
- **Retry endpoint.** `POST /api/v1/jobs/{job_id}/retry` re-enqueues failed or
  cancelled jobs with the original source, output, and options.
- **Operational feedback.** Persistent errors and warnings, action buttons on
  notices, and shell-level error/success reporting.
- 12 Vitest tests and 8 Playwright tests for the new shell.

### Changed

- **Real cancellation.** `FFmpegAdapter` runs FFmpeg with `Popen`, polls for
  cancellation, and terminates the whole process group on cancel or timeout.
  Render and preview queues now pass a cancel event, remove partial output, and
  report `cancelled` without leaking processes or files.
- **SQLite is the operational store.** Jobs, assets, and batches load from
  SQLite first and JSON second; interrupted jobs are requeued on startup; reads
  no longer create the home folder as a side effect.
- Version bumped to 2.1.0 for the server and UI bundle.

### Notes

- Local-only development build. No release artifact was produced for 2.1.0.
- `ProjectState` remains the timeline source of truth; SQLite holds operational
  state for jobs, assets, and batches, with JSON kept for interchange.

## [2.0.0] - 2026-10-24

### Added

- **Local automation closure.** Human gate UI, variant comparison, analytics
  weights in scoring, scheduler job reconciliation, persistent priority queue,
  restart requeue, and real thumbnail variants.
- **Media quality.** Real audio onset/beat detection, music and SFX mixing in
  Shorts, per-Short selection reports, and thumbnail winner selection.
- **Dubbing in recipes.** `localization.dub` runs translation + TTS dubbing
  after Short rendering when a TTS provider is configured.
- **Semantic B-roll matching.** TF-IDF cosine matching over asset names/tags and
  the clip transcript, replacing keyword overlap.
- **Library CRUD.** Delete music, image, and font assets from the UI.
- **SQLite migration.** Existing JSON jobs/assets/batches import into SQLite;
  schema version 2; WAL; backup and restore.
- **Plugin step loading.** Local `plugins/<id>` packages with manifests.
- **Accessibility.** Skip-to-content link and improved labels.
- 34 built-in recipes.
- 485 Python tests, 8 media tests, 13 Vitest tests, 19 Playwright tests.

### Notes

- Local-only release: Linux binary + AppImage + SBOM. No GitHub Actions, no
  distribution, no publishing, no multiuser.
- Native NLE titles/color/B-roll remain sidecar-based; manual NLE QA still
  pending.
- Plugin SDK covers steps; providers/exporters/UI panels are not part of this
  local release.
- Full UI i18n and per-clip waveforms remain future work.

## [1.0.0] - 2026-10-24

### Added

- **0.97 — render and media closure.** Real onset/beat detection, music/SFX
  mixing in Shorts, bounded parallel map, thumbnail winner selection, and
  per-Short selection reports.
- **0.98 — Shorts intelligence.** Analytics weights applied to scoring,
  explicit score breakdowns/reports, diversity filtering, and A/B winner
  selection.
- **0.99 — finishing.** NLE structural QA, chapter planning, sidecars for
  titles/color/audio/B-roll, and a finishing recipe.
- **1.0 — local stable.** Persistent priority queue with restart requeue,
  scheduler job reconciliation, human-gate UI, variant comparison, backup
  restore, operational metrics, plugin steps, accessibility skip link, and
  SQLite WAL indices.
- 34 built-in recipes.
- 8 media tests including real beat detection.

### Validation

- 484 Python tests passed.
- 8 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Local release only: Linux binary + AppImage + SBOM. No GitHub Actions.
- Distribution, signing, macOS, Windows local builds, and collaboration remain
  out of scope.
- Native NLE titles/color/B-roll remain sidecar-based; manual NLE QA is still
  required.
- Plugin SDK v1 covers steps, not providers/exporters/UI panels.
- SQLite is an operational index; JSON remains canonical for jobs/assets.
- `flow.map` parallel is bounded for file collections.
- Full UI i18n and per-clip waveforms remain future work.

## [0.96.0] - 2026-10-24

### Added

- **Human gate UI.** Jobs waiting for approval show the gate title, comment
  field, approve/reject buttons, and resume the recipe from checkpoints.
- **Variant comparison.** Job results list every variant with output path,
  segment/short counts, and step count.
- **Analytics feedback.** `shorts.score` now reads analytics weights from
  `analytics.review` or `delivery/analytics-review.json`.
- **Scheduler job tracking.** Schedules reconcile queued/running job ids into
  succeeded/failed/waiting states and surface failures.
- **Persistent job queue.** API/MCP submissions queue instead of failing when
  the worker limit is full; queued jobs survive restart and are requeued.
- **Priority queue.** Jobs accept a priority and drain highest-first.
- **Real thumbnail variants.** `thumbnail.pack` renders different frames/styles
  and copies variants into the shared thumbnails directory.

### Validation

- 481 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- No release was built for this version.
- Native NLE effects, SFX/music mixing in the renderer, and parallel map
  execution remain future work.

## [0.95.0] - 2026-10-24

### Added

- **Recipe variables and expressions.** Typed variables, defaults, enum
  validation, `{{ expression }}` and `$name` substitution, and safe functions
  (`min`, `max`, `clamp`, `if`, `coalesce`).
- **Profiles and dry-run.** Recipe profiles override variables/step params;
  `recipe dry-run` and `POST /recipes/dry-run` return the resolved plan.
- **Variants.** A recipe can run the same DAG into named output folders with
  per-variant variables.
- **Map/reduce/subflows.** `flow.map` and `flow.reduce` operate over files,
  Shorts, sentences, scenes, and assets, with error policy and collected
  results.
- **Human gates.** `human.gate` pauses the job as `waiting_approval`; the resume
  endpoint records the decision and restarts from checkpoints.
- **Short quality scoring.** Multifactor bonuses (completeness, payoff, hook,
  CTA, speaker balance, duration fit), diversity filtering, profiles, and
  optional LLM re-rank.
- **Asset intelligence.** Shot detection, semantic B-roll matching, beat grid,
  and SFX planning.
- **Delivery.** Metadata pack, thumbnail pack, publish queue, analytics review,
  experiment evaluation, chapters, and NLE QA.
- **34 built-in recipes**, including rough cut, captions, NLE export, clean
  audio, chapters, Shorts select/render, best moments, trailer, review gate,
  variants, podcast/interview/webinar/lecture/product/testimonial/livestream,
  B-roll/music/SFX, metadata, thumbnails, publishing, analytics, localization,
  and finishing.
- **SQLite index** for jobs, assets, and batches with WAL and a backup bundle.
- **Plugin SDK v1.** Load `plugins/<id>/plugin.json` and register custom steps.
- **Diagnostics 2.0.** FFmpeg capabilities, CUDA/ONNX, SQLite integrity,
  providers, services, models, metrics, backup, and support bundle.
- **Settings wiring.** Model defaults/device/compute, speech, quality,
  translation, proxy height, runtime host/port/log/open-browser, retry/backoff,
  and locale/theme/density are consumed by the runtime.
- **Library and i18n.** Brand/project templates, presets, fonts, images, music,
  and EN/PT-BR navigation strings.

### Validation

- 477 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Local release only (Linux + AppImage + SBOM). No GitHub Actions.
- Native NLE titles/color/B-roll remain sidecar-based; manual NLE QA is still
  required.
- Windows, distribution, signing, macOS, and collaboration remain out of scope.

## [0.86.0] - 2026-10-23

### Added

- **Settings Hub.** `settings.json` with runtime, paths, models, automation,
  quality, UI, LLM, speech, TTS, stock, and translation sections; export,
  import, reset, environment overrides, and restart-required markers.
- **Runtime wiring.** Settings influence job workers/history, allowed roots,
  cache/models dirs, FFmpeg/FFprobe resolution, scheduler interval, LLM
  temperature/timeout/retries, and TTS/stock defaults.
- **Model Manager 2.0.** Expanded ASR catalog (Faster-Whisper tiny/base/small/
  medium/large-v3 and whisper.cpp base/small/medium), per-capability defaults,
  device/compute/threads, local model registration, and file/checksum
  verification.
- **Service Manager 2.0.** SQLite-backed service definitions with start/stop,
  health checks, autostart, logs, and arbitrary local commands (Ollama, LM
  Studio, whisper.cpp server, Piper, ComfyUI, and others).
- **Library.** Brand templates, project templates, presets, fonts, images, and
  music are available again in the UI.
- **Diagnostics 2.0.** Doctor checks FFmpeg capabilities, CUDA/ONNX providers,
  SQLite integrity, providers, service definitions, models, disk, and settings;
  support bundle ZIP redacts environment values.
- **LLM controls.** Temperature, timeout, max tokens, retries, and JSON mode.

### Validation

- 467 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Local release build only; GitHub Actions is disabled for automatic releases.
- Distribution, signing, macOS packaging, and Windows cross-builds remain out of
  scope.
- Manual NLE QA and per-clip waveforms remain future work.

## [0.80.0] - 2026-10-23

### Added

- **Timeline pro.** Shift-click multi-select, atomic batch edits, group move,
  bulk delete/ripple, ripple trim, real clip thumbnails, markers, and
  per-track mute/solo/lock.
- **Background MP4 render queue.** Progress, cancel, and download; filters,
  titles, color, and audio-master chain are applied.
- **Caption undo.** Caption edits now share the timeline history.
- **Schedule reliability.** SQLite-backed schedules with a JSON migration,
  retry/backoff, run history, watch-file size/mtime signatures, and concurrency
  through the job manager.
- **Provider failover.** LLM chains retry providers in order; ASR/TTS/vision
  read the configured provider when no explicit endpoint is supplied.
- **Secret store.** Environment, OS keyring, or 0600 fallback with presence-only
  API and provider-panel controls.
- **Translation.** `transcript.translate` writes translated JSON and SRT through
  the recipe LLM provider.
- **Delivery metrics.** Review comments and thumbnail CTR metrics; A/B selection.
- **NLE sidecars.** Exports now package titles, LUT/eq, audio-master filters,
  B-roll plans, and markers with instructions.
- **Audio QA.** `audio.qa` measures EBU R128 integrated loudness and true peak
  and warns when out of spec.
- **MCP parity.** Timeline edit, B-roll approval, providers, schedules, and
  review decisions are available as MCP tools.

### Validation

- 464 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Distribution, signing, macOS packaging, and onedir builds remain out of
  scope.
- Manual NLE QA, frame-accurate per-clip waveforms, and translation quality
  review remain future work.

## [0.70.0] - 2026-10-23

### Added

- **Incremental timeline rendering.** The scene layer is rebuilt only when the
  timeline, zoom, selection, or B-roll changes. The playhead and guides live on
  an overlay layer, so scrubbing no longer reconstructs every clip.
- **Background preview rendering.** `POST /preview?background=true` starts a
  worker with progress, cancellation, and `GET /preview/status`. The UI shows
  the percentage and can cancel.
- **Burned titles.** `titles.plan` writes `titles.ass`; MP4 previews and
  exports apply title cards and speaker lower thirds.
- **Audio master in the render path.** `audio.master` writes
  `audio/master-filters.json`; previews apply the same high-pass, denoise, and
  EBU R128 chain to the mixed timeline audio.
- **Color/LUT step.** `color.grade` writes deterministic `eq` and optional
  `.cube` LUT filters consumed by MP4 previews.
- **Multi-entry B-roll rendering.** Every approved B-roll entry is overlaid in
  order instead of only the first one.
- **Per-clip style editing.** Timeline API and inspector now edit transitions,
  transition length, scale, position, and audio fade in/out.
- **Editable playhead timecode** and persisted clip style revisioning.
- **Isolated flow loops.** `flow.loop` over files gives each item its own
  source, output, artifacts, warnings, and Shorts.
- **Provider fallbacks for LLM, ASR, TTS, and vision.** The configured chain is
  used when no explicit endpoint is supplied.
- **Recipe automation.** Persistent `once`, `interval`, and `watch` schedules
  with a 20-second local scheduler, run-now, status, and errors.
- **Review approval and thumbnail A/B.** Persist approval/comments and the
  selected thumbnail variant; the timeline shows both deliverables.
- **Resumable model downloads.** Partial files are hashed and resumed with HTTP
  Range; statuses survive a restart as `interrupted`.

### Validation

- 455 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Distribution, signing, macOS packaging, and onedir builds remain out of
  scope.
- Manual NLE QA, multicam editing beyond split-screen, and frame-accurate
  multi-select dragging remain future work.

## [0.67.0] - 2026-10-23

### Added

- **Professional canvas timeline.** Konva ruler, tracks, clip drag with
  snapping, trim handles, split, delete, ripple delete, zoom, fit, playhead
  scrubbing, and keyboard shortcuts.
- **Synced preview and waveform.** MP4 preview and wavesurfer.js waveform both
  seek with the timeline playhead; on-demand 540p proxy rendering.
- **Undo and redo.** Every edit records `timeline_history.json`; the API exposes
  `POST /timeline/undo` and `/timeline/redo`.
- **B-roll approval.** Approve, reject, and reorder planned B-roll per Short;
  persisted in `broll_approval.json` and consumed by the Shorts renderer.
- **Persistent providers.** `providers.json` with capability defaults, secret
  environment names, connection tests, and ordered fallback chains. The job
  runner uses the LLM provider chain when no explicit base URL is set.
- **Model download manager.** Background downloads with progress, cancellation,
  checksum verification, and status polling.
- **Executable flow nodes.** `flow.conditional`, `flow.loop`, and
  `flow.subflow` run real nested steps or referenced recipes.
- **Content depth.** Real `audio.master` (high-pass, FFT denoise, EBU R128),
  `titles.plan` (title cards and speaker lower thirds), `analytics.import`
  (CSV normalization), `review.queue` (pre-publish checklist), and multi-variant
  thumbnails.
- **Top-of-page errors.** A shared sticky `ErrorBanner` with alert semantics,
  copy diagnostics, and dismissal is used across every panel. Footer error
  blocks are gone.

### Removed

- Legacy project/module routes, `ProjectStore`, module registry, legacy planning
  runner, and their tests.
- Legacy rack UI: module cards, Studio panel, project templates screen, caption
  preview, asset managers embedded in the rack, and dead configuration state.
- The rack navigation tabs and the global run form. Recipes are the only
  execution path; the filesystem picker remains.

### Changed

- `PATCH /api/v1/jobs/{id}/timeline` accepts `trim`, `move`, `delete`, `split`,
  and `ripple`, returns undo/redo availability, and records history.
- Timeline responses include revision, FPS, undo/redo state, and B-roll
  approvals.
- UI version is 0.67.0 and is checked against the server version at runtime.

### Validation

- 448 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 18 Playwright tests passed.

### Notes

- Distribution, code signing, macOS packaging, and onedir builds remain out of
  scope.
- Face reframing, color/LUT, multicam, and manual NLE QA remain future work.

## [0.62.0] - 2026-10-23

### Added

- **Timeline editing foundation.** Trim, move, and delete clips through
  `PATCH /api/v1/jobs/{id}/timeline`; state revision increments and a re-render
  warning is returned.
- Timeline clip selection and edit controls.
- Caption editing remains available.
- Provider connection test, services doctor, model capability groups, recipe
  history/templates, flow-node bypasses, storyboard/thumbnail nodes.
- Legacy New project/ProjectTemplateManager removed from settings pages.

### Notes

- Full drag/trim handles, B-roll approval, provider persistence/fallback,
  scheduler, analytics, and audio master remain future work.
- 459 Python tests, 8 media tests, 14 Vitest tests, and 15 Playwright tests pass.
- Distribution remains out of scope.

## [0.57.0] - 2026-10-23

### Added

- **Recipe template gallery** with search and built-in/user recipes.
- Final recipe-management polish: Save as, version history, restore, and
  templates in one place.
- Timeline caption editing and implemented storyboard/thumbnail nodes from the
  0.56 work.
- Settings pages cleanup, provider connection test, services doctor, and models
  grouped by capability from the 0.54 work.

### Notes

- 459 Python tests, 8 media tests, 14 Vitest tests, and 15 Playwright tests pass.
- Distribution remains out of scope.

## [0.56.0] - 2026-10-23

### Added

- **Timeline caption editing.** Clicking a caption opens an editor and writes
  the new text back to `project_state.json`.
- `PATCH /api/v1/jobs/{id}/captions/{sentence_id}`.
- **Storyboard node** now writes `storyboard.json` from the validated timeline,
  captions, Shorts, and B-roll plan.
- **Thumbnail node** now renders a real thumbnail frame from the source.
- Timeline selection state and save feedback.

### Notes

- 459 Python tests, 8 media tests, 14 Vitest tests, and 14 Playwright tests pass.
- Timeline drag/trim is still pending.
- Distribution remains out of scope.

## [0.55.0] - 2026-10-23

### Added

- **Recipe version history.** Saving a recipe snapshots the previous JSON; the
  API can list and restore versions.
- **Save as** in the recipe header for forks/duplicates.
- **History modal** with restore.
- Planned control-flow nodes: `flow.conditional`, `flow.loop`, `flow.subflow`.
- 458 Python tests and 14 Playwright tests pass.

## [0.54.0] - 2026-10-23

### Changed

- Removed the legacy **New project** card and **ProjectTemplateManager** from
  Models/Services/Providers.
- Added a provider connection test:
  - base URL;
  - secret env name;
  - path;
  - HTTP status;
  - secret presence.
- API: `POST /api/v1/providers/test`.
- Provider page now separates policy from the collapsed capability catalog.
- Models page downloads are explicit and decoupled from the external-provider
  toggle.
- Services page has Doctor diagnostics and destructive-action confirmations.

### Notes

- 457 Python tests, 8 media tests, 14 Vitest tests, and 14 Playwright tests pass.
- Distribution remains out of scope.

## [0.53.0] - 2026-10-23

### Changed

- **Models page** now groups by capability and shows used-by steps, license,
  source, installed size, and explicit downloads. Model download is decoupled
  from the external-provider toggle.
- **Services page** has a Doctor/diagnostics panel, destructive-action
  confirmations, and bounded cache/disk reporting.
- **Providers page** separates policy from the capability catalog; the catalog
  is collapsed, searchable, filterable, and hides API/MCP details by default.
- Added `GET /api/v1/system/doctor`.
- Model manifest JSON includes capability, used_by, license, and source.

### Notes

- Provider connection tests and per-provider secret forms are still pending.
- 456 Python tests, 8 media tests, 14 Vitest tests, and 14 Playwright tests pass.
- Distribution remains out of scope.

## [0.52.0] - 2026-10-23

### Added

- **Recipes-first navigation.** Speech, Edit, Shorts, Studio, and Export were
  removed from the top-level UI; Recipes is the execution surface.
- **Content-cycle nodes.** Idea, research, script, storyboard, asset index,
  audio master, titles, thumbnail, publish, analytics, and review.
- **Implementation status.** New steps expose `status`, `icon`, `color`, and
  `bypass`; planned nodes show a dashed card and are skipped by the runner.
- **Asset library.** Scan local folders, search by name/tag/kind, edit tags,
  view license metadata, download, and remove entries.
- **Read-only timeline.** Video, audio, captions, B-roll, playhead, and preview
  from a successful job.
- New `content_cycle` built-in recipe with implemented and bypassed nodes.
- UI tests for the Assets and Timeline tabs.

### Notes

- The legacy rack code is no longer reachable from the UI; its backend routes
  remain for compatibility.
- 459 Python tests, 8 media tests, 14 Vitest tests, and 14 Playwright tests pass.
- Distribution remains out of scope.

## [0.51.0] - 2026-10-23

### Added

- **Per-step logs.** Recipe nodes have a Logs action that opens the log lines for
  that step from the current job.
- Final editor/scale polish for the 0.49–0.51 sequence.
- UI build guard from 0.49 keeps future releases from bundling a stale UI.

### Notes

- 452 Python tests, 8 media tests, 14 Vitest tests, and 12 Playwright tests pass.
- Kdenlive exact cross-dissolve and manual NLE QA remain pending.
- Distribution remains out of scope.

## [0.50.0] - 2026-10-23

### Added

- **Local pyannote auto-detection.** If the Models catalog installed the model,
  `audio.diarize` uses it when `model_path` is the default Hugging Face id.
- **Streaming Pexels downloads.** Stock clips are written chunk-by-chunk to a
  `.part` file instead of being buffered entirely in memory.
- **Melt plugin diagnostics.** `melt_check.py` reports failed filter/transition
  plugin loads separately from the render verdict.

### Notes

- 452 Python tests, 8 media tests, 14 Vitest tests, and 12 Playwright tests pass.
- Exact Kdenlive cross-dissolve and manual NLE QA remain pending.
- Distribution remains out of scope.

## [0.49.0] - 2026-10-23

### Added

- **Cycle prevention in the canvas.** New edges that would create a cycle are
  rejected immediately.
- **Undo/redo** for structural edits and node drags.
- **Array fields** render as JSON textareas with inline parse validation.
- **UI build guard.** `build_portable.py` rebuilds the Svelte UI and refuses a
  stale `ui/build/index.html` whose version differs from `version.ts`.
- Fixed the 0.48 local release mismatch where the server was 0.48.0 and the
  bundled UI was 0.34.0.

### Notes

- Node width remains a cycle control, not drag-resize.
- 452 Python tests, 8 media tests, 14 Vitest tests, and 12 Playwright tests pass.

## [0.48.0] - 2026-10-23

### Added

- **Pagination.** Jobs, batches, and persisted run history accept `limit` and
  `offset` and return `total`.
- **Batch history UI.** The batch modal lists persisted batches and loads them.
- **Proxy preview UI.** Successful jobs can generate and play the 540p proxy.
- **Viewport and node width persistence** in the recipe canvas.
- Tests for history pagination, batch pagination, and job listing.

### Notes

- Arrays and deeply nested objects still use the advanced JSON editor.
- Kdenlive cross-dissolve and manual NLE QA remain pending.
- 452 Python tests, 8 media tests, 14 Vitest tests, and 10 Playwright tests pass.
- Distribution work remains out of scope.

## [0.47.0] - 2026-10-23

### Added

- **Saved viewport.** The recipe canvas restores the persisted pan/zoom and saves
  viewport changes.
- **Node width cycling.** Expanded nodes cycle between compact, medium, and wide
  widths; the choice is persisted.
- **Proxy preview in the UI.** A 540p proxy can be generated from a successful
  job and played inline.
- **Persisted batch history.** The batch modal lists stored batches and loads
  them.
- URL and schema-pattern validation for inline fields.

### Notes

- Arrays and deeply nested objects still fall back to the advanced JSON editor.
- 449 Python tests, 8 media tests, 14 Vitest tests, and 10 Playwright tests pass.

## [0.46.0] - 2026-10-23

### Added

- **pyannote model downloader.** The Models catalog can install
  `pyannote/speaker-diarization-3.1` through `huggingface_hub`, using
  `HF_TOKEN` when the repository is gated.
- Installed model detection checks for `config.yaml`.
- Mocked install test for the Hugging Face path.

### Notes

- Real pyannote inference still requires the `diarization` extra and model
  access; the adapter remains lazy.
- Kdenlive cross-dissolve and manual NLE import QA remain pending.
- 449 Python tests, 8 media tests, 14 Vitest tests, and 8 Playwright tests pass.

## [0.45.0] - 2026-10-23

### Added

- **Preview proxy.** `POST /api/v1/jobs/{id}/preview` writes a 540p
  H.264/AAC proxy, served by `GET /api/v1/jobs/{id}/preview/file`.
- **Global cache pruning.** `prune_cache` trims analysis entries by age and
  total size; exposed through `videoflow recipe cache prune --global-cache` and
  the maintenance API.
- **Engine cleanup.** Removed the unimplemented `PipelineRunner.execute`
  scaffold; legacy planning remains, execution belongs to the recipe engine.
- Tests for the preview proxy and global cache pruning.

### Notes

- Preview is generated on demand; it is not automatically created after every
  render.
- 448 Python tests, 8 media tests, 14 Vitest tests, and 8 Playwright tests pass.
- Distribution work remains out of scope.

## [0.44.0] - 2026-10-23

### Added

- **Second-source audio mix.** `shorts.render.mix_second_audio` mixes the second
  split-screen source with the primary audio, with a UI checkbox.
- **Stable Pexels cache.** Stock downloads are keyed by the source URL hash, so
  repeated plans reuse the same file instead of re-downloading.
- B-roll plan remains auditable with provider, license, attribution, and source
  URL.

### Notes

- The second source is still operator-supplied; face detection and automatic
  source assignment remain future work.
- pyannote and Pexels still need real model/API validation.
- 445 Python tests, 14 Vitest tests, and 8 Playwright tests pass.

## [0.43.0] - 2026-10-23

### Added

- **Inline recipe nodes.** Each node expands into schema-derived fields with
  labels, descriptions, validation, enums, booleans, numbers, colors and path
  pickers.
- **Saved canvas.** Recipe JSON carries optional `ui` layout metadata:
  positions, expanded/pinned state, width, and viewport. UI-only changes do not
  invalidate checkpoints.
- **Autosave layout.** Dragging or pinning a node saves the recipe layout after a
  short debounce. `Auto layout` resets positions.
- **Per-step progress.** `StepIO` reports local progress; jobs expose
  `step_progress`; each node shows state and percentage.
- **Field validation.** Drafts remain editable, but Run is blocked while fields
  have errors. Server validation remains authoritative.
- Playwright coverage for saved inline layout and direct node edits.

### Notes

- 445 Python tests, 14 Vitest tests, and 8 Playwright tests pass.

## [0.42.0] - 2026-10-23

### Added

- **MLT/Kdenlive render smoke.** `scripts/melt_check.py` renders a generated
  Kdenlive/MLT project with `melt` and returns a JSON verdict.
- A media test builds a real two-cut project, exports Kdenlive, and renders it
  with `melt` when available.
- CI installs `melt` and runs the media suite.
- Final Windows, AppImage, Linux, and SBOM assets are produced by the tag
  release workflow.

### Notes

- The exact Kdenlive cross-dissolve remains a limitation; the generated project
  uses affine opacity/volume fades.
- Manual Resolve/Premiere/Kdenlive import QA remains pending.
- 443 Python tests, 8 media tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.41.0] - 2026-10-23

### Added

- **Inline preview.** MP4 artifacts render in the recipe result panel, and
  rendered Shorts get video previews.
- **Artifact serving API.**
  - `GET /api/v1/jobs/{id}/artifacts/{name}`.
  - `GET /api/v1/jobs/{id}/shorts/{index}/file`.
  - Both paths are constrained to the job output directory.
- API tests for artifact and Short file serving.

### Notes

- Previews use the rendered file; there is no low-res proxy yet.
- 443 Python tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.40.0] - 2026-10-23

### Added

- **Job persistence.** `JobManager` writes each job as JSON under the VideoFlow
  home and reloads it on restart. Queued/running jobs become `failed` with
  `job_interrupted`, so the API never reports a dead job as live.
- **Batch resume.** `POST /api/v1/batches/{id}/resume` and the batch modal
  restart failed/cancelled batches, skipping items already succeeded.
- **Shared persistence pattern** for jobs and batches: atomic JSON writes,
  restart reload, interrupted-state recovery.
- Tests for job restart, interrupted jobs, and batch resume.

### Notes

- The legacy `PipelineRunner.execute` contract remains an xfail; planning is
  live, and the recipe engine is the execution path.
- 442 Python tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.39.0] - 2026-10-23

### Added

- **Tag-driven release workflow.** `v*` tags build Linux, AppImage, and Windows
  artifacts, generate an SBOM, stage checksums, and publish the GitHub release.
- **Windows smoke test.** The Windows runner executes `version`, `doctor`, and
  `demo` before uploading the executable.
- **Media tests in CI.** `pytest -m media --no-cov` now runs on Ubuntu.
- **SBOM.** `scripts/generate_sbom.py` writes a CycloneDX-style JSON SBOM; the
  release includes `sbom.json`.
- **Automatic retention.** Successful recipe runs prune checkpoints beyond 200
  and run history beyond 30. Opt out with `VIDEOWFLOW_PRUNE_AFTER_RUN=0`.
- Fixed the media API test to force the FFmpeg VAD path instead of depending on
  Silero's speech classification.

### Notes

- 439 Python, 14 Vitest, and 6 Playwright tests pass.
- Media suite: 7 passing.

## [0.38.0] - 2026-10-23

### Added

- **Two-source split-screen.** `shorts.render.second_source_path` renders the
  left panel from the main source and the right panel from a second angle.
  Without a second source, the same-source two-panel layout remains.
- UI control and file picker for the second split-screen source.
- Repository policy test: project configuration and test data are JSON; only
  GitHub Actions workflows may be YAML.
- Playwright coverage for the second-source control.
- Final Windows PE workflow run and release attachment.

### Notes

- Exact Kdenlive cross-dissolve is still not validated; Kdenlive uses the
  affine opacity/volume transition fades.
- Manual Resolve/Premiere/Kdenlive import QA remains pending.
- 439 Python tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.37.0] - 2026-10-22

### Added

- **Schema-driven inspector.** Primitive parameters are rendered from each
  step's `params_schema` (boolean, number, enum, text), not only from the
  hand-written quick controls.
- **NLE validation in the UI.** A Validate action calls
  `POST /api/v1/exports/validate` and shows per-format status, counts, errors,
  and warnings.
- **B-roll plan viewer.** Job results expose `broll_plan`, and the UI shows the
  provider, license, and path for each planned clip.
- **Persistent batch history.** Batch JSON is written to the VideoFlow home,
  reloaded on restart, and interrupted batches are marked failed.
- Playwright now covers schema fields and the NLE validation modal.
- JSON-only configuration policy documented for project data and tests.

### Notes

- GitHub Actions still uses YAML because the platform requires it.
- 437 Python tests and 5 Playwright tests pass.

## [0.36.0] - 2026-10-22

### Added

- **Schema gates.** Recipes and project state now pass through explicit
  `schema_version` migration functions. Missing optional fields in older recipe
  JSON are filled before validation; future versions fail with a typed error.
- **Output maintenance.** `prune_output` removes old checkpoints beyond a keep
  count, stale B-roll cache files, and trims run history.
- CLI: `videoflow recipe cache prune --output ... --keep-steps ... --keep-runs ...`.
- API: `POST /api/v1/maintenance/prune`.
- Tests for migrations, malformed/future versions, checkpoint pruning, history
  trimming, and dry runs.

### Notes

- Checkpoints are still output-local and can be rebuilt; pruning never touches
  source media or export artifacts.
- 434 Python tests pass.

## [0.35.0] - 2026-10-22

### Added

- **Failed-run diagnostics.** Recipe failures write `work/failure.json` with the
  stage, error payload, FFmpeg command, stderr tail, and the last 200 log lines.
- **Failed runs in history.** `run-history.json` now records `failed` and
  `cancelled` runs with their error, so the UI survives restarts and shows them.
- **Playwright E2E.** Installed `@playwright/test`, added a JSON reporter, and
  covered the recipe graph, inspector transition controls, step palette, and
  persisted run-history browser.
- Refactored job history recording into one path for success, failure, and
  cancellation.
- `docs/testing.md` now reflects CI and Playwright.

### Notes

- GitHub Actions still needs a Playwright step; this release wires the local
  command and JSON report first.
- 427 Python tests, 14 Vitest tests, and 3 Playwright tests pass.

## [0.34.0] - 2026-10-22

### Added

- **NLE structural validation.** `scripts/validate_nle.py` and
  `POST /api/v1/exports/validate` parse FCPXML, XMEML, and Kdenlive exports and
  report clips, transitions, keyframes, effects, and affine filters.
- **Manual NLE checklist** in `docs/nle-qa.md`.
- **Legacy module rerun.** The project module route plans the rack graph,
  returns a cached no-op, or starts the full project pipeline. It no longer
  returns `501`.
- **Windows PE in releases.** The Windows workflow downloads a PE32+ x86-64
  executable and the release script attaches it when present.
- CI can be dispatched manually and runs Python and UI checks.

### Notes

- The legacy module route reruns the full graph; it does not yet execute one
  module in isolation. Recipe steps remain the checkpointed path.
- Resolve, Premiere, and Kdenlive are not installed here, so manual import QA is
  still pending. Automated XML validation passes.
- The Windows binary is unsigned; SmartScreen may warn.
- 426 Python tests and 14 UI tests pass.

## [0.33.0] - 2026-10-22

### Added

- **Optional model-based diarization.** `audio.diarize` supports
  `method: "pyannote"` with `model_path`, `device`, and an HF token environment
  variable. It falls back to the pause heuristic by default.
- **Pexels B-roll provider.** `broll.plan` can search and download portrait
  stock clips using `PEXELS_API_KEY`; local assets remain the default.
- **Dialogue split-screen.** `shorts.reframe` marks multi-speaker clips for the
  two-panel layout, and the renderer supports per-panel focus and zoom.
- B-roll plans now include provider, license, attribution, and source URL.
- UI controls for pyannote, Pexels, dialogue split, and panel focus/zoom.
- Optional `diarization` dependency extra.

### Notes

- Pyannote is not installed in this build; the adapter is lazy and tested with a
  fake pipeline plus the heuristic fallback.
- Pexels is opt-in and requires an API key; local B-roll remains fully offline.

## [0.32.0] - 2026-10-22

### Added

- **Kdenlive transforms and keyframes.** Video entries receive an MLT `affine`
  filter with static geometry or `transition.rect` keyframes.
- **Kdenlive transition fades.** Clip transitions add opacity keyframes and
  volume ramps in the MLT project.
- **Recipe inspector quick controls** for transition frames/type, progressive
  zoom, speaker turns, B-roll directory, split-screen, B-roll application, and
  caption speaker colors.
- **Run history browser** in the Recipes tab, with persisted runs and comparison.
- **Piper provider controls** in the Short editor, with binary and model path.
- README, exporter docs, and capability status updated.

### Notes

- Kdenlive crossfades are emitted as opacity/volume fades rather than a validated
  exact cross-dissolve; Kdenlive itself is not available on this build host.
- 419 Python tests and 14 UI tests pass.

## [0.31.0] - 2026-10-22

### Added

- **Heuristic speaker turns.** `audio.diarize` assigns speaker ids by pause
  length. Captions use `CaptionStyle.speaker_colors` for per-speaker colors.
- **Local B-roll.** `broll.plan` matches files in a local asset directory to
  selected Shorts and writes `broll.json`; `shorts.render` applies full-frame
  B-roll overlays.
- **Split-screen Shorts.** `shorts.render` accepts `split_screen` and renders a
  two-panel vertical frame.
- **Local Piper TTS.** The voice-over route accepts `provider: "piper"` with a
  binary and voice model path, in addition to OpenAI-compatible TTS.
- Capability manifest entries for transitions, speaker turns, B-roll,
  split-screen, and local TTS.

### Notes

- Diarization is heuristic, not model-based speaker identification.
- B-roll is local-asset matching, not a stock-video search service.
- Kdenlive parity for transforms and transitions remains pending.

## [0.30.0] - 2026-10-22

### Added

- **Persistent run history.** Successful recipe runs append a compact record to
  `<output>/work/run-history.json`; `GET /api/v1/runs?output=...` exposes it.
  The comparison modal uses this history, so it survives a server restart.
- **GitHub Actions CI.** Linux tests and UI checks run on push and pull request.
- **Windows portable build workflow.** A `windows-latest` workflow builds and
  uploads `videoflow.exe`.
- **Optional onedir build.** `scripts/build_portable.py --onedir` uses PyInstaller
  `COLLECT` instead of a onefile executable.

## [0.29.0] - 2026-10-22

### Added

- **Clip transitions.** `VideoSegment.transition_out` carries a
  `Transition` with `crossfade` or `fade_to_black`, duration, and audio flag.
- `edit.timeline` accepts `transition_frames` and `transition_type`.
- **FCPXML** emits a `transition` element between clips.
- **XMEML** emits a video `transitionitem` with Cross Dissolve/Fade to Black.
- **MP4** uses `xfade`/`acrossfade` for crossfades and video/audio fades for
  fade-to-black.
- Project-state schema updated for transitions.

### Notes

- Kdenlive does not apply clip transforms or per-cut transitions yet.
- The transition duration reduces the MP4 duration for crossfades because the
  clips overlap, as expected.

## [0.28.0] - 2026-10-22

### Added

- **Progressive zoom keyframes.** `Transform` now carries normalized scale
  keyframes. `progressive_zoom` generates two smooth keyframes (minimum scale
  to punch-in scale) for alternating clips.
- **FCPXML keyframes.** `adjust-transform` emits a keyframed `scale` parameter
  with clip-relative rational times.
- **XMEML keyframes.** Basic Motion scale emits `keyframe` entries with
  clip-relative frame positions.
- **MP4 keyframes.** The direct renderer uses `zoompan` for clips with
  keyframes, keeping the output dimensions stable.
- Project state schema updated for `TransformKeyframe`.

### Notes

- Kdenlive does not apply clip transforms yet, so keyframes are not represented
  there.
- Transitions between clips remain the next editing pass.

## [0.27.0] - 2026-10-22

### Added

- **Run comparison.** After a successful recipe run, the UI finds the previous
  successful job for the same output and recipe and offers a comparison modal.
  It shows duration, cached/executed counts, warnings, and a per-step table with
  previous/current status and elapsed milliseconds.
- The comparison uses the normal job history; no new persistent store is
  required.

### Notes

- Keyframed progressive zooms and video transitions remain the next creative
  editing pass. This release focuses on run observability.

## [0.26.0] - 2026-10-22

### Added

- **Direct main-timeline MP4 render.** `export.nle` accepts `mp4` as a target.
  The exporter builds a filter graph from the validated timeline, applies
  J/L-cut audio ranges, fades, and static transforms, and writes H.264/AAC with
  `+faststart`. The legacy job form and recipe editor expose the target.
- **Folder batches.** `videoflow recipe batch`, `POST /api/v1/batches`,
  `videoflow_run_batch`, `videoflow_get_batch`, and `videoflow_cancel_batch`
  process a folder one file at a time. Each item is a normal job with its own
  output folder, progress, cancellation, logs, and recipe checkpoints.
- **Batch UI.** The Recipes tab has a **Batch** modal with folder pickers,
  recursive mode, extension filter, item-level progress, and cancel.
- **Capability manifest entries** for direct MP4 and folder batches.

### Changed

- `ExportParams.targets` and `NewJobRequest.export_targets` accept `mp4`.
- `FFmpegAdapter.render` is implemented with a one-hour render timeout.
- Built-in recipe validation now enforces required upstream step types.

### Validation

- 405 Python tests passed; 14 UI tests passed.
- Real FFmpeg media rendered through the timeline filter graph and was probed
  back at the source dimensions.
- A two-file batch completed both items into separate output folders.

## [0.25.0] - 2026-10-22

### Added

- **Per-step checkpoints.** Every successful recipe step writes
  `work/steps/<id>/manifest.json` and `snapshot.json`. A fingerprint covers the
  step type/version, validated parameters, source fingerprint, and upstream
  step hashes. Matching steps are reused across runs in the same output
  directory, and file-producing steps verify that their outputs still exist.
- **Step-scoped runs.** `POST /api/v1/steps/{step_id}/run`,
  `videoflow recipe step ...`, and the MCP tool `videoflow_run_step` execute a
  step and its dependency closure, then stop.
- **Resume controls.** `videoflow recipe run|step --force` ignores
  checkpoints; the Recipes Config modal has a reuse-checkpoints switch.
- **Per-node execution state.** The graph shows cached, executed, running, and
  failed nodes. The inspector has **Run to here**.
- **Step run reporting.** Job results and `run.json` expose `step_runs` with
  status, elapsed time, fingerprint, and outputs.
- **Dependency validation.** Recipes are rejected when a step's declared
  upstream types are missing, preventing steps from running with absent VAD or
  transcript context.

### Fixed

- `retakes.cull` now explicitly requires `audio.vad` in addition to the
  transcript, so partial runs cannot subtract culls from empty speech.
- Built-in Shorts recipes place NLE export after Shorts rendering.

## [0.24.0] - 2026-10-22

### Added

- **Independent Shorts steps.** `shorts.select`, `shorts.reframe`,
  `shorts.captions`, and `shorts.render` are separate nodes. Reframe tracking
  and ASS caption generation no longer happen inside selection/render.
- **Recipe analysis cache.** `audio.vad` and local/HTTP `transcribe` results are
  cached by source PCM digest plus step parameters under
  `<videoflow-home>/cache/recipe-v1/`. The cache is shared across output
  directories. `videoflow recipe cache path|clear` inspects or clears it;
  `VIDEOWFLOW_RECIPE_CACHE=0` disables it.
- **Cache hit/miss reporting.** `run.json`, job results, and `PipelineContext`
  expose `cache_hits` and `cache_misses`.
- **Full-width recipe canvas.** The Recipes tab now spans the whole content
  area and hides the legacy run-summary sidebar while active.
- **Collapsible recipe controls.** The step inspector is an overlay that opens
  on node click; the step palette is a filterable popover; recipe settings and
  the full recipe/step JSON editor are modal dialogs with a large text area.

### Changed

- The built-in Shorts recipes now run `shorts.reframe` and `shorts.captions`
  explicitly before `shorts.render`.
- `shorts.select` no longer tracks faces. If a recipe sets a non-center
  `reframe_mode` on selection, it emits a warning and leaves tracking to
  `shorts.reframe`.

### Fixed

- Added a test-isolation home so recipe cache entries never touch the
  developer's real `~/.videoflow` directory.

## [0.23.1] - 2026-10-22

### Fixed

- Recipe path parameters are now resolved through the same allowlist jail as
  media, output, and transcript paths. This covers `srt_path` and the
  overlay/music/intro/outro assets of `shorts.render` in REST and MCP runs.
- Built-in Shorts recipes now depend on the retakes step, so selection uses the
  same cull decisions as the main timeline instead of racing it.
- Operator recipes under the VideoFlow home directory override built-in recipes
  with the same id, and recipe ids are validated before any filesystem lookup.

## [0.23.0] - 2026-10-22

### Added

- **Recipe engine v1.** Recipes are versioned DAGs of typed steps with
  explicit dependencies, stable ids, parameter schemas, progress, cancellation,
  and per-step hashes. The engine validates duplicate ids, unknown step types,
  missing dependencies, disabled dependencies, and cycles before execution.
- **Step registry.** Ingest, voice detection, transcription, retakes, timeline,
  Shorts selection, Shorts rendering, and NLE export are independently
  invocable. The legacy pipeline remains available and is covered by a parity
  test against the recipe path.
- **Recipes tab, first in the workspace.** A Svelte Flow canvas edits the DAG,
  exposes JSON parameters per node, loads built-in recipes, validates, saves,
  downloads, and runs jobs with live progress.
- **Recipe API.** `GET /api/v1/steps`, `GET /api/v1/recipes`,
  `GET /api/v1/recipes/{id}`, `PUT /api/v1/recipes/{id}`,
  `POST /api/v1/recipes/validate`, and `POST /api/v1/recipes/run`.
- **Recipe MCP tools.** `videoflow_list_steps`, `videoflow_list_recipes`,
  `videoflow_get_recipe`, `videoflow_validate_recipe`,
  `videoflow_save_recipe`, `videoflow_run_recipe`, and
  `videoflow_run_recipe_inline`.
- **Recipe CLI.** `videoflow recipe list|steps|show|validate|run`.
- **Built-in recipes and examples.** `youtube_talking_head`,
  `viral_shorts_batch`, and `full_podcast_curation`, mirrored under `recipes/`.
- **LLM router.** OpenAI-compatible local/cloud endpoints are the default; an
  opt-in OpenCode CLI adapter adds timeouts, a non-shell subprocess, output
  limits, and strict JSON parsing. Secrets are stored by environment variable
  name, never inside recipes.
- **Recipe JSON Schema** at `schemas/recipe.schema.json`.

### Notes

- The visual editor is additive: the existing Speech, Edit, Shorts, Studio,
  Export, Models, Services, and Providers tabs remain available.
- The v1 recipe scope is the current pipeline. B-roll, TTS, and new vision
  models remain future steps.

## [0.22.3] - 2026-10-21

### Fixed

- Moved the workspace tabs (Speech, Edit, Shorts, Studio, Export, Models,
  Services, Providers) directly under the header as a sticky navigation bar.
  Shorts, Models, and Services no longer disappear below the New project card.
- Removed a duplicated connection banner inside the header that pushed the page
  down and made the tab bar harder to find.
- Added cache-control headers: `index.html` and `/` are `no-store`; hashed
  `_app/immutable` assets are immutable; other UI assets are revalidated.
- The browser now opens with `?v=<version>`, preventing an old UI bundle from
  being reused after an update.
- Added a UI/server version mismatch banner with a **Reload UI** action.
- Added a per-port startup lock so double-clicking the AppImage several times
  does not start competing servers; later launches wait for health and open the
  existing UI.
- Verified the AppImage starts from a detached, no-terminal session, keeps
  running, serves the UI, and exposes the Services tab.

## [0.22.2] - 2026-10-21

### Fixed

- Starting a new VideoFlow build no longer reuses an older service on the same
  port. The launcher reads `/health`, compares versions, stops the old
  VideoFlow process tree, waits for the port, and starts the current version.
  This removes the "already running" loop that kept a 0.20.0 service alive.
- Discovery now finds VideoFlow `serve`/`mcp`/`desktop` processes through
  `/proc`, including AppImage-mounted binaries and their parent processes.
- Added a **Services** tab with the current PID, port, version, URL, other
  VideoFlow services, per-process Stop, Stop all others, Restart current, and
  Stop current.
- The Services tab shows the server log and its path; startup, version
  replacement, cleanup, restart, and crashes are appended to
  `videoflow-data/logs/server.log`.
- `videoflow status` now lists discovered services in addition to the PID file.
- Cleanup stops port-owning children before launchers/parents and falls back to
  SIGKILL when SIGTERM does not finish in time.

## [0.22.1] - 2026-10-21

### Fixed

- The local file browser no longer turns a damaged or out-of-range file
  timestamp, unreadable entry, or deleted current directory into an HTTP 500.
  Failed entries are skipped and the picker offers "Open Home folder".
- Service lifecycle: `serve` keeps the executable running, writes
  `server.pid`, detects an already-running instance, and can be managed with
  `videoflow status`, `videoflow stop`, and `videoflow restart`.
- The rack header now has **Restart service** and **Stop service** buttons.
  Restart reuses the in-memory job manager and recreates the MCP session.
- The AppImage starts in the user's home directory and prints explicit
  instructions for keeping the service running or stopping it.

## [0.22.0] - 2026-10-21

### Added

- OpenAI-compatible multimodal Short analysis through
  `POST /api/v1/jobs/{job_id}/shorts/{index}/analyze/llm` and
  `videoflow_analyze_short_llm`. Frames are sampled locally, sent only when
  external services are enabled, and the result is persisted in `shorts.json`.
- A separate Studio tab with AI Analysis, Timeline, Keyframes, Tracks, and
  Transitions sections. AI Analysis runs vision analysis; Timeline opens the
  per-Short editor; the other sections expose reframe, track, and transition
  state.
- LLM emoji captions: `POST /api/v1/jobs/{job_id}/shorts/{index}/captions/emoji`
  and `videoflow_generate_short_emoji` generate a validated emoji map and
  re-render the Short with it.
- Optional model downloads through `GET /api/v1/models`,
  `POST /api/v1/models/{id}/install`, `DELETE /api/v1/models/{id}`, the Models
  tab, and three MCP tools. Downloads are checksum-verified and stored under
  the portable home directory.
- Lean portable builds: speech model weights are excluded unless
  `VIDEOWFLOW_BUNDLE_MODELS=1` or `scripts/build_portable.py --with-models` is
  used. Downloaded models are resolved at runtime without rebuilding.
- 30 transcription language codes across CLI/API/MCP/UI, including auto-detect.
- Short render resolution selection: 1080, 1440, or 2160 short-edge. 4K renders
  as 2160x3840 vertical, 2160x2160 square, or 3840x2160 landscape.

- Tabbed rack navigation: Speech, Edit, Shorts, Export, and Providers. Each tab
  shows only the modules and controls that belong to that area.
- A provider/capability panel backed by `GET /api/v1/capabilities` and the
  `videoflow_list_capabilities` MCP tool. External providers are opt-in per run
  and can be blocked globally with `VIDEOWFLOW_ALLOW_EXTERNAL=0`.
- `ProvidersConfig` in project state. `allow_external_services` is persisted and
  forwarded by project runs.
- Short render aspect ratios: `9:16`, `1:1`, and `16:9`. ASS PlayRes and FFmpeg
  dimensions follow the selected aspect.
- Short source window: `shorts_source_start_sec` and `shorts_source_end_sec` in
  the CLI, API, MCP, project config, and UI.
- Duration presets in the Shorts tab and an aspect-aware caption preview.
- Per-Short editor: trim, retitle, aspect/frame size, caption overrides, and
  re-render. The API is `POST /api/v1/jobs/{job_id}/shorts/{index}/edit`, the
  MCP tool is `videoflow_edit_short`, and the rack uses Clip/Captions tabs.
- Prompt-to-Clip and reprompt for Short selection: topic focus, refinement
  context from the previous `shorts.json`, heuristic term boosts, and LLM focus.
  Exposed in CLI, API, MCP, project config, and the Shorts tab.
- Auto hook (`off`, `metadata`, `repeat`, `reorder`) and an explainable 0–100
  virality score with a per-factor breakdown. Hook/score metadata appears in
  `shorts.json` and the rack.
- Short result badges expose the selected aspect, virality score, and hook text.
- Caption profanity masking with a configurable word list/replacement.
- Optional filler-word cuts for Shorts when word timings are available.
- Deterministic social metadata (title, description, hashtags, character limits)
  for YouTube, TikTok, Instagram, and LinkedIn, exposed via API/MCP and the
  Short editor's Metadata tab.
- Caption keyword highlighting, contextual emoji mapping, and brand vocabulary
  rewriting. Empty keyword lists auto-select frequent content words.
- Custom TTF/OTF font upload with internal-family detection, a local font asset
  store, UI font picker, `fontsdir` rendering, and API/MCP access.
- Short thumbnail generator: frame extraction plus caption-style title overlay,
  persisted under `shorts/thumbs/` and exposed through API/MCP/UI.
- Optional FFmpeg speech enhancement for rendered Shorts: high-pass, FFT
  denoise, and loudness normalization, with API/MCP/UI/CLI controls.
- Watermark overlay: PNG/JPEG asset store, position/margin/width/opacity
  controls, API/MCP/UI access, and post-caption compositing.
- Background music: MP3/WAV/M4A/AAC/OGG asset store, looping bed, volume,
  fades, sidechain ducking, and AAC mix output.
- External TTS voice-over: OpenAI-compatible synthesis, environment-only API
  key, original-audio ducking, mixed MP4, API/MCP/UI controls.
- Intro/outro image cards with configurable durations, normalized size, silent
  audio, and API/MCP/UI access.
- Translation dubbing: external LLM translation, TTS synthesis, dub-only mix,
  and API/MCP/UI controls.
- Reusable brand templates bundling caption style, overlay, music, and
  intro/outro settings, with save/apply/delete and server-side job application.
- Motion-tracking reframing with frame-difference focus, optional OpenCV face
  tracking fallback, and persisted crop focus.
- Project templates and versioned config export/import for non-secret run
  options.
- Audio-energy peak analysis that boosts Short candidates and exposes peak
  counts.
- FFmpeg scene-change analysis that boosts Short candidates around visual cuts
  and exposes scene counts.
- Public URL import through yt-dlp, external-policy guarded, with API/MCP/UI
  integration and normal media probing.
- Webhook publishing and scheduling with target CRUD, generated metadata, a
  durable queue, bearer-token secret references, and a local daemon.
- Optional multimodal Short analysis: audio-emotion heuristics, visual motion
  regions, and OpenCV face statistics when installed.

### Changed

- `scripts/release.py` now keeps only the three newest `releases/v*` folders.
  `--keep N` changes the retention count, and the release output lists every
  pruned folder.
- Release staging is documented as the canonical artifact store. Generated
  `build/`, `dist/`, coverage files, and caches are cleaned after each release.
- MCP now exposes thirty-six tools and four resources.

### Docs

- Refreshed the README, module specs, testing notes, UI spec, and operator
  manuals to describe FCPXML audio fades, the caption preview, the tabbed rack,
  provider policy, Short aspect ratios, and the three-release retention policy.

### Verified

- Tests: 370 passed, 11 xfailed, 7 deselected; coverage 99.06%; ruff and mypy
  clean.
- UI: `svelte-check` reports 0 errors and 0 warnings; 13 Vitest tests and the
  production build pass.

## [0.21.2] — 2026-10-21

### Added

- The Shorts card now includes a live 9:16 caption preview. It follows the
  configured font, size, weight, italic/uppercase, primary and karaoke colors,
  outline, shadow, box, alignment, position, and animation.

### Fixed

- FCPXML/Resolve now emits audio fade edges as keyframed `adjust-volume` ramps
  on each `asset-clip`. The ramp uses the clip-relative `keyframeAnimation`
  form required by the FCPXML 1.9 DTD.
- FCPXML sequences declare the enumerated `audioRate` label (`48k`, `44.1k`, ...)
  instead of raw hertz. A generated timeline now validates against the FCPXML
  1.9 DTD.
- All three NLE artifacts now carry audio fades: xmeml transition items,
  Kdenlive volume filters, and FCPXML volume keyframes.

### Verified

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- UI: `svelte-check` reports 0 errors and 0 warnings; the production build
  succeeds with 13 Vitest tests.
- Linux and Windows binaries produced six xmeml fade items, a Kdenlive volume
  ramp, and FCPXML that validates against the official 1.9 DTD. Sizes and
  SHA-256 values are in `releases/v0.21.2/` and its `manifest.json`.

## [0.21.1] — 2026-10-21

### Fixed

- Premiere xmeml now writes single-sided `transitionitem` fades for audio
  fade-in and fade-out edges, using the Cross Fade (0 dB) audio transition.
- Kdenlive MLT audio entries now carry a keyframed `volume` filter for the same
  fades. The project still opens as a native `.kdenlive` sequence.
- FCPXML/Resolve fade transitions remain pending; the FCPXML artifact still
  carries the audio offsets but not dedicated fade elements.

### Verified

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- Linux and Windows binaries emitted six xmeml audio transition items and a
  Kdenlive volume keyframe ramp. Sizes and SHA-256 values are in
  `releases/v0.21.1/release-notes.md` and `manifest.json`.

## [0.21.0] — 2026-10-21

### Added

- Configurable zoom window: `min_scale`, `max_scale`, and `punch_in_scale` with
  validation and UI/API/MCP controls. The state model no longer hard-codes a
  1.30 maximum.
- Configurable audio fades: `fade_in_ms`, `fade_out_ms`, and `fade_curve` in the
  J/L-cut module, in addition to the existing crossfade and offset.
- Configurable Shorts selection: target count, minimum count, duration window,
  and `auto|llm|heuristic` ranking. The LLM client is created for Shorts even
  when retake culling is off, and the heuristic ranks hook/impact signals rather
  than taking the first windows.
- `videoflow run --shorts` with count/minimum/duration/selection flags, so the
  main project and vertical Shorts are produced together.
- Detailed caption/karaoke style: font family, size, weight, italic, uppercase,
  primary/highlight/outline colors, outline width, shadow color/offset/opacity,
  background box color/opacity/padding, alignment, normalized position, max
  width, animation, and word-timing fallback.
- ASS karaoke generation from word timings, with proportional and sentence
  fallbacks when an engine does not return word timestamps.
- The same caption and Shorts fields are available in the UI rack, job API,
  project config, presets, and MCP overrides. `videoflow_generate_shorts` now
  accepts `min_count` and `selection_mode`.

### Changed

- The setup card now has an explicit “Also render vertical shorts” control, and
  the “Main + Shorts” starting point makes clear that Shorts are additive.
- Shorts report a score and warning when fewer than the configured minimum can
  be selected.
- Audio fade timing/curve is now configurable and stored on the timeline. NLE
  transition elements for those fades remain a follow-up; the current exporters
  still carry the audio cut offsets rather than dedicated crossfade items.

### Verified

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- UI: 0 errors/warnings, 13 Vitest tests, production build passed.
- A real source with `--shorts` produced the main project and Shorts MP4s/ASS,
  including word-timed karaoke.
- Linux binary, AppImage, and Windows PE were built and smoke-tested. Sizes and
  SHA-256 values are in `releases/v0.21.0/release-notes.md` and
  `manifest.json`.

## [0.20.1] — 2026-10-20

### Fixed

- DaVinci Resolve FCPXML 1.9/1.10 media references now use the required
  `<media-rep kind="original-media" src="..."/>` child. The old `<asset src>`
  form is FCPXML 1.8-only and could make Resolve reject or offline the timeline.
- Premiere Pro now receives xmeml version 4 with `explodedTracks`, a sequence
  UUID, `file://localhost/` path URLs, a full `<file>` definition on every
  video and audio clipitem, and explicit A/V `<link>` groups. The Basic Motion
  effect id is now `basicmotion`.
- Kdenlive now receives a native `.kdenlive` MLT XML project instead of an OTIO
  file: profile, source chain, video/audio tractors, sequence tractor, bin, and
  final tractor. OTIO remains available as a library helper, not the Kdenlive
  deliverable.

### Changed

- The Kdenlive artifact is `timeline.kdenlive`; the API/MCP target key remains
  `kdenlive`. The historical `write_otio` config key still controls this
  artifact.
- Export tests now assert the media-rep, xmeml full-file/link shape, and native
  MLT structure.

### Verified

- Tests: 310 passed, 11 xfailed, 7 deselected; coverage 99.28%; ruff and mypy
  clean.
- Linux and Windows binaries wrote all three artifacts; each was parsed back as
  FCPXML, xmeml, or MLT XML and checked for its required media links and track
  structure. AppImage smoke passed.
- Sizes and SHA-256 values are in `releases/v0.20.1/release-notes.md` and
  `manifest.json`.
- The three NLE import flows still require a manual gate in Resolve, Premiere,
  and Kdenlive; this environment does not have those applications installed.

## [0.20.0] — 2026-10-20

### Added

- A local filesystem browser for the rack: `GET /api/v1/fs/roots`,
  `GET /api/v1/fs/list`, and `POST /api/v1/fs/mkdir`, with search, file-extension
  filters, hidden-file control, breadcrumbs, writable checks, and a 2,000-entry
  ceiling.
- `GET /api/v1/media/probe`, so selecting a source shows duration, resolution,
  frame rate, audio rate, and size without running the pipeline.
- `PathPicker.svelte` with keyboard navigation, focus trapping, loading, empty,
  and typed error states. It replaces typed source, output, SRT, and model paths
  in the primary flow.
- Source selection suggests `<source-stem>-videoflow` next to the source. The
  output picker can create a folder in place.
- A redesigned project setup: numbered source/output/transcript cards, metadata
  chips, YouTube/Lecture/Shorts starting points, a collapsed advanced section, a
  clear primary action, inline validation, progress details, and transient
  success toasts.
- Pure path helpers for POSIX and Windows basenames, parents, and output
  suggestions, covered by Vitest.

### Changed

- The rack no longer requires typing an absolute path in the normal flow.
  Advanced users can still paste paths under **Advanced paths and local models**.
- The primary action is disabled until both source and output are present, and
  source/output/transcript changes keep the UI state consistent.
- The run summary keeps the same job, artifact, recent-job, inspector, and log
  behavior while adopting the updated visual hierarchy.

### Security

- The browser is restricted to `VIDEOWFLOW_ALLOWED_ROOTS`; symlinks that escape a
  root are omitted or rejected. Directory creation validates a single portable
  segment, including Windows reserved names. No media is uploaded.

### Verified

- Tests: 309 passed, 11 xfailed, 7 deselected; coverage 99.28%; ruff and mypy
  clean.
- UI `check` reports 0 errors and 0 warnings; 13 Vitest tests pass and the
  production build succeeds.
- Frozen Linux UI: selected a real 48 kHz source, showed its metadata, created
  an output folder, ran the pipeline, and wrote all three exports.
- Linux binary, AppImage, and Windows PE were built. Windows `version`, `doctor`,
  `demo`, served filesystem routes, and a real Faster-Whisper run passed under
  Wine. Sizes and SHA-256 values are in
  `releases/v0.20.0/release-notes.md` and `manifest.json`.

## [0.19.0] — 2026-10-20

### Added

- Local Faster-Whisper 1.2.1 transcription through CTranslate2, with the full
  16 kHz WAV sent to the engine, word timestamps required for the quality path,
  and exact floor/ceil conversion from word seconds to source samples.
- `TranscribeConfig.engine` with `auto`, `faster-whisper`, and `whisper.cpp`.
  `auto` prefers Faster-Whisper when the optional package and selected model are
  present, then falls back to whisper.cpp. Explicit engines fail with an
  actionable hint instead of silently downgrading.
- `--whisper-engine`, `--model-size`, `--device`, `--compute-type`,
  `--whisper-vad`, and `--faster-whisper-model` in `videoflow run`; matching job
  API fields, project run options, MCP arguments/overrides, and rack controls.
- Local CTranslate2 model discovery through `VIDEOWFLOW_FASTER_WHISPER_MODEL`,
  the frozen bundle, the executable directory, and the portable home. A model
  directory must contain `model.bin` and `config.json`; models are never
  downloaded implicitly.
- `scripts/fetch_faster_whisper.py` with the pinned
  `Systran/faster-whisper-small` revision
  `536b0662742c02347bc0e980a01041f333bce120`, per-file sizes, and SHA-256
  verification.
- `--with-faster-whisper` and `--refresh-faster-whisper` in the portable build.
  PyInstaller collects Faster-Whisper, CTranslate2, Tokenizers, PyAV, Hugging
  Face Hub, and the ~484 MB small model under `faster-whisper/small/`.
- `doctor` reports the Faster-Whisper package version, resolved model, and
  readiness.
- Unit, contract, CLI, job, API, MCP, runtime, and portable coverage for engine
  selection, fallback, explicit failures, full-WAV calls, exact timestamps, and
  model discovery.

### Changed

- `transcribe` is now an `auto` local quality path. An SRT or project transcript
  still wins, and an ASR base URL still takes precedence over both local engines.
- Transcript sources are reported distinctly as `faster-whisper`, `whisper`,
  `asr`, `srt`, or `project`.
- The optional `faster-whisper` extra pins Faster-Whisper 1.2.1 and PyAV
  `>=11,<19`; PyAV 19 removes the `metadata_errors` argument used by 1.2.1.
- Release builds bundle the model and runtime, so artifacts are substantially
  larger than 0.18.0. A build without the flag keeps the whisper.cpp fallback.

### Verified

- Tests: 301 passed, 11 xfailed, 7 deselected; coverage 99.27%; ruff and mypy
  clean; UI check, Vitest, and production build pass.
- A real 48 kHz source produced a `faster-whisper` transcript with source-sample
  word timings; `auto` selected Faster-Whisper and an explicit whisper.cpp run
  still completed. The frozen Linux API and AppImage quality paths produced the
  same result.
- Linux 0.19.0 binary, AppImage, and Windows PE were built and smoke-tested.
  Windows `version`, `doctor`, `demo`, and a real Faster-Whisper run passed under
  Wine. Sizes and SHA-256 values are in
  `releases/v0.19.0/release-notes.md` and `manifest.json`.

## [0.18.0] — 2026-10-20

### Added

- Silero VAD v5.1.2 as the quality speech detector, running through ONNX
  Runtime on the CPU with 16 kHz mono PCM, 512-sample windows, and the pinned
  `state` tensor carried between windows.
- Typed VAD engine selection: `auto` prefers Silero when the model and
  `onnxruntime` are available, `silero` requires it, and `ffmpeg` forces
  `silencedetect`. Explicit Silero failures are actionable instead of silent.
- Exact floor/ceil rescaling from 16 kHz windows to source sample spans, plus
  speech pads that are applied after retake culling and clamped to the media
  duration.
- `--vad-engine`, `--speech-threshold`, `--speech-pad-before-ms`, and
  `--speech-pad-after-ms` in `videoflow run`; matching job API, project config,
  MCP overrides, and rack fields.
- `vad_engine` in job results, `run.json`, MCP VAD results, project-state
  config, and JSON Schemas; `doctor` reports the model and ONNX Runtime.
- `scripts/fetch_silero.py` with a pinned URL, SHA-256 verification, and
  `vendor/silero/silero_vad.onnx`; `--with-silero` and `--refresh-silero` in
  the portable build. PyInstaller bundles the model and ONNX Runtime.
- Unit, contract, CLI, project, job, runtime, and portable coverage for Silero,
  engine selection, rescaling, pads, fallback, and packaging.

### Changed

- `work/vad.wav` is written at 16 kHz only when Silero runs; `work/source.wav`
  remains at the source rate and FFmpeg remains the portable fallback.
- Release builds now bundle the Silero model. A build without `--with-silero`
  still runs: `auto` falls back to FFmpeg and `silero` fails with a fetch/build
  hint.
- `videoflow demo` explicitly uses FFmpeg so the self-contained demo does not
  depend on the optional VAD model.

### Verified

- Tests: 284 passed, 12 xfailed, 7 deselected; coverage 99.26%; ruff and mypy
  clean; UI check, Vitest, and production build pass.
- Linux 0.18.0 binary, AppImage, and Windows PE were built and smoke-tested,
  including Silero `vad_engine=silero` runs. The PE was validated under Wine.
- Frozen Linux and Windows project and MCP flows passed with Silero and
  revision snapshots `000001` through `000004`.
- Auto fallback was verified with a missing model; explicit Silero failed with
  `ingest_failed` and the fetch/build hint.

## [0.17.0] — 2026-10-20

### Added

- Persistent projects under `<root>/.videoflow/`: a compact registry, atomic
  state writes, monotonically increasing `revision`, and append-only snapshots
  under `revisions/`.
- Project REST routes: create/list/read, media registration, module config and
  enabled flags, full project run, cancel, SSE events, transcript read and
  sentence overrides, exports, and preset application.
- `ProjectState.revision`, starting at 1 and written into every snapshot.
- Project runs preserve `project_id`, module config, enabled flags, transcript
  word timings, manual overrides, export target flags, and FCPXML dialect.
- Operator presets under `$VIDEOWFLOW_HOME/presets/`, with partial-file
  validation, shipped-name shadowing, list/read/write routes, and atomic apply
  to a project.
- Shared SRT formatting in the domain, used by the REST transcript route and
  MCP resources.

### Changed

- `run_portable` and `JobManager` accept project metadata, revision, config,
  enabled flags, and a preloaded transcript; successful project jobs snapshot
  the state they wrote.
- Per-module reruns return typed `501 not_implemented` until the cache-backed
  module runner lands. The full project run is implemented.
- Project media registration and transcript overrides invalidate stale derived
  results instead of leaving old timeline data looking current.
- API docs now describe the implemented project contract and error statuses.

### Verified

- Tests: 269 passed, 13 xfailed, 7 deselected; coverage 99.26%; ruff and mypy
  clean.
- Project route contracts cover create/list/read, media jail, config validation,
  enabled flags, transcript overrides, exports, presets, project runs, events,
  cancellation, and active-job rejection.
- Linux 0.17.0 binary and AppImage plus Windows PE 0.17.0 build and smoke checks
  are recorded in `releases/v0.17.0/release-notes.md`.

## [0.16.0] — 2026-10-20

### Added

- All twelve MCP tools now execute real work. `run_vad` uses FFmpeg speech
  detection; `transcribe` uses local whisper.cpp and stages an SRT;
  `get_transcript`, culling, zoom, J-cut, shorts, and export tools read and
  modify real project state.
- Staged MCP edits: retake culling, zoom configuration, and J-cuts update
  pending options that the next `videoflow_run_pipeline` applies unless the
  caller explicitly overrides them.
- `videoflow_generate_shorts` returns deterministic vertical clip proposals
  from the cached or project transcript, with retake cuts respected.
- `videoflow_export_fcpxml` exports the latest completed state for Resolve,
  Premiere, or Kdenlive, warns when staged edits are pending, and writes any
  requested output path inside the allowed roots.
- All four MCP resources are live: project state, transcript SRT, presets, and
  export paths. Missing data returns typed errors instead of stubs.
- `videoflow_transcribe` writes its SRT into the target project and stages it,
  so the pipeline uses the exact transcript the agent inspected.

### Changed

- `videoflow_run_vad` takes `noise_db`, `min_silence_ms`, and `min_speech_ms`,
  matching the FFmpeg backend.
- Loading a different source clears the previous MCP job, transcript, pending
  edits, and output context.
- Word-level retake culling returns `word_overrides_not_supported`; sentence
  ids remain the supported granularity.
- MCP documentation and the agent manual now describe the live contract.

### Verified

- Real MCP end-to-end on `jfk.mp4`: load, VAD, local transcription, transcript,
  culling, zoom, J-cut, shorts, pipeline success, all resources, and export.
- Linux 0.16.0 binary and AppImage: `version`, `doctor`, `demo`, and a frozen
  MCP workflow with local whisper.cpp.
- Windows PE 0.16.0 under Wine: `version`, `doctor`, `demo`, and a frozen MCP
  workflow with local `whisper-cli.exe`.
- Tests: 243 passed, 15 xfailed, 7 deselected; coverage 99.22%; ruff and mypy
  clean.

## [0.15.0] — 2026-10-20

### Added

- Offline transcription through the bundled whisper.cpp CLI and a tiny GGML
  model. `--transcribe` with no ASR URL extracts 16 kHz audio and runs locally.
- `whisper_model` in the job API, MCP overrides, and the Transcribe card; an
  empty value uses `ggml-tiny.bin`, a path selects a larger model.
- `scripts/fetch_whisper.py` builds Linux `whisper-cli` from pinned v1.7.6
  source and downloads the official Windows x64 build plus the tiny model.
- `scripts/build_portable.py --with-whisper` bundles the CLI and model.
- Runtime discovery through `VIDEOWFLOW_WHISPER_BIN` and
  `VIDEOWFLOW_WHISPER_MODEL`, with bundled `whisper/` paths as defaults.

### Changed

- ASR URL remains the opt-in remote path; an empty URL now means local
  whisper.cpp instead of a configuration error.
- Portable binaries grow by roughly 80 MB for the CLI and tiny model.

### Verified

- Real Linux `whisper-cli` and Windows `whisper-cli.exe` under Wine transcribe a
  16 kHz WAV to SRT; the adapter parses it into source-sample sentences.

## [0.14.1] — 2026-10-20

### Fixed

- Duration badges show milliseconds under one second instead of `0:00`.
- Header and footer no longer claim Shorts is CLI-only.
- Added a favicon, removing the `/favicon.ico` 404.

### Verified

- Real Chrome session: load, fill paths, enable culling, run, 7 per-block
  progress bars at 100%, global log with 53 lines, keep override, apply, second
  job succeeded. No console errors, request failures, or 4xx/5xx responses.

## [0.14.0] — 2026-10-20

### Added

- Speech-to-text through an OpenAI-compatible `/audio/transcriptions` endpoint,
  with `verbose_json` segments and optional word timings.
- `transcribe`, `asr_base_url`, `asr_model`, and `asr_language` on the job API,
  MCP overrides, and the Transcribe card.
- ASR key stays in `VIDEOWFLOW_ASR_API_KEY`; base URL falls back to
  `VIDEOWFLOW_ASR_BASE_URL`.
- SRT still wins when both a transcript and ASR are configured.
- `transcript_source` in the job report (`srt`, `asr`, or `none`).
- Unit tests for the HTTP client and an end-to-end ASR job.

### Changed

- Version is 0.14.0.
- The Transcribe card is enabled and configurable; local Faster-Whisper is still
  a future adapter.

### Verified

- Fake OpenAI-compatible ASR: 3 segments, `transcript_source=asr`, 3 timeline
  segments, stage `transcribe` succeeded.

## [0.13.0] — 2026-10-20

### Added

- Manual sentence overrides: `POST /api/v1/jobs` accepts `overrides` with
  `sentence_id` and `action` (`keep` or `discard`).
- Overrides are applied after the retake guard, so an editor can keep a culled
  take or discard a kept one. A manual decision wins.
- The inspector lists transcript sentences with Keep/Discard controls and an
  Apply overrides action that starts a new job with the same configuration.
- `manual_override_count` in the job report.
- MCP `overrides` support and unit/API tests.

### Changed

- Version is 0.13.0.

### Verified

- Base cull: 2 segments, 1 cull.
- Keep override: 3 segments, 0 culls, 1 override.
- Discard override: 2 segments, 1 cull, 1 override.

## [0.12.0] — 2026-10-20

### Added

- Shorts run as part of a job: selection, retake-aware conforming, ASS captions,
  1080x1920 MP4 render, a `shorts` stage with progress/logs, and `shorts.json`.
- `POST /api/v1/jobs` accepts `shorts`, `shorts_count`, `shorts_min_sec`,
  `shorts_max_sec`, and `shorts_subtitles`.
- `GET /api/v1/jobs/{id}/shorts/{index}` downloads a rendered vertical clip.
- The Shorts card is configurable and enabled when an SRT is present; the run
  summary lists shorts with download links.
- MCP overrides accept the shorts fields.
- API/journal tests and a real media job with two shorts.

### Changed

- Version is 0.12.0.

### Verified

- Live API job: 7 stages, export + shorts; two 1080x1920 MP4s; short download 200.
- AppImage/Windows PE rebuilt with the Shorts card and telemetry.

## [0.11.0] — 2026-10-20

### Added

- Per-stage telemetry: status, progress, start/finish timestamps, duration, and
  messages for ingest, VAD, SRT import, retakes, J/L cuts, zooms, and export.
- Bounded job logs with module/level filters and a download endpoint. FFmpeg
  commands and the last 50 stderr lines are captured; `job.log` is written to the
  output directory.
- API fields for VAD/pads, J/L offsets, zoom mode/scale/anchor/pan, retake
  strictness/strategy/window, LLM URL/model, and export targets.
- New rack UI: per-block progress, date/duration, status icons, global/per-block
  log drawer, configurable cards, recent jobs, and a run summary.
- Vitest coverage for date/duration/status formatting.
- `GET /api/v1/jobs/{id}/logs` and `?download=1`.

### Changed

- Version is 0.11.0.
- Job timestamps use millisecond precision, so short runs report real durations.

### Verified

- API job reports all stages with durations and logs.
- AppImage and Windows PE rebuilt with the new UI and telemetry.

## [0.10.0] — 2026-10-20

### Added

- Vertical shorts engine: deterministic or LLM sentence selection, retake-aware
  conforming, 1080x1920 H.264/AAC render, and ASS captions.
- `videoflow shorts INPUT --transcript subs.srt -o DIR` with count, duration
  bounds, subtitle toggle, culling, and optional OpenAI-compatible selection.
- `FFmpegAdapter.render_short` with concatenated pieces, center crop, and libass
  burn-in.
- ASS timing/text escaping and source-to-output subtitle mapping.
- Unit and real-media tests for selection, culls, LLM validation, ASS, CLI, and
  vertical output dimensions.

### Changed

- Version is 0.10.0.

### Verified

- Media test renders two 1080x1920 shorts with subtitles from a generated
  fixture.
- Frozen Linux binary and Windows PE (Wine) include the `shorts` command.

## [0.9.1] — 2026-10-20

### Fixed

- AppImage no longer exits immediately when opened without arguments. AppRun now
  starts `serve --open`, keeps the server running, and opens the rack UI.
- `videoflow serve --open` schedules the browser at the correct loopback URL,
  including when bound to `0.0.0.0` or `::`.
- AppImage builds can run `--appdir-only` for contract tests without
  appimagetool.

### Added

- AppDir contract tests for AppRun, desktop entry, icon, and executable bits.
- `scripts/smoke_appimage.py` and a `packaging` pytest marker for a real
  AppImage: version, doctor, demo, extract-and-run fallback, and serve health.

### Changed

- Version is 0.9.1.

## [0.9.0] — 2026-10-20

### Added

- `POST /api/v1/jobs` accepts `transcript` (SRT path) and `cull_retakes`.
  Transcript paths go through the same allowlist as media.
- `GET /api/v1/jobs/{id}/state` returns the project state for the UI inspector.
- The rack UI takes an optional SRT, enables retake culling, and shows culled
  sentences and guard restorations from the job state.
- MCP `videoflow_run_pipeline` overrides accept `transcript`, `cull_retakes`,
  `strictness`, `retake_strategy`, and `context_window`.
- Release artifact names include the version:
  `videoflow-0.9.0-linux-x86_64`, `VideoFlow-0.9.0-x86_64.AppImage`,
  `videoflow-0.9.0-windows-x86_64.exe`.

### Changed

- Version is 0.9.0.
- The job manager builds an LLM client from `VIDEOWFLOW_LLM_BASE_URL`,
  `VIDEOWFLOW_LLM_MODEL`, and `VIDEOWFLOW_LLM_API_KEY` when culling is enabled.

### Verified

- API test for transcript options, path jail, and state output.
- UI `npm run check` and `npm run build` are clean.

## [0.8.0] — 2026-10-20

### Added

- Linux AppImage builder (`scripts/build_appimage.py`) wrapping the onefile
  binary, with an icon, desktop entry, and AppRun.
- Portable Linux data directory next to the AppImage (`APPIMAGE` aware).
- Windows PE build path without GitHub Actions: Wine WoW64 + Windows embeddable
  Python + PyInstaller, with Windows FFmpeg binaries.
- `release.py` stages multiple artifacts, checksums, and a manifest.
- Releases now include Linux binary, AppImage, and Windows `.exe`.

### Changed

- Version is 0.8.0.
- GitHub Actions workflows removed. Builds and smoke tests are local.
- `packaging/videoflow.spec` accepts `VIDEOWFLOW_VENDOR_DIR` for cross-OS
  binaries.

### Verified

- AppImage: `doctor` and `demo`, three exports, bundled FFmpeg.
- Windows PE under Wine: `version`, `doctor`, `demo`, three exports, bundled
  FFmpeg.
- Both artifacts are staged in `releases/v0.8.0/`.

## [0.7.0] — 2026-10-19

### Added

- `GET /api/v1/jobs/{id}/artifacts/{target}` serves a generated timeline for
  download, confined to the job output directory.
- UI artifact cards are download links.
- Quick presets in the portable panel: YouTube, Lecture, Shorts.

### Changed

- Version is 0.7.0.

### Verified

- API contract test for in-output downloads and unknown artifacts.
- `npm run check` and `npm run build` are clean.

## [0.6.0] — 2026-10-19

### Added

- SRT transcript import with exact sample-time conversion.
- OpenAI-compatible JSON client: Ollama, LM Studio, Groq, and other
  `/chat/completions` endpoints; temperature 0; response-format fallback; no key
  in errors.
- Transcript-driven retake culling with overlapping context windows, strict id
  validation, exact-repeat fallback, and the `keep_last`/`keep_best` guard.
- `videoflow run --transcript subs.srt --cull-retakes`, optional LLM via
  `--llm-base-url`, and strictness/strategy/window flags.
- Transcript and retake decisions are persisted in `project_state.json` and
  reported in `run.json`.
- `--min-speech-ms` removes sub-100 ms blips left by codec edges.
- Tests for SRT parsing, LLM transport, chunking, guard restoration, interval
  subtraction, and the culling pipeline.

### Changed

- Version is 0.6.0.
- The LLM adapter is now a real implementation; its contract xfail is removed.

### Verified

- Frozen Linux binary: `--transcript` + `--cull-retakes` culls an exact repeat.
- Frozen Linux binary against a local OpenAI-compatible server: the model
  discards both attempts, the guard restores the last one, and the run reports
  one cull plus one restoration.

## [0.5.0] — 2026-10-19

### Added

- The SvelteKit rack starts real portable jobs: source/output fields, silence
  and zoom options, live progress, cancel, artifact paths, and typed errors.
- Module cards reflect live job stages. Neural modules are marked `later` and
  render as bypassed.
- Typed API client (`ui/src/lib/api.ts`) for system info and jobs.
- `releases/` policy, a `scripts/release.py` staging tool, checksums, manifests,
  and notes per version.
- Tag builds attach Linux and Windows binaries to the GitHub Release.

### Changed

- Version is 0.5.0.
- The served UI is no longer a static-only shell; it drives the portable API.

### Verified

- `npm run check` and `npm run build` are clean.
- The frozen binary serves the new UI, and the browser page is produced from the
  bundle.

## [0.4.0] — 2026-10-19

### Added

- `JobManager`: in-process jobs with queued/running/succeeded/failed/cancelled
  states, progress, cancellation between stages, bounded concurrency, and history
  pruning.
- REST routes: `POST /api/v1/jobs`, list, get, cancel, per-job SSE, and
  `/api/v1/system`.
- Path allowlist on HTTP and MCP inputs through `VIDEOWFLOW_ALLOWED_ROOTS`,
  defaulting to home, cwd, and the portable data directory.
- Live MCP tools: `videoflow_load_media`, `videoflow_run_pipeline`,
  `videoflow_get_job`, and `videoflow_cancel_job` now call the real pipeline.
  `run_pipeline` accepts optional `source` and `output`.
- Pipeline progress stages: probe, extract, VAD, timeline, export, state.
- Job and API contract tests, plus a real-media API job test.

### Changed

- Version is 0.4.0.
- `create_app` owns the API routes; `create_http_app` adds MCP and the static UI.
- `videoflow serve` now exposes a working job API, not only health.

### Verified

- Frozen Linux binary: POST job → poll → succeeded with three artifacts; SSE
  returns the terminal state; MCP stdio `load_media → run_pipeline → get_job`
  produces three artifacts.

## [0.3.0] — 2026-10-19

### Added

- Unified `videoflow` CLI: `run`, `serve`, `mcp`, `doctor`, `demo`, `version`.
- Model-free speech detection with FFmpeg `silencedetect`, including a parser and
  complement calculation.
- Portable pipeline service: probe, PCM, speech detection, timeline, three
  exports, `project_state.json`, and `run.json`.
- Portable runtime: data directory next to the executable, `VIDEOWFLOW_HOME`,
  binary discovery from the bundle, sibling files, then `PATH`.
- PyInstaller onefile spec, build script with FFmpeg bundling, and a Linux/Windows
  CI matrix with smoke tests.
- Static rack UI served by `videoflow serve` when the UI was built.
- MCP no-trailing-slash redirect (`/mcp` → `/mcp/`).

### Changed

- Version is 0.3.0.
- The API app can mount the built UI at `/`.
- Documentation adds a portable manual and ADR-0010.

### Verified

- Linux onefile (168 MB with static FFmpeg) runs with `PATH` empty: bundled
  FFmpeg and FFprobe are found, `doctor` passes, `demo` produces three artifacts,
  `serve` answers `/health`, `/`, and `/mcp/`, and MCP stdio lists twelve tools.
- Windows is built and smoke-tested in the CI matrix; no Windows binary was
  produced in this Linux workspace.

## [0.2.0] — 2026-10-19

### Added

- FFprobe ingest with rational frame rate, frame count, dimensions, and audio
  sample rate. Missing or unreadable sources fail with `ingest_failed`.
- PCM extraction to 16 kHz mono WAV with atomic replacement and SHA-256 digest.
- Deterministic timeline builder: span normalisation, frame coverage,
  sample-aligned audio, J/L-cut boundary shifts with handle checks, fade metadata,
  and alternating punch-in/pan transforms.
- FCPXML 1.9/1.10 writer with `audioStart`/`audioDuration` for J/L-cuts and
  `adjust-transform` for zoom.
- xmeml (FCP 7 XML) writer with separate video and audio tracks and a Basic
  Motion filter.
- OTIO writer with V1/A1 tracks for Kdenlive 25.04+.
- `export_timeline` service that writes all three artifacts from one validated
  timeline.
- Real-FFmpeg media tests for generated fixtures.
- Timeline builder and exporter contract tests.

### Changed

- Version is 0.2.0.
- Coverage gate now includes the deterministic timeline builder.
- Media, slow, and manual tests are excluded from the default pytest run. Run
  them with `-m media --no-cov`.

### Known gaps

- Audio transitions are not emitted in the NLE artifacts yet; the fade samples are
  recorded in state and the AC-01 contract remains xfail.
- Progressive zoom is stored as metadata but not emitted as keyframes.
- Neural engines, jobs, project routes, SSE, live MCP results, MP4 render, and the
  interactive rack are still stubs.

## [0.1.0] — 2026-10-19

### Added

- English normative product requirements, architecture, data model, timebase,
  pipeline, cache, security, and test plan.
- Specifications for all eight rack modules, the REST API, the MCP server, the
  rack UI, and the three NLE exporters.
- Nine ADRs covering rational time, hexagonal boundaries, secrets, NLE dialects,
  MCP transports, XML building, the retake guard, CPU-first defaults, and the
  single-user runtime.
- User, operator, developer, MCP agent, NLE import, and testing manuals.
- Pydantic project state, module configs, presets, job and error models.
- Committed JSON Schemas generated from the models.
- Rational `Timebase` with frame coverage, pads, and exact round-trips.
- Cache canonicalization and module hashing without mtime.
- Run planning with upstream-dirty rules and bypass handling.
- Retake keeper guard, exact repetition clustering, and restoration records.
- Path allowlist jail, secret redaction, and timeline overlap checks.
- FastAPI health endpoint and MCP Streamable HTTP mount.
- MCP SDK server with twelve tools and four resources, returning structured
  `not_implemented` results.
- Three shipped presets: `youtube-talking-head`, `shorts-aggressive`,
  `lecture-clean`.
- 107 passing unit/contract tests, 21 strict xfails for unbuilt engines, and
  99% coverage on the pure core.
- SvelteKit and Tailwind rack scaffold with the eight module cards.
- CI workflow for tests, coverage, lint, and types.

### Changed

- The Portuguese brief moved to `docs/origin/prd-pt.md` and is non-normative. The
  old `requirements.txt` name was removed because Python treats it as a
  dependency list.
- FCPXML is no longer claimed as a Premiere import format. Premiere receives
  xmeml; Kdenlive receives OTIO.
- Neural defaults are CPU/int8/small, not CUDA/float16/large-v3.
- Authoritative time is rational frames and samples, not float seconds.

### Known gaps

- Media engines, exporters, job execution, project routes, SSE, and the live rack
  are specified and stubbed.
- No license has been chosen.
- No face tracking in v1.
- The NLE compatibility spike and long-file manual QA are not yet executed.

### Security

- Secrets are names in state and values only in the environment or a mode-0600
  file.
- The API binds to loopback and CORS is limited to the local UI.
