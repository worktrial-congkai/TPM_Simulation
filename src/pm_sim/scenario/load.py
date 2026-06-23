"""Scenario path helpers and YAML loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SCENARIOS_DIR = Path("scenarios")


def _repo_root() -> Path:
  return Path(__file__).resolve().parents[3]


def scenario_dir(scenario_id: str) -> Path:
  return _repo_root() / SCENARIOS_DIR / scenario_id


def load_yaml(path: Path) -> dict[str, Any]:
  with path.open(encoding="utf-8") as f:
    return yaml.safe_load(f) or {}
