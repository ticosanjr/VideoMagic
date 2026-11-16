"""Manual DaVinci Resolve Studio smoke check.

Run on the machine that has Resolve Studio open with External Scripting enabled.
The script never modifies a user timeline unless an explicit FCPXML push is
requested; the pull/sync path is read-only for markers/cuts.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from videoflow.adapters.resolve import resolve_roundtrip, resolve_status
from videoflow.core.context import PipelineContext
from videoflow.domain.state import ProjectState


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fcpxml", default="")
    parser.add_argument("--direction", choices=("push", "pull", "sync"), default="pull")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    report = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": resolve_status(),
    }
    if args.fcpxml and report["status"].get("available"):
        root = Path(args.fcpxml).expanduser().parent
        context = PipelineContext(
            source=root / "source.mp4",
            output=root,
            work=root / "work",
            exports=root,
            state=ProjectState(),
        )
        report["roundtrip"] = resolve_roundtrip(
            context,
            direction=args.direction,
            path=args.fcpxml,
            apply=args.apply,
        )
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.json_out:
        target = Path(args.json_out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["status"].get("available") else 2


if __name__ == "__main__":
    raise SystemExit(main())
