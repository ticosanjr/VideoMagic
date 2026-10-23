# VideoFlow 0.57.0

This release closes the 0.54–0.57 sequence.

## Recipe management

- Template gallery with search.
- Save as/fork.
- Version history with restore.
- Planned flow nodes: conditional, loop, subflow.
- History and templates modals.

## Timeline

- Caption editor writes back to `project_state.json`.
- Caption blocks are selectable.
- Preview and playhead remain available.

## Content nodes

- `storyboard.plan` writes `storyboard.json`.
- `thumbnail.generate` renders a real thumbnail.
- Planned content-cycle/flow nodes bypass safely.

## Settings

- Legacy New project/ProjectTemplateManager removed.
- Models grouped by capability, with used-by/license/source.
- Services Doctor and destructive confirmations.
- Providers connection test and collapsed capability catalog.
- API: `POST /api/v1/providers/test`, `GET /api/v1/system/doctor`.

## Validation

- 459 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 15 Playwright tests passed.

## Notes

- Timeline drag/trim, B-roll approval, provider persistence/fallback, and
  distribution remain pending.
