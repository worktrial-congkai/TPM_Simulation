"""vendor.turnaround_complete — unblock PROJ-17 after vendor escalation timer."""

from __future__ import annotations

from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent
from pm_sim.sim.task_timers import schedule_task_complete


def handle_vendor_turnaround(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  task_id = event.payload.get("task_id", "PROJ-17")
  db.conn.execute(
    """
    UPDATE tasks
    SET status = 'in_progress', blocker_reason = NULL
    WHERE id = ?
    """,
    (task_id,),
  )

  followups: list[SimEvent] = []
  completion = schedule_task_complete(
    db,
    task_id,
    source=f"vendor.turnaround_complete:{task_id}",
  )
  if completion:
    followups.append(completion)
  return followups
