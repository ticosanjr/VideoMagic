# Human-in-the-loop (HILT)

HILT pauses a recipe at a durable checkpoint, asks a person for a decision,
answers, or files, and resumes the same recipe from the last checkpoint.

## Storage

Every interaction is written beside the project output:

```
output/hilt/<interaction_id>/
  request.json        # immutable request: questions, files, artifacts, channels
  response.json       # answers, action, comment, attachments, responder
  uploads.json        # uploaded attachment manifest
  events.jsonl        # created/notified/attachment/responded/resumed
  notifications.jsonl # local notification attempts
  files/              # uploaded files, kept for audit
```

The interaction id is deterministic from the step id and gate id. A response is
idempotent: answering twice returns the first recorded response.

## Steps

| Step | Purpose |
| --- | --- |
| `human.gate` | Approve or reject with a comment and review artifacts. |
| `human.input` | Ask typed questions: text, textarea, choice, boolean, number, file. |
| `human.files` | Receive new or revised files, validate them, and copy them to targets. |

All human steps are non-cacheable so a resumed run always re-reads the current
response. The legacy `approvals/<gate>.json` file remains supported.

## Job states

- `waiting_approval`: a gate is waiting for approve/reject.
- `waiting_input`: a question or file handoff is waiting.
- `answered`: the waiting job was superseded by the resumed run.

## API

```http
GET  /api/v1/jobs/{job_id}/interactions
GET  /api/v1/jobs/{job_id}/interactions/{interaction_id}
POST /api/v1/jobs/{job_id}/interactions/{interaction_id}/respond
POST /api/v1/jobs/{job_id}/interactions/{interaction_id}/files
POST /api/v1/jobs/{job_id}/interactions/{interaction_id}/cancel
GET  /api/v1/jobs/{job_id}/interactions/{interaction_id}/artifacts/{artifact_id}
GET  /api/v1/hilt/pending
GET  /api/v1/hilt/channels
POST /api/v1/hilt/test
```

`respond` accepts `action` (`approve`, `reject`, `submit`), `answers`, `comment`,
and an optional `token` for external channels. `files` is multipart and accepts
one or more `files` plus an optional `request_id`.

## Security

- Paths are resolved inside the job output; `..` and absolute paths outside it
  are rejected.
- Attachments are checksummed, size-limited, and type-checked when the file
  request declares accepted suffixes/MIME types.
- External channel responses require a token; the raw token is never returned by
  the API and only its SHA-256 is persisted.
- Notification failures are logged and never fail the job.

## Current channels

M0 ships the local channel: the studio panel plus a best-effort desktop
notification (`notify-send` on Linux, `osascript` on macOS). E-mail, Slack, and
Signal are the next milestone; the request/response contract already supports
them through the same service.

## Full AI Editor

`full_ai_editor` is a built-in, favorite recipe that uses HILT for the editorial
brief, research datasets, script lock, decoupage audit, entity corrections, style
lock, sample homologation, fact-check, and final approval.
