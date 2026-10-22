# VideoFlow 0.33.0

This release improves the content layer with optional model diarization, stock
B-roll, and dialogue-aware split-screen.

## Diarization

- `audio.diarize` now supports `method: "pyannote"`.
- Parameters: `model_path`, `device`, `hf_token_env`, and
  `fallback_to_heuristic`.
- Sentence labels come from the model turn with the largest overlap.
- The `diarization` extra installs `pyannote.audio`; the default remains the
  offline pause heuristic.
- Pyannote is not installed on this host; the adapter is lazy and tested with a
  fake pipeline plus fallback behavior.

## B-roll

- `broll.plan` supports `provider: "pexels"` with `PEXELS_API_KEY`.
- Local assets remain the default and work fully offline.
- Stock results are downloaded into the output and the plan records provider,
  license, attribution, and source URL.
- The provider layer is tested with an HTTP mock.

## Split-screen

- `shorts.reframe` can set `split_screen_on_dialogue`; a clip with more than one
  speaker is marked for the two-panel layout.
- The renderer supports `split_screen_zoom`, `split_screen_focus_left`, and
  `split_screen_focus_right` for per-panel framing.
- Fixed a render-loop variable shadowing bug where a B-roll plan could overwrite
  the Short metadata on the next iteration.

## UI

- Diarization method/model/fallback controls.
- B-roll provider, query, and API-key environment controls.
- Dialogue split toggle and panel focus/zoom controls.

## Validation

- 423 Python tests passed; 14 UI tests passed.
- The 0.33.0 AppImage rendered a Short with dialogue split-screen and a local
  B-roll cutaway at 1080x1920.
- `broll.json` recorded provider `local`, license `operator`, and the asset path.

## Artifacts

- `videoflow-0.33.0-linux-x86_64` — SHA-256 `24e5be99e62be8d45d5730ad066c56269bb4dcadb3fc14ad1ae386a7403de59d`
- `VideoFlow-0.33.0-x86_64.AppImage` — SHA-256 `1a28bdcdc4e8bb96a617555468fa0471ac8faee9bfd2afd98cd339bd5135c68b`
