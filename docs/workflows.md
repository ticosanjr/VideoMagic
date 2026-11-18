# Workflows

Workflows are Markdown playbooks read by OpenCode before editing. They are not
MCP recipes; the MCP surface exposes only catalog steps.

## Storage

```text
{VF_DATA_DIR}/workflows/<workflow_id>.md
<workspace>/.opencode/workflows/<workflow_id>.md
```

Seeds ship at `src/videoflow/workflows/`:

- `youtube-longform.md`
- `reels-from-raw.md`
- `shorts-from-long.md`
- `decupagem-limpa.md`
- `clone-style.md`

## Format

```markdown
---
schema_version: 1
workflow_id: youtube-longform
name: YouTube Longform 16:9
description: Edição completa com B-roll, motion, QA e multi-NLE.
aspect_ratio: "16:9"
platforms: [youtube]
steps:
  - id: ingest
    node: ingest
    requires_approval: false
approvals: [beatmap, final_export]
export_targets: [mp4_youtube, resolve, premiere, kdenlive]
---

# Direção

1. Leia AGENTS.md e presets/.
2. Pergunte Estilo e Workflow.
3. Gere beatmap e peça aprovação.
```

## API

```text
GET/POST/GET-id/PUT/DELETE /api/v1/system/opencode/workflows[/{id}]
POST /api/v1/system/opencode/workflows/{id}/duplicate
POST /api/v1/system/opencode/workflows/{id}/restore
POST /api/v1/system/opencode/workflows/sync
```

## Bootstrap

`POST /api/v1/system/bootstrap/opencode` copies the selected `workflow_ids`
into `.opencode/workflows/` and generates the six slash commands.
