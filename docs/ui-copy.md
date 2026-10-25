# UI copy and naming

## Areas

| Area | Purpose | Tabs |
| --- | --- | --- |
| Produce | Create and run recipes | Recipes, Assistant |
| Edit | Edit and finish the cut | Timeline |
| Runs | Track and schedule runs | Jobs, Schedules |
| Library | Source and reusable assets | Media, Brand library |
| Setup | Configure the local product | AI models, AI providers, Local services, Extensions, Connect, Settings |

The order is the workflow order. Routes keep flat hashes (`#recipes`,
`#timeline`, …) and legacy hashes redirect: `#assets` → Media, `#automation` →
Schedules, `#copilot` → Assistant, `#library` → Brand, `#plugins` → Extensions,
`#integrations` → Connect.

## Vocabulary

| Concept | Use | Do not use |
| --- | --- | --- |
| One execution | run | job (in UI) |
| Workflow document | recipe | workflow |
| Source file | media | asset |
| Reusable brand content | brand library | library (alone) |
| LLM helper | assistant | copilot |
| Add-on code | extension | plugin (in UI) |
| External connection | connect | integration (in UI) |

Keep API/MCP names stable (`jobs`, `plugins`, `integrations`); only the UI uses
the friendlier terms.

## Buttons

- Imperative verb + object: `Run recipe`, `Save changes`, `Cancel run`.
- Destructive actions name the object: `Delete media "clip.mp4"`.
- Never use `OK`, `Submit`, `Yes` alone.
- Disabled controls explain why through a tooltip or hint.

## Status

Dispatch, paused, queued, waiting approval, running, succeeded, failed,
cancelled. Show the label in sentence case; keep the API code unchanged.

## Tooltips

Every non-obvious option uses `HelpTip` with:

1. what it does;
2. default;
3. unit/range;
4. practical effect.

Hints are one or two lines and stay visible for fields that need constant
context (use `FieldHint`). Never put critical information only in a tooltip.

## Errors

Format: **what happened** + **next action** + code + link.

Example: `The provider did not respond (LLM_TIMEOUT). Check the URL and run Test connection.`

## Empty states

Title, one-line description, primary action, optional shortcut. Example:
“No runs yet. Run a recipe from Produce.” with `Open Produce`.

## Units and defaults

Put units in labels (`Timeout (s)`, `True peak (dBTP)`, `Proxy height (px)`,
`Priority (-100…100)`). Show the default in the hint, not in the label.
