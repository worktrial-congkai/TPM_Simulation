"""task.complete — mark task done and check milestones."""

from __future__ import annotations

from pm_sim.sim.clock import get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent
from pm_sim.sim.task_timers import dependencies_met


def handle_task_complete(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  task_id = event.payload.get("task_id")
  if not task_id:
    return []

  row = db.conn.execute(
    "SELECT status FROM tasks WHERE id = ?",
    (task_id,),
  ).fetchone()
  if row is None or row["status"] != "in_progress":
    return []
  if not dependencies_met(db, task_id):
    return []

  db.conn.execute(
    "UPDATE tasks SET status = 'done' WHERE id = ?",
    (task_id,),
  )

  sim_time = get_sim_time(db)
  return [
    SimEvent.create(
      event_type="milestone.check",
      start_ts=sim_time,
      source=f"task.complete:{task_id}",
      payload={"task_id": task_id},
    ),
  ]
