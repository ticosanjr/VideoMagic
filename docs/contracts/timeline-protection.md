# Timeline protection

Manual timeline edits are authoritative.

## Revision guard

Every write to the timeline passes `expected_revision` (or `expected_sample`).
If the project revision changed:

- without `reset`, raise `TimelineConflict`;
- with `reset=True`, create a snapshot of the current state, then rebuild.

## Read-only steps

`vf_qa_final`, `vf_export`, `vf_job`, and any `qa.*` step never write the
timeline.

## Revisions and checkpoints

- Every destructive write creates a snapshot in `history/`.
- Named checkpoints live in `history/checkpoints.json` and are created with
  `vf_project(action="checkpoint", label="pos_broll")`.
- `restore_checkpoint` snapshots the current state before restoring, so the
  restore itself is reversible.
