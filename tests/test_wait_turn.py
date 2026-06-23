"""Tests for wait-turn execution."""

from pathlib import Path

import pytest

from pm_sim.sim.clock import get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import enqueue
from pm_sim.sim.task_timers import schedule_task_complete
from pm_sim.sim.turns import execute_wait_turn


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = SimDatabase(tmp_path / "test.db")
  database.init_schema()
  database.set_meta("sim_time", "2026-06-22T09:00:00")
  database.conn.execute(
    """
    INSERT INTO tasks (id, title, status, owner_id, duration_minutes, depends_on)
    VALUES ('PROJ-99', 'Wiki update', 'in_progress', 'sam', 60, '[]')
    """
  )
  database.conn.commit()
  return database


def test_wait_turn_advances_clock_and_updates_health(db: SimDatabase) -> None:
  result = execute_wait_turn(db)

  assert get_sim_time(db).isoformat() == "2026-06-22T09:01:00"
  assert result.minutes_advanced == 1
  assert result.health in ("ON_TRACK", "AT_RISK", "BLOCKED")

  row = db.conn.execute(
    "SELECT status FROM tasks WHERE id = 'PROJ-99'"
  ).fetchone()
  assert row["status"] == "in_progress"


def test_wait_turn_drains_task_complete_and_milestone_check(db: SimDatabase) -> None:
  db.conn.execute(
    """
    UPDATE tasks SET duration_minutes = 1 WHERE id = 'PROJ-99'
    """
  )
  db.conn.execute(
    """
    INSERT INTO milestones (id, title, due_at, status, depends_on_tasks)
    VALUES ('launch', 'Launch', '2026-06-26T18:00:00', 'pending', '["PROJ-99"]')
    """
  )
  completion = schedule_task_complete(
    db, "PROJ-99", source="test",
  )
  assert completion is not None
  enqueue(db, completion)
  db.conn.commit()

  execute_wait_turn(db)

  task = db.conn.execute(
    "SELECT status FROM tasks WHERE id = 'PROJ-99'"
  ).fetchone()
  assert task["status"] == "done"

  launch = db.conn.execute(
    "SELECT status FROM milestones WHERE id = 'launch'"
  ).fetchone()
  assert launch["status"] == "completed"


def test_wait_turn_uses_custom_wait_minutes(db: SimDatabase) -> None:
  db.set_meta("wait_minutes", "5")
  result = execute_wait_turn(db)
  assert get_sim_time(db).isoformat() == "2026-06-22T09:05:00"
  assert result.minutes_advanced == 5
