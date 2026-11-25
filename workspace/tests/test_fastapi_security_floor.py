"""Regression guard for FastAPI GHSA-f56c-v883-vx8r in the workspace."""
from pathlib import Path


def test_workspace_fastapi_minimum_excludes_affected_versions() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    dependency_line = next(line for line in pyproject.splitlines() if "fastapi>=" in line)
    # GHSA-f56c-v883-vx8r is fixed in 0.163.2; do not allow resolver backtracking
    # into the affected 0.123.2 <= version < 0.163.2 interval.
    assert "fastapi>=0.163.2,<0.166" in dependency_line
