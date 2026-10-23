# VideoFlow 0.56.0

This release connects the timeline and content nodes.

## Timeline editing

- Captions are selectable and editable.
- Saving writes into `project_state.json`.
- API: `PATCH /api/v1/jobs/{id}/captions/{sentence_id}`.
- Caption blocks highlight the selected item.

## Content nodes

- `storyboard.plan` is now implemented:
  - writes `storyboard.json`;
  - includes scenes, captions, Shorts, and B-roll.
- `thumbnail.generate` is now implemented:
  - renders a thumbnail frame from the source;
  - stores it as an artifact.

## Validation

- 459 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 14 Playwright tests passed.

## Notes

- Timeline drag/trim and B-roll approval remain pending.
- Distribution remains out of scope.
