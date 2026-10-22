from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {".git", "node_modules", ".venv", "build", "test-results", "releases"}


def test_project_configuration_is_json_except_github_workflows() -> None:
    offenders = []
    for path in ROOT.rglob("*"):
        if any(part in EXCLUDED for part in path.parts):
            continue
        if path.suffix.casefold() not in {".yml", ".yaml"}:
            continue
        if path.is_relative_to(ROOT / ".github" / "workflows"):
            continue
        offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
