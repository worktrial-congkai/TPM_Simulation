"""Tests for vendor turnaround handler."""

from datetime import datetime
from pathlib import Path

import pytest

from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent
from pm_sim.sim.turns import execute_tool_turn, execute_wait_turn


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = SimDatabase(tmp_path / "test.db")
  database.init_schema()
  database.set_meta("sim_time", "2026-06-22T10:00:00")
  database.conn.execute(
    """
    INSERT INTO tasks (
      id, title, status, owner_id, blocker_reason, critical_path,
      duration_minutes, depends_on
    ) VALUES ('PROJ-17', 'API', 'blocked', 'alex', 'integration issue', 1, 2, '[]')
    """
  )
  database.conn.commit()
  return database


def test_vendor_turnaround_unblocks_proj17(db: SimDatabase) -> None:
  execute_tool_turn(db, SimEvent.create(
    event_type="vendor.turnaround_complete",
    start_ts=datetime(2026, 6, 22, 10, 0),
    source="test",
    payload={"task_id": "PROJ-17"},
  ))

  row = db.conn.execute(
    "SELECT status, blocker_reason FROM tasks WHERE id = 'PROJ-17'"
  ).fetchone()
  assert row["status"] == "in_progress"
  assert row["blocker_reason"] is None


def test_vendor_turnaround_schedules_task_complete(db: SimDatabase) -> None:
  execute_tool_turn(db, SimEvent.create(
    event_type="vendor.turnaround_complete",
    start_ts=datetime(2026, 6, 22, 10, 0),
    source="test",
    payload={"task_id": "PROJ-17"},
  ))

  pending = db.conn.execute(
    """
    SELECT event_type, start_ts FROM events
    WHERE event_type = 'task.complete' AND status = 'pending'
    """
  ).fetchone()
  assert pending is not None
  assert pending["start_ts"] == "2026-06-22T10:02:00"


def test_unblocked_task_completes_after_scheduled_duration(db: SimDatabase) -> None:
  execute_tool_turn(db, SimEvent.create(
    event_type="vendor.turnaround_complete",
    start_ts=datetime(2026, 6, 22, 10, 0),
    source="test",
    payload={"task_id": "PROJ-17"},
  ))

  for _ in range(3):
    execute_wait_turn(db)

  row = db.conn.execute(
    "SELECT status FROM tasks WHERE id = 'PROJ-17'"
  ).fetchone()
  assert row["status"] == "done"
