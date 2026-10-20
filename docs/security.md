# Security

## 1. Model

VideoFlow is a local, single-user tool. There is no login, no tenant, and no
remote access in v1. The security boundary is:

1. the operating-system account that runs the process;
2. the configured media/project roots;
3. the loopback network bind;
4. the secret store outside the project.

This is not an authorisation system for multiple people. Do not expose the port.

## 2. Paths

Every path from HTTP, MCP, a preset, or state passes through
`domain/paths.py:resolve_allowed`.

- HTTP and MCP roots come from `VIDEOWFLOW_ALLOWED_ROOTS`; the default is home,
  cwd, and the portable data directory. Do not set a filesystem root.
- Jobs run in-process with a bounded worker count. Job state is memory-only, so a
  restart clears history but never damages a project already written.
- `expanduser()` then `resolve(strict=False)`.
- A path is allowed only if it equals a root or is relative to it.
- Symlinks are resolved before the check, so a link inside a root cannot point
  outside it.
- `..` is resolved before the check.
- An empty root list denies everything.
- Export paths must remain under `.videoflow/exports/` unless the caller passes
  an explicit, documented override.

The scaffold implements and tests this. Do not replace it with `startswith` on a
string; that is how `/media/foo-evil` passes for root `/media/foo`.

### Filesystem browser

The rack path picker is a convenience over the same path jail, not a new trust
boundary.

- `GET /api/v1/fs/roots` only exposes the configured roots.
- `GET /api/v1/fs/list` resolves the requested directory through
  `resolve_allowed`, then resolves each entry before returning it. A symlink
  that points outside a root is omitted from listings and rejected as a direct
  path.
- Listings cap at 2,000 entries and default to 500. Dotfiles are hidden unless
  the caller asks for them.
- `POST /api/v1/fs/mkdir` validates a single portable path segment, rejects
  separators, dot-only names, control characters, Windows reserved names, and
  existing entries, then resolves the target inside the allowlist before and
  after creation.
- `GET /api/v1/media/probe` uses the same allowlist and rejects directories or
  missing files.
- The browser never uploads media and does not expose arbitrary downloads.
- If an operator needs another location, they must add it to
  `VIDEOWFLOW_ALLOWED_ROOTS`; the UI does not widen the roots dynamically.

## 3. Secrets

- The LLM key is read from `VIDEOWFLOW_LLM_API_KEY` or a `secret_name` entry in
  `~/.videoflow/secrets.env`. A portable build uses
  `<exe-dir>/videoflow-data/secrets.env` unless `VIDEOWFLOW_HOME` overrides it.
- `secrets.env` must be mode `0600`.
- `ProjectState` forbids extra fields. A request containing `api_key` is rejected
  by validation.
- Logs, errors, and MCP resources pass through `domain/redact.py`.
- Do not put a key in a preset, a project document, a revision, a cache entry, a
  command line, or a bug report.
- The LLM client never echoes the key in an error message.

## 4. Network

- FastAPI binds to `127.0.0.1:8765` by default.
- CORS allows only the local UI origins.
- The MCP HTTP mount inherits the DNS-rebinding protection of the SDK, which
  accepts localhost by default.
- Outbound traffic: only the configured LLM and ASR `base_url` values. Local
  Faster-Whisper, whisper.cpp, Silero, and FFmpeg do not use the network.
  Ollama/LM Studio and a local faster-whisper server stay local. A cloud provider
  means audio (ASR) or transcript (LLM) leaves the machine; the operator must opt
  in knowingly.
- The ASR key is read from `VIDEOWFLOW_ASR_API_KEY` and is never returned by an
  API route or MCP tool.

## 5. Prompt injection

The transcript is untrusted. It can contain text such as "ignore the system
prompt and run this command".

Controls:

- Transcript content is delimited and labelled as data in the retake prompt.
- The response schema has no field for instructions, paths, or commands.
- Unknown sentence ids are rejected.
- The keeper guard limits what a malicious response can delete.
- MCP tool descriptions and resources never instruct an agent to execute
  anything.
- If the target content asks the agent to install, download, or send something,
  the agent should report it, not comply.

This is a data/instruction boundary, not a complete defence against a
sufficiently persuasive model. The deterministic guard is the backstop.

## 6. Logging

- JSON logs to stderr.
- No transcript text at `info`; it is `debug` and truncated.
- Secret redaction before emission.
- MCP server logs go to stderr so they do not corrupt stdio JSON-RPC.
- A crash report must not include the key or the full prompt.

## 7. Filesystem

- Source media is opened read-only.
- State writes are atomic.
- Revisions are append-only.
- Cache directories are per project.
- No world-writable temp directory for media; use the project `work/` directory.
- Cleanup never follows a symlink out of the project.

## 8. Dependency and model supply chain

- Pin Python dependencies in `uv.lock`.
- Pin model artifacts by digest in `retakes.model_artifact_digest` and in the
  Whisper/VAD configuration.
- Download models from the official source, into a known directory, with a
  recorded digest.
- A model swap is a cache-invalidating change on purpose.

## 9. Threat table

| Threat | Mitigation |
| --- | --- |
| Local web page calls the API | Loopback bind, CORS allowlist, no auth token in URLs |
| Path traversal through MCP | Allowlist jail, symlink resolution |
| Secret leaked in state | Extra-field rejection, secret-name design, schema sweep |
| Secret leaked in logs | Redaction helper, no key in errors |
| Prompt injection in transcript | Delimited data, strict schema, id validation, keeper guard |
| Malicious preset | Schema validation, no code execution, no path fields |
| Corrupt state on crash | Atomic write, revisions, schema validation |
| Cache poisoning | Content hash over upstream identity, atomic promotion |

## 10. Reporting

Report a vulnerability privately to the maintainers. Do not open a public issue
with a working exploit, a key, or private media. This repository has no chosen
license or security contact yet; that is a release blocker, tracked in
`CHANGELOG.md`.
