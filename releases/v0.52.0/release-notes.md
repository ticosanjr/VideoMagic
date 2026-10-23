# VideoFlow 0.52.0

This release makes recipes the only visible execution surface and adds the
content-cycle foundation.

## Recipes-first UI

- Speech, Edit, Shorts, Studio, and Export tabs are no longer in navigation.
- Top-level tabs: Recipes, Assets, Timeline, Models, Services, Providers.

## Content cycle

New step types:

- `content.idea`
- `content.research`
- `content.script`
- `storyboard.plan`
- `assets.index`
- `audio.master`
- `titles.plan`
- `thumbnail.generate`
- `publish.webhook`
- `analytics.import`
- `review.queue`

Every manifest now carries:

- `status`: available, partial, or planned;
- `icon`;
- `color`;
- `bypass`.

Planned nodes are rendered dashed and skipped by the runner. The `content_cycle`
built-in recipe includes the whole cycle.

## Asset library

- Scan a local folder into the library.
- Search by name, path, tag, or kind.
- Edit tags and see license/source metadata.
- Download or remove assets.
- File serving is path-allowlisted.

## Timeline

- Read-only video/audio/caption/B-roll tracks from a successful job.
- Time ruler, playhead, clip metadata, and MP4 preview.
- API: `GET /api/v1/jobs/{id}/timeline`.

## Validation

- 455 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 14 Playwright tests passed.

## Notes

- Legacy rack backend routes remain for compatibility, but are no longer
  reachable from the UI.
- Kdenlive exact cross-dissolve and manual NLE QA remain pending.
- Distribution remains out of scope.
