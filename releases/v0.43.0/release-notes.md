# VideoFlow 0.43.0

This release turns each recipe node into an editable configuration card.

## Inline node fields

- Primitive fields render inside the node: text, number, integer, boolean,
  enum select, color, and path with picker.
- Nested objects render as grouped field sections.
- Complex structures remain available through the advanced JSON editor.
- Field labels, descriptions, required markers, and inline errors are visible in
  the node.

## Saved canvas

- Recipe JSON now has an optional `ui` block with node positions, expanded/pinned
  state, width, and viewport.
- Layout is autosaved after drag/toggle with a short debounce.
- `Auto layout` restores a deterministic graph layout.
- `ui` changes are excluded from the checkpoint fingerprint path.

## Validation

- Drafts can be saved with incomplete fields.
- Run is blocked while a field is invalid; the count is shown in the error bar.
- The backend recipe validation remains authoritative.

## Per-step progress

- `StepIO` emits local progress as well as overall job progress.
- Jobs expose `step_progress`.
- Each node shows idle/queued/running/cached/executed/failed and a percentage bar.

## Validation

- 445 Python tests passed.
- 14 Vitest tests passed.
- 8 Playwright tests passed.

## Notes

- NLE parity and content-provider work continue in 0.44.
- Distribution work remains intentionally out of scope.
