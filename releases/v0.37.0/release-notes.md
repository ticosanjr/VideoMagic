# VideoFlow 0.37.0

This release improves the recipe UI and persistence.

## Recipe inspector

- Primitive parameters now render from each step's JSON `params_schema`:
  boolean, number/integer, enum, and text.
- The hand-written quick controls remain for transitions, speaker turns,
  B-roll, split-screen, captions, and TTS.
- Schema fields are covered by Playwright.

## NLE validation in the UI

- A Validate action calls `POST /api/v1/exports/validate`.
- The modal shows per-format status, clips, transitions, keyframes, effects,
  affine filters, errors, and warnings.

## B-roll plan

- Job results include `broll_plan`.
- The recipe result panel shows provider, license, and path for each planned
  clip.

## Batch persistence

- Batch JSON is written to the VideoFlow home and reloaded on restart.
- Interrupted queued/running batches are marked failed with a restart message.
- Batch records include the recipe JSON so history can be audited.
- New tests cover restart recovery and interrupted batches.

## Configuration

Project data, schemas, fixtures, batch records, history, checkpoints, and test
data are JSON. The only YAML files are the GitHub Actions workflows, which
GitHub requires.

## Validation

- 437 Python tests passed.
- 14 Vitest tests passed.
- 5 Playwright tests passed.
- AppImage 0.37.0 built.

## Artifacts

- `videoflow-0.37.0-linux-x86_64` — SHA-256 `5f20576c4794bf523234420da9d129ecee828b6bc5c09c5a04badcb9c38e0137`
- `VideoFlow-0.37.0-x86_64.AppImage` — SHA-256 `b31b5504f89afcfa2a21443e4cd224a55d9438ffd2489b9d92c092a3a0eef1e7`
