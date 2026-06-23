"""Load scenario NPC policy and message templates."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from pm_sim.npcs.types import PolicyTemplate
from pm_sim.scenario.load import scenario_dir


def _load_yaml(path: Path) -> dict[str, Any]:
  with path.open(encoding="utf-8") as f:
    return yaml.safe_load(f) or {}


@lru_cache(maxsize=8)
def load_policy_templates(scenario_id: str) -> tuple[PolicyTemplate, ...]:
  data = _load_yaml(scenario_dir(scenario_id) / "policy_templates.yaml")
  templates: list[PolicyTemplate] = []
  for raw in data.get("templates") or []:
    templates.append(
      PolicyTemplate(
        id=str(raw["id"]),
        trigger=str(raw["trigger"]),
        condition=str(raw.get("condition") or ""),
        action=str(raw["action"]),
        requires_role=raw.get("requires_role"),
        requires_goal=raw.get("requires_goal"),
        requires_constraint=raw.get("requires_constraint"),
      )
    )
  return tuple(sorted(templates, key=lambda t: t.id))


@lru_cache(maxsize=8)
def load_coworkers(scenario_id: str) -> dict[str, dict[str, Any]]:
  data = _load_yaml(scenario_dir(scenario_id) / "coworkers.yaml")
  return {c["id"]: c for c in (data.get("coworkers") or [])}


@lru_cache(maxsize=8)
def load_message_templates(scenario_id: str) -> dict[str, str]:
  data = _load_yaml(scenario_dir(scenario_id) / "message_templates.yaml")
  messages = data.get("messages") or {}
  return {str(key): str(value) for key, value in messages.items()}


def template_by_id(scenario_id: str, template_id: str) -> PolicyTemplate | None:
  for template in load_policy_templates(scenario_id):
    if template.id == template_id:
      return template
  return None
