"""Render one Kdenlive/MLT project with melt and report a JSON verdict."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--output", type=Path, default=Path("/tmp/videoflow-melt.mp4"))
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    melt = shutil.which("melt")
    if melt is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": "melt_missing",
                    "message": "Install the MLT melt package to render Kdenlive projects.",
                    "project": str(project),
                },
                indent=2,
            )
        )
        return 2
    if not project.is_file():
        print(
            json.dumps(
                {"ok": False, "code": "project_missing", "project": str(project)},
                indent=2,
            )
        )
        return 2
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [melt, "-consumer", f"avformat:{output}", str(project)],
        capture_output=True,
        text=True,
        timeout=args.timeout,
        check=False,
    )
    payload = {
        "ok": completed.returncode == 0 and output.is_file() and output.stat().st_size > 0,
        "project": str(project),
        "output": str(output),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-8000:],
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
