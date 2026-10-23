# VideoFlow 0.44.0

This release polishes the content path.

## Second-source audio

- `shorts.render.mix_second_audio` mixes the second split-screen source with the
  primary audio.
- The Recipes inspector exposes the checkbox next to the second-source field.
- Verified with two generated clips: the split-screen MP4 contains both panels
  and mixed audio.

## Stock B-roll cache

- Pexels downloads are cached by a SHA-1 of the source URL, not by clip index.
- Replanning the same Short reuses the already downloaded asset.
- The plan still records provider, license, attribution, and source URL.

## Validation

- 445 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 8 Playwright tests passed.

## Notes

- Manual NLE import QA remains pending.
- pyannote/Pexels still need real model/API credentials for final validation.
- Distribution work remains out of scope.
