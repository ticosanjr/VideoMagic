# Error catalog

Every API error is a JSON object with `detail` containing `ok: false`, `code`,
`message`, and optional `details`. MCP tool failures use the same object as
`structured_content` without the HTTP `detail` wrapper. The UI shows the code, a
human message, and the next action.

| Code | HTTP | Meaning | Next action |
| --- | --- | --- | --- |
| `path_not_allowed` | 403 | Path outside the allowed roots | Add the root in Settings → Paths |
| `path_not_found` | 404 | File or folder does not exist | Pick another path |
| `not_a_directory` | 422 | Expected a folder | Choose a folder |
| `permission_denied` | 403 | OS denied access | Fix permissions or choose another root |
| `job_queue_full` | 429 | Active job limit reached | Wait or pause/cancel a run |
| `job_not_found` | 404 | Unknown job id | Refresh Runs |
| `job_already_running` | 409 | Same job is active | Wait for it or cancel |
| `state_not_ready` | 409 | Timeline/state missing or locked | Finish the run, or unlock the track |
| `project_state_invalid` | 500 | Corrupt project state | Restore backup or re-run export |
| `media_not_found` | 422 | Source media missing | Re-link the source |
| `media_not_registered` | 409 | Media not in the library | Scan the folder in Media |
| `transcript_not_found` | 404 | No transcript yet | Run transcription or import SRT |
| `transcription_failed` | 502 | ASR failed | Check model/provider and retry |
| `llm_timeout` / `llm_failed` | 502 | LLM unreachable or invalid | Test connection, reduce prompt, retry |
| `external_service_blocked` | 403 | External call not allowed | Enable policy and allow the host |
| `capability_unavailable` | 501 | Feature has no engine in this build | Configure provider/model or skip |
| `recipe_invalid` | 422 | Recipe graph invalid | Use Validate and fix the step |
| `recipe_not_found` | 404 | Unknown recipe id | Pick from the list |
| `export_failed` | 500 | NLE/MP4 writer failed | Check logs and `scripts/qa_nle.py` |
| `render_failed` | 500 | FFmpeg render failed | Read stderr tail, retry |
| `waveform_failed` | 422 | Audio decode failed | Check source audio |
| `overlay_failed` | 422 | Overlay path invalid | Pick a file inside allowed roots |
| `backup_failed` | 500 | Backup could not be written | Check disk and home permissions |
| `plugin_not_found` | 404 | Unknown plugin id | Reload Extensions |
| `schema_too_new` | 409 | File written by a newer version | Upgrade VideoFlow |
| `internal_error` | 500 | Unexpected failure | Open the crash report path from the response |

## MCP

MCP tool failures use the same object as `structured_content`, so agents can
branch on `code`. Destructive tools are annotated `destructiveHint`; read-only
tools are annotated `readOnlyHint`.

## Rules

1. Never expose secrets, stack traces, or absolute home paths in `message`.
2. Always name the next action.
3. UI errors persist until dismissed; success notices auto-dismiss.
4. `details.report` points to a redacted crash report for `internal_error`.
