"""Load eval rubric YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pm_sim.scenario.load import load_yaml, scenario_dir


@dataclass(frozen=True)
class RubricCheck:
  id: str
  condition: str | None = None
  penalty_if: str | None = None
  deadline: str | None = None
  late_decay_days: float | None = None
  on_time_floor: float | None = None
  full_credit_within_minutes: int | None = None
  decay_minutes: int | None = None
  penalty_max: float | None = None
  penalty_scale: float | None = None


@dataclass(frozen=True)
class RubricComponent:
  id: str
  weight: float
  checks: tuple[RubricCheck, ...] = ()
  scoring: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RubricSpec:
  components: tuple[RubricComponent, ...]


def _parse_checks(raw_checks: list[dict[str, Any]] | None) -> tuple[RubricCheck, ...]:
  if not raw_checks:
    return ()
  return tuple(
    RubricCheck(
      id=check["id"],
      condition=check.get("condition"),
      penalty_if=check.get("penalty_if"),
      deadline=check.get("deadline"),
      late_decay_days=check.get("late_decay_days"),
      on_time_floor=check.get("on_time_floor"),
      full_credit_within_minutes=check.get("full_credit_within_minutes"),
      decay_minutes=check.get("decay_minutes"),
      penalty_max=check.get("penalty_max"),
      penalty_scale=check.get("penalty_scale"),
    )
    for check in raw_checks
  )


def load_rubric(scenario_id: str) -> RubricSpec:
  path = scenario_dir(scenario_id) / "eval_rubric.yaml"
  data = load_yaml(path)
  components: list[RubricComponent] = []
  for comp_id, comp_data in data.items():
    if not isinstance(comp_data, dict):
      continue
    components.append(
      RubricComponent(
        id=comp_id,
        weight=float(comp_data.get("weight", 0)),
        checks=_parse_checks(comp_data.get("checks")),
        scoring=dict(comp_data.get("scoring") or {}),
      )
    )
  return RubricSpec(components=tuple(components))
