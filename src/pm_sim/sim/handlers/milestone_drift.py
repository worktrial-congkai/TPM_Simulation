"""milestone.drift — slip launch when drift conditions still hold."""

from __future__ import annotations

import json
from datetime import timedelta

from pm_sim.sim.clock import format_sim_time, parse_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent


def _record_drift_outcome(db: SimDatabase, event: SimEvent, label: str) -> None:
  payload = dict(event.payload or {})
  payload["world_effects"] = [label]
  db.conn.execute(
    "UPDATE events SET payload = ? WHERE id = ?",
    (json.dumps(payload), event.id),
  )


def handle_milestone_drift(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  task_id = event.payload.get("task_id", "PROJ-17")
  milestone_id = event.payload.get("milestone_id", "launch")
  slip_days = int(event.payload.get("slip_days", 1))

  row = db.conn.execute(
    "SELECT status FROM tasks WHERE id = ?", (task_id,)
  ).fetchone()
  if row is None or row["status"] != "blocked":
    _record_drift_outcome(
      db,
      event,
      "no launch slip — launch date unchanged (blocker resolved)",
    )
    return []

  milestone = db.conn.execute(
    "SELECT due_at, status FROM milestones WHERE id = ?", (milestone_id,)
  ).fetchone()
  if milestone is None:
    return []

  due = parse_sim_time(milestone["due_at"])
  new_due = due + timedelta(days=slip_days)

  db.conn.execute(
    "UPDATE milestones SET due_at = ?, status = 'slipped' WHERE id = ?",
    (format_sim_time(new_due), milestone_id),
  )

  current_slip = int(db.get_meta("launch_slipped_days") or "0")
  db.conn.execute(
    "INSERT INTO sim_meta (key, value) VALUES ('launch_slipped_days', ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
    (str(current_slip + slip_days),),
  )

  _record_drift_outcome(
    db,
    event,
    f"launch slipped +{slip_days}d — {task_id} still blocked",
  )

  return []
