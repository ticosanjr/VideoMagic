# Cache

## 1. Goal

A parameter change must reprocess only what that parameter affects. Changing
`punch_in_scale` must not re-run Whisper.

## 2. Identity

```
hash = SHA256(canonical({
  module, module_version, enabled, params,
  upstream_hash, media_fingerprint,
  model_artifact_digest, prompt_template_version
}))
```

| Field | Why it is part of the identity |
| --- | --- |
| `module` | Two modules cannot share a cache entry |
| `module_version` | A bug fix invalidates old results |
| `enabled` | A bypassed module has an identity result, not no result |
| `params` | The module's configuration |
| `upstream_hash` | Upstream data changes must propagate |
| `media_fingerprint` | The PCM digest, not the container path |
| `model_artifact_digest` | A different Whisper/VAD artifact is different work |
| `prompt_template_version` | A prompt change can change retakes |

`mtime` and the source path are deliberately absent. A copied file with identical
PCM is identical work. A touched file is not different work.

## 3. Canonicalization

- Object keys are sorted.
- JSON is encoded with compact separators and UTF-8.
- Booleans are booleans, not `1`/`0`.
- Floats are quantized to 6 decimal places, half-even, then formatted.
- Non-finite floats raise.
- Enums use their value.
- Map keys must be strings.
- Unsupported types raise instead of using `repr`, which is not stable.

Quantizing a float is a deliberate contract. `1.15` and `1.1500000004` hash
identically; `1.15` and `1.16` do not. Integers and floats remain distinct.

## 4. Status

| Status | Meaning | What a full run does |
| --- | --- | --- |
| `cached` | Stored hash matches the current identity | Skip |
| `dirty` | Parameters or upstream changed | Execute |
| `missing` | No artifact for this identity | Execute |
| `bypassed` | Module is disabled | Skip; identity result exists |
| `failed` | Last attempt failed | Execute |
| `blocked` | Upstream cannot provide data | Execute once upstream is ready |
| `running` | A job owns it | Reject a second job |

## 5. Storage layout

```
.videoflow/cache/<module>/<hash>/
  payload.json
  artifacts/
```

- `payload.json` records the module id, hash, version, and a summary.
- Writes go to a temp directory and are renamed into place.
- A prune command removes entries not referenced by the current or a recent
  revision. Pruning is manual in v1.
- The cache may be deleted at any time. It is not a source of truth.

## 6. What is not cached

- The source media.
- The project state. That is versioned, not cached.
- A failed partial artifact.

## 7. Invalidation examples

| Change | Re-runs |
| --- | --- |
| `punch_in_scale` 1.15 → 1.25 | zooms, export |
| `speech_threshold` | vad, jl_cuts, zooms, shorts, export |
| Transcript model `small` → `medium` | transcribe, retakes, jl_cuts, zooms, shorts, export |
| New source file with the same PCM | nothing |
| New source file with different PCM | everything |
| Disable shorts | shorts (identity), export |
| Change the retake prompt version | retakes, jl_cuts, zooms, shorts, export |
| Change zooms only with shorts disabled | zooms, export |

These are the cases that the cache tests and AC-05 encode.

## 8. Failure and concurrency

- The project lock serialises jobs.
- Two processes cannot both promote artifacts for one project.
- A crashed job cannot leave a half-written cache entry because the rename is
  atomic.
- An interrupted transcription leaves a temp file; the next run removes stale
  temp directories.
