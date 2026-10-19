# ADR-0007 — A guard enforces keep-last

Status: accepted. Date: 2026-10-19.

## Context

The brief requires that retake culling "never cut the final version" and that the
kept sentence is "categorically the last iteration". The same brief relies on a
prompt and a JSON schema. A language model can still discard the last take, and a
schema cannot express "this id must survive".

## Decision

- The model returns only `{discard_sentence_ids, reasoning}`.
- Every id must exist in the prompt window.
- The domain detects repetition clusters.
- `keep_last` removes the keeper from the discard set and records a restoration.
  This is the default and the AC-03 guarantee.
- `keep_best` is opt-in. It keeps the highest-scored take in a cluster and still
  leaves exactly one keeper. The guard does not judge semantic completeness; that
  is the model's job, and the inspector exposes the decision.
- Manual overrides run after the guard.
- Restoration ids are persisted and shown in the inspector.

## Consequences

- The acceptance criterion is deterministic and testable with a fake LLM.
- With `keep_last`, a model cannot silently delete the final take.
- Some legitimate aggressive cuts are refused. The editor can discard manually.
- Cluster detection for non-exact retakes is best-effort; the guard is exact only
  for clusters the system knows about. The prompt asks the model to reason about
  the rest, and the inspector exposes the result.
- An operator who selects `keep_best` accepts that an earlier scored take may win.
  That is a style choice, not the default safety rule.

## Alternatives rejected

- Prompt-only: unenforceable.
- Ask the model twice: still probabilistic.
- Always keep the last sentence of the entire transcript: too blunt.
