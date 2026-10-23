# VideoFlow 0.55.0

This release improves recipe creation and management.

## Recipe history

- Each save snapshots the previous recipe under the VideoFlow home.
- History API:
  - `GET /api/v1/recipes/{id}/history`
  - `POST /api/v1/recipes/{id}/history/{version}/restore`
- History modal lists versions and restores one.

## Save as

- Fork a recipe with a new id and name.
- The new recipe is saved immediately.

## Flow nodes

Planned bypass nodes:

- `flow.conditional`
- `flow.loop`
- `flow.subflow`

They give the DAG a vocabulary for branching, iteration, and reusable groups
without pretending execution exists.

## Validation

- 458 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 14 Playwright tests passed.

## Notes

- Conditional/loop/subflow execution remains planned.
- Distribution remains out of scope.
