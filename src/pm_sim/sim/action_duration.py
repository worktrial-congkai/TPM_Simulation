"""Per-action sim time costs — code defaults with scenario overrides in sim_meta."""

from __future__ import annotations

import json

from pm_sim.agent.types import AgentAction
from pm_sim.sim.db import SimDatabase

DEFAULT_ACTION_DURATIONS: dict[str, int] = {
  "tasks_list": 2,
  "start_next_critical_task": 1,
  "read_dm": 2,
  "read_email": 2,
  "ask_blocker_owner_dm": 3,
  "spam_ping_dm": 3,
  "escalate_vendor": 3,
  "send_status_update": 3,
  "schedule_requirements_meeting": 5,
  "schedule_tradeoff_meeting": 5,
  "write_decision_doc": 10,
  "default": 1,
}

DEFAULT_WAIT_MINUTES = 1


def _load_duration_overrides(db: SimDatabase) -> dict[str, int]:
  raw = db.get_meta("action_durations")
  if not raw:
    return {}
  data = json.loads(raw)
  if not isinstance(data, dict):
    return {}
  return {str(key): int(value) for key, value in data.items()}


def resolve_wait_minutes(db: SimDatabase) -> int:
  raw = db.get_meta("wait_minutes")
  if raw is None:
    return DEFAULT_WAIT_MINUTES
  return int(raw)


def resolve_action_duration(db: SimDatabase, action: AgentAction) -> int:
  if action.type == "wait":
    return resolve_wait_minutes(db)

  overrides = _load_duration_overrides(db)
  if action.name in overrides:
    return overrides[action.name]
  if action.name in DEFAULT_ACTION_DURATIONS:
    return DEFAULT_ACTION_DURATIONS[action.name]
  if "default" in overrides:
    return overrides["default"]
  return DEFAULT_ACTION_DURATIONS["default"]
