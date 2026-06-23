"""Tests for milestone.check handler."""

from datetime import datetime
from pathlib import Path

import pytest

from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent, enqueue, process_due_events
from pm_sim.sim.task_timers import schedule_task_complete
from pm_sim.sim.turns import execute_wait_turn


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = SimDatabase(tmp_path / "test.db")
  database.init_schema()
  database.set_meta("sim_time", "2026-06-22T14:00:00")
  database.conn.execute(
    """
    INSERT INTO milestones (id, title, due_at, status, depends_on_tasks)
    VALUES ('launch', 'Launch', '2026-06-26T18:00:00', 'pending', '["PROJ-30"]')
    """
  )
  database.conn.execute(
    """
    INSERT INTO tasks (id, title, status, owner_id, critical_path, depends_on)
    VALUES ('PROJ-30', 'QA', 'done', 'alex', 1, '[]')
    """
  )
  database.conn.commit()
  return database


def test_milestone_check_completes_launch(db: SimDatabase) -> None:
  enqueue(db, SimEvent.create(
    event_type="milestone.check",
    start_ts=datetime(2026, 6, 22, 14, 0),
    source="test",
    payload={"task_id": "PROJ-30"},
  ))
  process_due_events(db)

  row = db.conn.execute(
    "SELECT status FROM milestones WHERE id = 'launch'"
  ).fetchone()
  assert row["status"] == "completed"
  assert db.get_meta("launch_sim_datetime") == "2026-06-22T14:00:00"


def test_task_complete_enqueues_milestone_check_on_completion(tmp_path: Path) -> None:
  database = SimDatabase(tmp_path / "tick.db")
  database.init_schema()
  database.set_meta("sim_time", "2026-06-22T09:00:00")
  database.conn.execute(
    """
    INSERT INTO tasks (
      id, title, status, owner_id, duration_minutes, depends_on
    ) VALUES ('PROJ-99', 'Wiki', 'in_progress', 'sam', 1, '[]')
    """
  )
  database.conn.execute(
    """
    INSERT INTO milestones (id, title, due_at, status, depends_on_tasks)
    VALUES ('launch', 'Launch', '2026-06-26T18:00:00', 'pending', '["PROJ-99"]')
    """
  )
  completion = schedule_task_complete(database, "PROJ-99", source="test")
  assert completion is not None
  enqueue(database, completion)
  database.conn.commit()

  execute_wait_turn(database)

  task = database.conn.execute(
    "SELECT status FROM tasks WHERE id = 'PROJ-99'"
  ).fetchone()
  assert task["status"] == "done"

  launch = database.conn.execute(
    "SELECT status FROM milestones WHERE id = 'launch'"
  ).fetchone()
  assert launch["status"] == "completed"
