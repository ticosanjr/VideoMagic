# VideoFlow 0.50.0

This release hardens real-provider behavior.

## pyannote

- The Models catalog can install `pyannote/speaker-diarization-3.1`.
- `audio.diarize` now auto-detects the installed local model when the configured
  `model_path` is the default Hugging Face id.
- Real inference still requires the `diarization` extra and model access.

## Pexels

- Stock downloads stream to a `.part` file instead of loading the full clip in
  memory.
- The URL-keyed cache remains in place.

## Melt diagnostics

- `melt_check.py` now reports `plugin_warnings` for failed filter/transition
  plugin loads separately from the render verdict.

## Validation

- 452 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 12 Playwright tests passed.

## Notes

- Kdenlive exact cross-dissolve and manual NLE QA remain pending.
- Distribution remains out of scope.
