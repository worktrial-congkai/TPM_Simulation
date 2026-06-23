"""Tests for task.complete scheduling."""

from datetime import timedelta
from pathlib import Path

import pytest

from pm_sim.sim.clock import get_sim_time, set_sim_time
from pm_sim.sim.events import SimEvent, process_due_events
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.turns import execute_tool_turn, execute_wait_turn


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_tasks_update_schedules_task_complete(db) -> None:
  db.conn.execute(
    "UPDATE tasks SET status = 'todo' WHERE id = 'PROJ-99'"
  )
  db.conn.commit()

  start = get_sim_time(db)
  event = SimEvent.create(
    event_type="agent.tasks_update",
    start_ts=start,
    source="test",
    payload={"action": "tasks_update", "task_id": "PROJ-99", "status": "in_progress"},
  )
  execute_tool_turn(db, event)

  pending = db.conn.execute(
    """
    SELECT start_ts FROM events
    WHERE event_type = 'task.complete' AND status = 'pending'
    """
  ).fetchone()
  assert pending is not None

  expected = start + timedelta(minutes=60)
  assert pending["start_ts"] == expected.strftime("%Y-%m-%dT%H:%M:%S")


def test_task_complete_fires_on_later_wait(db) -> None:
  db.conn.execute(
    "UPDATE tasks SET status = 'todo', duration_minutes = 2 WHERE id = 'PROJ-99'"
  )
  db.conn.commit()

  event = SimEvent.create(
    event_type="agent.tasks_update",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "tasks_update", "task_id": "PROJ-99", "status": "in_progress"},
  )
  execute_tool_turn(db, event)

  for _ in range(3):
    execute_wait_turn(db)

  task = db.conn.execute(
    "SELECT status FROM tasks WHERE id = 'PROJ-99'"
  ).fetchone()
  assert task["status"] == "done"
