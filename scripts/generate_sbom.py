"""Write a CycloneDX-style JSON SBOM for the current Python environment."""

from __future__ import annotations

import argparse
import json
from importlib.metadata import distributions
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist/sbom.json")
    args = parser.parse_args()
    components = []
    for distribution in distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name or not version:
            continue
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name.lower()}@{version}",
            }
        )
    components.sort(key=lambda item: (item["name"].lower(), item["version"]))
    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "videoflow"}},
        "components": components,
    }
    target = Path(args.output).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {target} ({len(components)} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
