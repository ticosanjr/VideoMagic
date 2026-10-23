# VideoFlow 0.54.0

This release removes the remaining legacy project UI and hardens settings.

## Removed

- Legacy “New project” card from Models, Services, and Providers.
- ProjectTemplateManager from Providers.
- The old rack project form is no longer part of the settings pages.

## Providers

- Connection test form:
  - base URL;
  - secret environment variable;
  - path;
  - HTTP status;
  - secret presence.
- API: `POST /api/v1/providers/test`.
- Capability catalog is collapsed, searchable, and filterable.
- API/MCP details stay behind a disclosure.

## Models

- Grouped by capability.
- Downloads are explicit and independent from the provider policy.
- Shows used-by steps, license, source, size, and path.

## Services

- Doctor diagnostics.
- Confirmation for destructive actions.
- Server log remains available.

## Validation

- 457 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 14 Playwright tests passed.

## Notes

- Provider forms for persistence, fallback, and per-provider defaults remain
  pending.
- Distribution remains out of scope.
