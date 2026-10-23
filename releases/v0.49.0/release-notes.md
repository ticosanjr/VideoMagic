# VideoFlow 0.49.0

This release hardens the recipe editor and fixes the UI version mismatch.

## Canvas reliability

- New edges that would create a cycle are rejected immediately.
- Undo/redo covers structural edits and node drags.
- Arrays render as JSON textareas with inline validation.
- Node width still cycles between compact, medium, and wide.

## Build correctness

- `build_portable.py` now rebuilds the Svelte UI before packaging.
- It refuses to package when `ui/build/index.html` does not contain the version
  from `ui/src/lib/version.ts`.
- This fixes the 0.48 local artifact where the server was 0.48.0 and the UI was
  0.34.0.

## Validation

- 452 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 12 Playwright tests passed.

## Notes

- Kdenlive parity and manual NLE QA remain pending.
- Distribution work remains out of scope.
