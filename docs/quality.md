# Content quality

This page covers the 2.3.0 quality work: Short selection calibration, B-roll
matching by shot, the SFX library, dubbing inside a recipe, and the delivery
package.

## Golden set and channel profiles

`tests/golden/shorts.json` holds transcript cases with the ideal sentence
groups and the profile that should win for that channel. Each case is scored by
the same heuristic used in production, so the golden set measures the product
and not a parallel implementation.

`src/videoflow/application/scoring.py` owns:

- `PROFILES` — multipliers for the score components (`markers`, `question`,
  `exclamation`, `numbers`, `prompt`, `duration`, and the quality bonuses such
  as `payoff`, `completeness`, and `hook_strength`).
- `profile_weights(profile, analytics)` — merges a profile with analytics
  weights.
- `rerank(clips, weights, diversity_threshold, top_k)` — applies weights, sorts,
  and drops near-duplicate titles.
- `evaluate_cases(cases, top_k)` — precision@k, recall, duplicates, coverage,
  latency, and cost.

Run the report:

```bash
uv run pytest tests/unit/test_shorts_score_dedup.py tests/unit/test_shorts_score_llm.py -q
```

Current result: baseline precision@1 **0.75**, calibrated **1.00**, zero
duplicates, 100% coverage, zero LLM cost (heuristic path).

Profiles can be chosen before selection through `shorts.select.profile` or with
the `shorts_profile` job option, so the weights change which windows are
selected rather than only re-ordering the survivors.

## Semantic option

`application/embeddings.py` uses a local sentence-transformers directory when
`VIDEOWFLOW_EMBEDDING_MODEL` points at one and the extra is installed. TF-IDF is
used otherwise; the match entry records `match: "embeddings"` or `"tfidf"`.

## B-roll by shot and licences

`assets.match` reads the shots produced by `assets.shots` and, for each Short,
scores local assets against the transcript text that overlaps each shot:

- the entry records `shot_id`, the relative `start_sec` inside the Short, a
  cutaway duration capped at five seconds, and the TF-IDF `score`;
- an asset is used at most once across the plan;
- `broll-licenses.json` lists every used asset with name, path, license, and
  attribution;
- when no shots exist, the step falls back to one window for the whole Short.

The renderer still honours `broll_approval.json`, so approval order wins over
the automatic order.

## SFX library

`GET /api/v1/assets/sfx`, `POST /api/v1/assets/sfx?name=`, and
`DELETE /api/v1/assets/sfx/{name}` manage `<home>/assets/sfx`. Uploads accept
MP3, WAV, M4A, AAC, OGG, and FLAC up to 50 MB. The Library tab lists, uploads,
and deletes SFX next to music, images, and fonts. `sfx.plan` places cues and
`shorts.render` mixes them with the voice track.

## Dubbing alignment and review

After synthesis, the dub probes the audio duration. A drift beyond ±15% triggers
one retry with a corrected speed (clamped to 0.75–1.3). Every dub writes a
`translation.json` review file next to the audio with source, translated text,
language, and `approved: false`. The recipe step tries every configured TTS
provider in order and only warns when all of them fail. Voice cloning remains a
provider capability; the OpenAI-compatible adapter has no clone endpoint.

## Hook and duration A/B

`shorts.ab` turns each selected Short into hook (`original`/`repeat`) and
duration (100%/80%) variants, capped by `max_variants`. The
`hook_duration_ab` recipe inserts it between scoring and reframe, so the normal
renderer produces real candidates.

## Dubbing in a recipe

`localized_shorts` is a built-in recipe: the viral Shorts DAG followed by
`localization.dub` before the NLE export. It targets English, keeps 15% of the
original volume, and skips with a warning when no TTS provider is configured.
The mirror is `recipes/localized_shorts.json`.

## Delivery package

`delivery.package` runs after the Shorts render. It reads
`thumbnail_choice.json`, copies the winning variant to
`delivery/thumbnail.png`, and writes `delivery/package.json` with:

- the thumbnail winner and every variant;
- each Short title and path;
- the metadata pack path;
- music and SFX files referenced by the run;
- the B-roll match and licence report paths.

The manifest is the hand-off artifact: one file that names everything a
publisher needs.

## Tests

- `tests/unit/test_golden_shorts.py` — calibrated beats baseline, top-k,
  coverage, duplicates.
- `tests/unit/test_scoring.py` — profiles, analytics overrides, re-ranking,
  duplicate removal.
- `tests/unit/test_broll_match.py` — shot windows, licence report, fallback.
- `tests/unit/test_delivery_package.py` — winner copy and manifest contents.
- `tests/contract/test_api_sfx.py` — upload, list, delete, validation.
- `tests/contract/test_shorts_media.py` — music and SFX mixed into a real Short.
- `tests/unit/test_advanced_recipe.py` — `localized_shorts` has dubbing after
  the render.
