# VideoFlow 0.47.0

This release finishes the recipe-editor experience.

## Canvas

- Saved viewport pan/zoom.
- Node width cycling between compact, medium, and wide.
- Layout and viewport continue to autosave in the recipe `ui` block.

## Preview proxy

- Successful jobs can generate a 540p H.264/AAC proxy.
- The proxy plays inline without touching the original render.

## Batch history

- The batch modal lists persisted batches.
- Selecting one loads its status and item state.

## Validation

- URL and schema-pattern checks were added to inline fields.
- 449 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 10 Playwright tests passed.

## Notes

- Arrays and deeply nested objects still use the advanced JSON editor.
- Kdenlive parity and manual NLE QA remain pending.
- Distribution remains out of scope.
