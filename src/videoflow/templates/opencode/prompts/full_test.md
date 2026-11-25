Execute o **Teste Completo e Rápido do VideoFlow** usando exclusivamente as tools do MCP.

## Dados
- RAW: `{{RAW_VIDEO}}`
- Projeto: `{{PROJECT_ID}}`
- Recorte: `{{DURATION_SEC}}` segundos
- Saída: `./PREVIEW_TEST/`
- Perfil MCP: `full` (22 tools)
- Preview: 540p / 30 fps / `qa_mode="skip"`

## Regras
1. Leia `AGENTS.md` e o workflow escolhido.
2. Use `mode="preview"` e `qa_mode="skip"` em todos os renders de teste.
3. O único comando fora do MCP é o recorte inicial com
   `ffmpeg -y -ss 00:00:00 -t {{DURATION_SEC}} -i "<RAW>" -c copy`.
4. Registre o payload exato de qualquer falha e continue para a próxima etapa.

## Fase 0 — Fixture e diagnóstico
1. Chame `vf_capabilities`; registre CUDA/NVENC, `ffmpeg_filter_flag`, modelos e actions.
2. Recorte o RAW para `{{DURATION_SEC}}s` em
   `./projects/{{PROJECT_ID}}/raw_test.mp4`.
3. Crie `./PREVIEW_TEST/`.

## Fase 1 — Decupagem assistida
1. `vf_project(action="init", project_id="{{PROJECT_ID}}")`.
2. `vf_ingest` no recorte.
3. `vf_style(action="apply", style_id="canal-paula-long")`.
4. `vf_decupage(action="review_packet", wait=True)`.
5. Leia **100%** das sentenças; identifique retakes/frases repetidas e mantenha
   a última tentativa completa.
6. `vf_decupage(action="discard_sentences", sentence_ids=[...])`.
7. `vf_decupage(action="run_full", pacing_profile="tight", wait=True)`.
8. Confirme `keep_ranges` preenchido, nenhuma palavra real cortada,
   `punch_in_scale <= 1.07` e `vf_transcript` devolvendo 100% das sentenças.

## Fase 2 — Cena, fala, B-roll e curadoria
1. `vf_scenes`.
2. `vf_transcript(action="editorial_map")`; valide `edited_start_sec`,
   `edited_end_sec`, `layout_type`, `protected_from_broll` e `keyframe_path`.
3. Escolha 2 momentos em `TALKING_HEAD` e prepare:
   - 1 imagem com `image_to_broll_motion` (`zoom_in`, `1.00 → 1.06`, `4s`);
   - 1 vídeo stock filtrado ou captura web de 5s;
   - 2 SFX procedurais nas entradas;
   - trilha musical.
4. `vf_media(action="search")` deve rejeitar clipes com mais de 120s, mais de
   80MB ou relevância abaixo de 0.35.
5. Aprove licenças com `vf_media(action="approve_license")`.
6. Publique 1 board com `start_sec`, `end_sec`, `spoken_context` e
   `local_path`; valide `media_url`/`poster_url` e finalize com
   `auto_select` + `read`, preservando `scene_id` e `local_path`.

## Fase 3 — Montagem, áudio 2x, preview, Short e NLEs
1. `vf_timeline(action="apply_beatmap")` com os 2 B-rolls, 2 SFX e punch-in
   `<= 1.06`.
2. `vf_audio(action="master")` duas vezes seguidas; confirme idempotência,
   loop de música, SFX no mix e ausência de `same as Input #0`.
3. Gere legendas (`captions.plan`).
4. `vf_export(action="render", mode="preview", burn_subtitles=True,
   qa_mode="skip", wait=True)` → `./PREVIEW_TEST/01_longform_preview_540p.mp4`.
5. `vf_export(action="bundle", targets=["resolve", "premiere", "kdenlive"],
   wait=True)` + `vf_export(action="validate")` → `./PREVIEW_TEST/nle/`.
6. Escolha 1 gancho de 25–35s em `TALKING_HEAD` via `editorial_map` e rode
   `vf_shorts(action="batch", time_basis="edited", burn_subtitles=True,
   wait=True)` → `./PREVIEW_TEST/02_short_9x16.mp4`.

## Relatório final
Mostre:
1. tempo total e por etapa (`execution_node`, NVENC/x264);
2. frases repetidas removidas e duração `{{DURATION_SEC}}s → Xs`;
3. timestamps `MM:SS` dos 2 B-rolls, do efeito `0–2.5s` e dos 2 SFX;
4. qualquer erro remanescente com payload exato.
