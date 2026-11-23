# Output layout

`delivery.collect` groups final artifacts into one workspace-root folder:

```text
VideoFlow_Output/
  videos/
  exports/
  shorts/
  scenes/
  manifests/
```

This is a delivery convenience, not an MCP requirement. The MCP accepts any
output path and must never block, fail, or mark a job degraded because artifacts
live elsewhere. The folder can be overridden with `VF_OUTPUT_DIR` or
`paths.output_root`.

When the user did not choose another destination, run it after the last export:

```text
vf_run(project_id="...", steps=["delivery.collect"],
        params={"mode": "copy"}, wait=True)
```

Rules:

- The collector copies by default; `mode="move"` is explicit.
- Source recordings stay where the user stored them.
- `manifests/<project>-collect.json` records copied, moved, and skipped files.
- If the only copy of a deliverable is under `work/`, warn about it; do not
  treat that as a validation failure.
- Custom output directories are always valid.
