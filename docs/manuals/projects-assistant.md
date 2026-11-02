# Assistant and review

This is the operator guide for the assistant workspace. Everything runs on the local
machine and stays inside the allowed roots.

## Assistant with tools

The assistant is not a free-form writer. It can only call these tools:

| Tool | Writes | Approval |
| --- | --- | --- |
| `list_recipes`, `get_job`, `get_timeline`, `validate_exports` | no | not needed |
| `apply_timeline_edits` | yes | required |
| `render_preview` | yes | required |
| `run_recipe` | yes | required |

1. Open **Produce → Assistant → Agent tools**.
2. Pick a finished run and describe the outcome.
3. Read the answer, tool calls, and the clip-level diff.
4. Select **Approve and apply**. The write only happens on this second call.
5. If the result is wrong, use **Undo** in the timeline.

Each turn records the token count, estimated cost, and the budget left. A pending
approval can be applied once; replaying it returns `409`.

Set a budget with `VIDEOWFLOW_COST_BUDGET_USD`. Calls stop with an actionable
`llm_failed` error when the budget is exhausted.

## Run graph and logs

**Runs** shows every queued, running, paused, waiting, and finished job.

- Select **Run graph** to see step order, edges (`needs`), status, per-step
  duration, p50/p95 for the same recipe, and the retry policy.
- The log viewer filters by step and level, and can download the filtered text.
- Failed attempts can be retried; retry uses the configured attempts/backoff.

## Variant comparison

Inside **Edit → Timeline → Deliverables**, select **Compare variants**.

- Recipe variants show best Short score, Short count, and artifact count.
- Shorts show hook title, score, and duration.
- Thumbnail A/B cards keep impressions, clicks, and CTR.
- **Winner** marks the chosen item in `review/variant_winner.json` so the final
  package and the operator agree.

## Delivery checklist

1. Review checks pass and the run is approved.
2. Compare variants and mark the winner.
3. Validate FCPXML/XMEML/Kdenlive.
4. Confirm the manifest, cover, metadata, NLE files, and checksums.
5. Open the output folder or copy the manifest for hand-off.

## Troubleshooting

| Symptom | Next action |
| --- | --- |
| Assistant says no provider | Add an OpenAI-compatible provider in **Setup → AI providers** |
| Approval returns 409 | The plan was already applied or expired; ask again |
| Stale timeline error (412) | Reload the timeline; the ETag changed |
| Variants list is empty | The recipe has no `variants` and produced no Shorts |
| Run graph has no nodes | The job was not started from a recipe |
