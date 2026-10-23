# VideoFlow 0.46.0

This release adds real model provisioning for optional diarization.

## pyannote model downloader

- Models catalog now includes `pyannote/speaker-diarization-3.1`.
- Install uses `huggingface_hub.snapshot_download`.
- `HF_TOKEN` is used when the repository is gated.
- Installed detection checks for `config.yaml`.
- The download path is covered by a mocked test.

## Validation

- 449 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 8 Playwright tests passed.

## Notes

- Real pyannote inference still needs the `diarization` extra and model access.
- Kdenlive cross-dissolve and manual NLE import QA remain pending.
- Distribution work remains out of scope.
