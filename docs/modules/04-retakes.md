# Module 04 — Retake culling

## Implementation status

Implemented: SRT import, exact-repeat fallback, OpenAI-compatible JSON client,
overlapping context windows, strict id validation, the keeper guard, interval
subtraction, CLI/API/UI execution, and manual sentence overrides. Not
implemented: built-in transcription and word-level overrides.

## Purpose

Remove aborted sentences, stumbles, and repeated attempts while never deleting
the final valid take.

## Inputs

- `state.transcript`.
- `RetakesConfig`.
- Manual overrides.

## Outputs

- `state.retake_culls`: sentence ids to drop.
- `state.retake_guard_restores`: ids the guard saved.
- Estimated duration after culling.

## Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `provider` | `ollama` | ollama or openai_compatible |
| `base_url` | `http://localhost:11434/v1` | Endpoint |
| `secret_name` | `VIDEOWFLOW_LLM_API_KEY` | Environment or secrets file key |
| `model_name` | `qwen2.5:7b-instruct` | Model |
| `strictness` | `balanced` | conservative/balanced/aggressive |
| `context_window_sentences` | 15 | Window size |
| `retake_strategy` | `keep_last` | keep_last/keep_best |
| `temperature` | `0.0` | Determinism |

No `api_key` field exists. A request that supplies one is rejected.

## Protocol

Prompt (structure):

```
SYSTEM: You remove failed takes. Return only JSON matching the schema.
DATA: [ {id, text}, ... ]  <-- untrusted transcript data
RULES: never discard the last complete take of a repetition group.
SCHEMA: {"discard_sentence_ids": [int], "reasoning": string}
```

Response:

```json
{ "discard_sentence_ids": [3, 4, 12], "reasoning": "Attempts before the final take." }
```

Validation, in order:

1. JSON parse.
2. Schema.
3. Every id exists in the sent window.
4. Repetition clusters.
5. Keeper guard.
6. Merge window decisions.
7. Manual overrides.

## Keeper guard

`keep_last`:

- The last sentence of each cluster is the keeper.
- If the model discards it, remove it from the discard set and record a
  restoration.

`keep_best`:

- The highest score wins; ties go to the later sentence.
- With no scores, fall back to the last.
- Exactly one keeper survives. The guard does not judge semantic completeness;
  preferring an earlier take is the explicit point of this opt-in strategy.

Unknown ids raise `InvalidRetakeIdsError`. No partial application.

## Deterministic fallback

Exact repeats are clustered by normalised text (case, whitespace, terminal
punctuation). This gives a working cull with no model for repeated identical
takes. Non-exact retakes need the model.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| Endpoint down | Fail with a clear connection error |
| Auth failure | Fail without echoing the key |
| Invalid JSON | Retry once, then fail |
| Unknown ids | Fail the module |
| Model discards everything | Guard restores the keeper of each cluster |
| No clusters | All discards accepted if ids are valid |

## Tests

| Id | Case |
| --- | --- |
| T-04-01 | Model drops all three attempts; last is restored |
| T-04-02 | Legal cull passes unchanged |
| T-04-03 | Unknown id fails without partial state |
| T-04-04 | keep_best picks the highest score |
| T-04-05 | keep_best without scores picks the last |
| T-04-06 | Exact repeats cluster across punctuation and case |
| T-04-07 | Empty reasoning is rejected |
| T-04-08 | Manual override beats a model keep |
| T-04-09 | Secret never appears in the prompt, log, or state |

AC: 03, 07.
