# VideoFlow 0.62.0

This release consolidates the 0.58–0.62 scope into the current recipes-first
application.

## Timeline editing foundation

- Select a video clip.
- Trim by start/end seconds.
- Move by a delta.
- Delete the clip.
- API: `PATCH /api/v1/jobs/{id}/timeline`.
- State revision increments and the API warns that artifacts must be re-rendered.
- Caption editing remains available.

## Recipes and content

- Recipe history, restore, save-as, template gallery.
- Conditional/loop/subflow nodes are planned bypasses.
- Storyboard and thumbnail nodes are implemented.
- Content-cycle status/icons/colors/bypass.

## Settings

- Models grouped by capability.
- Provider connection test with secret presence.
- Services doctor and destructive confirmations.
- Legacy New project/ProjectTemplateManager removed.

## Validation

- 459 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 15 Playwright tests passed.

## Notes

- Full drag handles, B-roll approval, provider persistence/fallback, scheduler,
  analytics, audio master, and NLE parity remain future work.
- Distribution remains out of scope.
