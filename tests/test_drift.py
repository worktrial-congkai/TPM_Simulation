"""Tests for milestone drift."""

from datetime import datetime
from pathlib import Path

import pytest

from pm_sim.sim.clock import set_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent, enqueue, process_due_events
from pm_sim.sim.reset import reset_scenario


def test_drift_slips_launch_when_proj17_still_blocked(tmp_path: Path) -> None:
  db_path = tmp_path / "sim.db"
  db = reset_scenario("first-week-pm", db_path=db_path)
  set_sim_time(db, datetime(2026, 6, 23, 18, 0))

  process_due_events(db)

  milestone = db.conn.execute(
    "SELECT due_at, status FROM milestones WHERE id = 'launch'"
  ).fetchone()
  assert milestone["status"] == "slipped"
  assert milestone["due_at"] == "2026-06-25T18:00:00"
  assert db.get_meta("launch_slipped_days") == "1"
  db.close()


def test_drift_does_not_fire_if_task_unblocked(tmp_path: Path) -> None:
  db = SimDatabase(tmp_path / "drift.db")
  db.init_schema()
  db.set_meta("sim_time", "2026-06-23T18:00:00")
  db.set_meta("launch_slipped_days", "0")
  db.conn.execute(
    """
    INSERT INTO milestones (id, title, due_at, status, depends_on_tasks)
    VALUES ('launch', 'Launch', '2026-06-26T18:00:00', 'pending', '[]')
    """
  )
  db.conn.execute(
    """
    INSERT INTO tasks (id, title, status, owner_id, critical_path, depends_on)
    VALUES ('PROJ-17', 'API', 'in_progress', 'alex', 1, '[]')
    """
  )
  db.conn.commit()

  enqueue(db, SimEvent.create(
    event_type="milestone.drift",
    start_ts=datetime(2026, 6, 23, 18, 0),
    source="test",
    payload={"task_id": "PROJ-17", "milestone_id": "launch", "slip_days": 1},
  ))
  process_due_events(db)

  milestone = db.conn.execute(
    "SELECT due_at, status FROM milestones WHERE id = 'launch'"
  ).fetchone()
  assert milestone["status"] == "pending"
  assert milestone["due_at"] == "2026-06-26T18:00:00"
