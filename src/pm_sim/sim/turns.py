"""Turn execution helpers for the run loop."""

from __future__ import annotations

from dataclasses import dataclass

from pm_sim.sim.action_duration import resolve_wait_minutes
from pm_sim.sim.clock import advance_clock
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent, enqueue, process_due_events
from pm_sim.sim.health import compute_project_health


@dataclass
class ToolTurnResult:
  processed_event_ids: list[str]
  health: str = "ON_TRACK"
  minutes_advanced: int = 0


@dataclass
class WaitTurnResult:
  processed_event_ids: list[str]
  health: str = "ON_TRACK"
  minutes_advanced: int = 0


def execute_wait_turn(db: SimDatabase) -> WaitTurnResult:
  """Agent chose wait: advance clock, drain due events, refresh project health."""
  minutes = resolve_wait_minutes(db)
  advance_clock(db, minutes=minutes)
  processed = process_due_events(db)
  health = compute_project_health(db)
  db.set_meta("project_health", health)
  return WaitTurnResult(
    processed_event_ids=processed,
    health=health,
    minutes_advanced=minutes,
  )


def execute_tool_turn(db: SimDatabase, event: SimEvent, *, minutes: int = 1) -> ToolTurnResult:
  """Agent chose a tool action: insert event, drain at T, advance clock, drain again."""
  enqueue(db, event)
  processed = process_due_events(db)
  advance_clock(db, minutes=minutes)
  processed.extend(process_due_events(db))
  health = compute_project_health(db)
  db.set_meta("project_health", health)
  return ToolTurnResult(
    processed_event_ids=processed,
    health=health,
    minutes_advanced=minutes,
  )
