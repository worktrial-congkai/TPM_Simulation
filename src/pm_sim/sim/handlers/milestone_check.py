"""milestone.check — complete milestones when dependency tasks are done."""

from __future__ import annotations

import json

from pm_sim.sim.clock import format_sim_time, get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent


def _milestone_tasks_done(db: SimDatabase, depends_on_tasks: list[str]) -> bool:
  if not depends_on_tasks:
    return True
  for task_id in depends_on_tasks:
    row = db.conn.execute(
      "SELECT status FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None or row["status"] != "done":
      return False
  return True


def handle_milestone_check(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  sim_time = get_sim_time(db)
  completed_at = format_sim_time(sim_time)
  trigger_task = event.payload.get("task_id")

  rows = db.conn.execute("SELECT * FROM milestones").fetchall()
  for row in rows:
    if row["status"] == "completed":
      continue

    depends_on = json.loads(row["depends_on_tasks"] or "[]")
    if trigger_task and trigger_task not in depends_on:
      continue
    if not _milestone_tasks_done(db, depends_on):
      continue

    db.conn.execute(
      "UPDATE milestones SET status = 'completed' WHERE id = ?",
      (row["id"],),
    )
    if row["id"] == "launch":
      db.conn.execute(
        "INSERT INTO sim_meta (key, value) VALUES ('launch_sim_datetime', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (completed_at,),
      )

  return []
