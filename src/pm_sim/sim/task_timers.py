"""Explicit task completion timers."""

from __future__ import annotations

import json
from datetime import timedelta

from pm_sim.sim.clock import get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent


def dependencies_met(db: SimDatabase, task_id: str) -> bool:
  row = db.conn.execute(
    "SELECT depends_on FROM tasks WHERE id = ?",
    (task_id,),
  ).fetchone()
  if row is None:
    return False
  for dep_id in json.loads(row["depends_on"] or "[]"):
    dep = db.conn.execute(
      "SELECT status FROM tasks WHERE id = ?",
      (dep_id,),
    ).fetchone()
    if dep is None or dep["status"] != "done":
      return False
  return True


def schedule_task_complete(
  db: SimDatabase,
  task_id: str,
  *,
  source: str,
) -> SimEvent | None:
  row = db.conn.execute(
    "SELECT duration_minutes FROM tasks WHERE id = ?",
    (task_id,),
  ).fetchone()
  if row is None or not row["duration_minutes"]:
    return None

  sim_time = get_sim_time(db)
  return SimEvent.create(
    event_type="task.complete",
    start_ts=sim_time + timedelta(minutes=int(row["duration_minutes"])),
    source=source,
    payload={"task_id": task_id},
  )
