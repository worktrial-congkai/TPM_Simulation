"""vendor.turnaround_complete — unblock PROJ-17 after vendor escalation timer."""

from __future__ import annotations

import json

from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent
from pm_sim.sim.task_timers import schedule_task_complete

PROJ17_UNBLOCKED_LABEL = "PROJ-17 (API integration) unblocked"


def handle_vendor_turnaround(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  task_id = event.payload.get("task_id", "PROJ-17")
  row = db.conn.execute(
    "SELECT status FROM tasks WHERE id = ?",
    (task_id,),
  ).fetchone()
  was_blocked = row is not None and row["status"] == "blocked"

  db.conn.execute(
    """
    UPDATE tasks
    SET status = 'in_progress', blocker_reason = NULL
    WHERE id = ?
    """,
    (task_id,),
  )

  if was_blocked:
    payload = dict(event.payload or {})
    payload["world_effects"] = [PROJ17_UNBLOCKED_LABEL]
    db.conn.execute(
      "UPDATE events SET payload = ? WHERE id = ?",
      (json.dumps(payload), event.id),
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
