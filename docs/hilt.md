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
POST /api/v1/hilt/approve
GET  /api/v1/hilt/channels
POST /api/v1/hilt/test
```

`respond` accepts `action` (`approve`, `reject`, `submit`), `answers`, `comment`,
and an optional `token` for external channels. `files` is multipart and accepts
one or more `files` plus an optional `request_id`. Expired interactions return
`410 hilt_expired` and are not resumed.

`/api/v1/hilt/approve` accepts `{items: [{job_id, interaction_id}], comment}` and
approves up to 50 gates in one request. Each item is resumed independently; the
response reports `approved` and `failed` items so one stale gate does not block
the rest. The inbox exposes the same action for selected approval cards.

The studio panel keeps answers, comments, and artifact review state in a
per-interaction local draft, shows upload progress, and offers per-artifact
review checkboxes. Drafts are cleared after a successful response.

## Security

- Paths are resolved inside the job output; `..` and absolute paths outside it
  are rejected.
- Attachments are checksummed, size-limited, and type-checked when the file
  request declares accepted suffixes/MIME types.
- External channel responses require a token; the raw token is never returned by
  the API and only its SHA-256 is persisted.
- Notification failures are logged and never fail the job.

## Channels

| Channel | Send | Receive |
| --- | --- | --- |
| Local | Studio panel + optional desktop notification (`notify-send`/`osascript`) | Studio API |
| E-mail | SMTP/TLS with the reply token in the subject | IMAP `UNSEEN` polling and attachments |
| Slack | Webhook or bot `chat.postMessage` | Bot history polling and optional Events API |
| Signal | `signal-cli` REST `/v2/send` | `/v1/receive` polling and attachment download |

All notifications are off by default. The master switch in
**Settings → Notifications** must be on, and the local/external channel must be
enabled, before anything is delivered. The in-app and desktop levels are `off`,
`required` (human interaction only), `important` (interaction plus failures),
and `all` (every event). The per-event checkboxes let you keep HITL and job
failures while dropping finished/cancelled jobs, warnings, and system messages.

`VIDEOWFLOW_NOTIFICATIONS=off` disables every channel; 
`VIDEOWFLOW_DESKTOP_NOTIFICATIONS=0` disables only the desktop pop-up. The test
suite sets both, so tests never show a system notification.

External channels are opt-in in Settings. They are best-effort: a failed
notification is written to `notifications.jsonl` and never fails the job.
Inbound replies must carry the interaction token; e-mail/Slack/Signal senders
can be restricted with allowlists. Slack Events requests are verified with the
signing secret.

The optional inbound webhooks are:

```http
POST /api/v1/hilt/slack/events
POST /api/v1/hilt/email/inbound
```

Notification secrets are stored through `POST /api/v1/hilt/secrets` using the
OS keyring when available; the API only reports presence, never the value.

## Full AI Editor

`full_ai_editor` is a built-in, favorite recipe that uses HILT for the editorial
brief, research datasets, script lock, decoupage audit, entity corrections, style
lock, sample homologation, fact-check, and final approval.

## Lamera Video Edit

`lamera_video_edit` is a built-in, favorite recipe organized in six colored
canvas groups. It adds HILT checkpoints for the presenter profile, separate
narration and edition approvals, the corrected entity manifest, placeholder
previews, the retention intro, and the repaired voice. The same brief, research,
master dossier, decoupage, style, asset-license, sample, fact-check, and final
approvals remain.

The **Produce · Lamera** tab is the operator workspace for this recipe. It
shows the six phase progress bars, recent runs, the pending HITL inbox, the
current approval/form with inline video and image previews, gate history, and
the job log. Approving a gate resumes the job from its checkpoint and the
workspace follows the resumed job id.
