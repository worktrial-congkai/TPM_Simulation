"""Project health computation (derived, not authoritative)."""

from __future__ import annotations

from pm_sim.sim.clock import get_sim_time, parse_sim_time
from pm_sim.sim.db import SimDatabase

HEALTH_ON_TRACK = "ON_TRACK"
HEALTH_AT_RISK = "AT_RISK"
HEALTH_BLOCKED = "BLOCKED"


def _launch_due_at(db: SimDatabase) -> str | None:
  row = db.conn.execute(
    "SELECT due_at FROM milestones WHERE id = 'launch'"
  ).fetchone()
  return row["due_at"] if row else None


def _critical_path_blocked(db: SimDatabase) -> bool:
  row = db.conn.execute(
    """
    SELECT COUNT(*) AS c FROM tasks
    WHERE critical_path = 1 AND status = 'blocked'
    """
  ).fetchone()
  return row["c"] > 0


def _critical_path_incomplete(db: SimDatabase) -> bool:
  row = db.conn.execute(
    """
    SELECT COUNT(*) AS c FROM tasks
    WHERE critical_path = 1 AND status != 'done'
    """
  ).fetchone()
  return row["c"] > 0


def _launch_slipped(db: SimDatabase) -> bool:
  row = db.conn.execute(
    "SELECT status FROM milestones WHERE id = 'launch'"
  ).fetchone()
  if row and row["status"] == "slipped":
    return True
  slipped = db.get_meta("launch_slipped_days")
  return slipped is not None and int(slipped) > 0


def compute_project_health(db: SimDatabase) -> str:
  if _critical_path_blocked(db):
    return HEALTH_BLOCKED

  if _launch_slipped(db):
    return HEALTH_AT_RISK

  due_at = _launch_due_at(db)
  if due_at and _critical_path_incomplete(db):
    sim_time = get_sim_time(db)
    due = parse_sim_time(due_at)
    hours_remaining = (due - sim_time).total_seconds() / 3600
    if hours_remaining < 48:
      return HEALTH_AT_RISK

  return HEALTH_ON_TRACK
