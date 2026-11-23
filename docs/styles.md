# Style catalog

VideoFlow stores channel/editorial styles as Markdown files with YAML
frontmatter. The catalog is the source of truth for style settings, learned
rules, and the OpenCode workspace presets.

## Storage

```text
{VF_DATA_DIR}/styles/<style_id>.md
```

Built-in seeds ship inside the package at `src/videoflow/styles/`:

- 3 base channel styles (`canal-*`);
- 5 Longform styles (`lf-*`);
- 10 Shorts/Reels styles (`sr-*`).

A user file overrides a seed with the same `style_id`. The legacy
`~/.videoflow/channels/*.json` rulebook is read only as a migration fallback.

## Compiler

`vf_style(action="validate", style_id=style_id)` checks every referenced caption preset, layout
mode, motion engine, and font. Unknown presets no longer fall back silently.
Fonts resolve through `fc-match` first, then through metric-compatible aliases
(`Arial`/`Helvetica` → `Liberation Sans`, `Times New Roman` → `Liberation
Serif`, `Courier New` → `Liberation Mono`, `Segoe UI` → `DejaVu Sans`), so a
Linux render keeps the intended metrics when the exact family is missing. ASS
captions write the resolved family, not the alias.

`vf_style_apply(project_id, style_id)` compiles the Markdown metadata into
timeline, audio, caption, layout, and motion parameters, writes a
non-destructive `beat_map.json` draft, and returns a revision diff without
rewriting the timeline.

## Format

```markdown
---
schema_version: 2
style_id: canal-paula-reels
name: "Canal Paula — Reels"
aspect_ratio: "9:16"
target_lufs: -16.5
max_static_sec: 3.0
min_silence_ms: 260
layout_mode: cutout
caption_preset: kinetic_highlight
motion_engine: hyperframes
platforms: [reels, tiktok, shorts]
beatmap_defaults: {caption_safe_zone: true, linked_sfx: true}
sound_design: {music_arc: three_act, ducking: true}
hook_strategy: "Gancho visual em 2 s."
intro_strategy: "Cutout + prova visual."
export_targets: [mp4_youtube, resolve, premiere, kdenlive]
palette: ["#f97316", "#111827"]
fonts: [Inter]
cut_rhythm: {median_cut_sec: 1.4}
safe_zones: {reels: {bottom: 0.18, right: 0.14}}
updated_at: "2026-11-16T21:00:00Z"
---

# Direção Visual & Editorial

- Cortes rápidos, legendas cinéticas e cutout do apresentador.

## Regras Aprendidas

- Cortar antes de 1,2 s.
```

- `style_id` must match `[a-z0-9][a-z0-9._-]{0,79}`.
- Learned rules are capped at **15**. Duplicate/exact rules gain weight; similar
  rules are consolidated.
- Frontmatter values are validated by Pydantic (`StyleDefinition`).
- The body keeps the human-readable direction. `## Regras Aprendidas` is the
  managed rule section.

## Mapping to recipes

`rulebook_from_style()` derives the existing `PresetRulebook`/brand kit
used by recipes:

| Style field | Applied to |
| --- | --- |
| `target_lufs` | `audio.master`, `audio.qa` |
| `min_silence_ms` | `audio.vad` |
| `layout_mode` | `layout.cutout` |
| `caption_preset` | `captions.plan`, `shorts.captions` |
| `motion_engine` | `motion.render` |
| `export_targets` | `export.nle`, `delivery.package` |
| `palette` / `fonts` | brand kit and legacy `style` preset |

## Interfaces

MCP:

```text
vf_style(action="list")
vf_style(action="get", style_id="canal-paula-reels")
vf_style(action="save", style_id="meu-estilo", name="Meu Estilo",
         target_lufs=-14, export_targets=["mp4_youtube", "resolve"],
         workspace_dir="/path/to/workspace")
vf_style(action="learn_rule", style_id="meu-estilo",
         feedback_note="Cortar antes de 1s")
vf_style(action="sync", workspace_dir="/path/to/workspace")
```

Resources: `vf://styles` and `vf://styles/{style_id}`.

CLI:

```bash
videoflow style list
videoflow style save ./meu-estilo.md --workspace /path/to/workspace
videoflow style save meu-estilo --name "Meu Estilo" --body "# Direção"
videoflow style learn meu-estilo --note "Cortar antes de 1s"
videoflow style sync --workspace /path/to/workspace
```

REST:

```text
GET    /api/v1/styles
GET    /api/v1/styles/{style_id}
POST   /api/v1/styles
DELETE /api/v1/styles/{style_id}
POST   /api/v1/styles/{style_id}/learn
POST   /api/v1/styles/sync
```

`vf_project(action="init|open", style_id="...")` binds the style to the
project and stores `style_id` in both the project record and `project_state.json`.

## Sync to an OpenCode workspace

```python
from videoflow.application.style_catalog import StyleCatalog

StyleCatalog().sync("/path/to/workspace", overwrite=False)
```

Files are written to `<workspace>/presets/<style_id>.md` plus a
`.videoflow-styles.json` manifest containing SHA-256 hashes. With
`overwrite=False`, a locally modified file is skipped. `overwrite=True` replaces
it.

The catalog uses an mtime cache for reads and a best-effort SQLite index
(`styles` table) for discovery. The filesystem remains the source of truth.
