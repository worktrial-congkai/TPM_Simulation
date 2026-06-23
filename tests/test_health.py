"""Tests for project health computation."""

from datetime import datetime
from pathlib import Path

import pytest

from pm_sim.sim.clock import set_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.health import (
  HEALTH_AT_RISK,
  HEALTH_BLOCKED,
  HEALTH_ON_TRACK,
  compute_project_health,
)


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = SimDatabase(tmp_path / "test.db")
  database.init_schema()
  database.set_meta("sim_time", "2026-06-22T09:00:00")
  database.set_meta("launch_slipped_days", "0")
  database.conn.execute(
    """
    INSERT INTO milestones (id, title, due_at, status, depends_on_tasks)
    VALUES ('launch', 'Launch', '2026-06-26T18:00:00', 'pending', '["PROJ-30"]')
    """
  )
  database.conn.commit()
  return database


def _insert_cp_task(db: SimDatabase, task_id: str, status: str) -> None:
  db.conn.execute(
    """
    INSERT INTO tasks (id, title, status, owner_id, critical_path, depends_on)
    VALUES (?, ?, ?, 'alex', 1, '[]')
    """,
    (task_id, task_id, status),
  )
  db.conn.commit()


def test_blocked_critical_path_is_blocked(db: SimDatabase) -> None:
  _insert_cp_task(db, "PROJ-17", "blocked")
  assert compute_project_health(db) == HEALTH_BLOCKED


def test_slipped_launch_is_at_risk(db: SimDatabase) -> None:
  _insert_cp_task(db, "PROJ-17", "in_progress")
  db.conn.execute(
    "UPDATE milestones SET status = 'slipped' WHERE id = 'launch'"
  )
  db.conn.commit()
  assert compute_project_health(db) == HEALTH_AT_RISK


def test_incomplete_critical_path_near_deadline_is_at_risk(db: SimDatabase) -> None:
  _insert_cp_task(db, "PROJ-17", "in_progress")
  set_sim_time(db, datetime(2026, 6, 25, 10, 0))  # <48h to Fri 6 PM launch
  assert compute_project_health(db) == HEALTH_AT_RISK


def test_all_clear_is_on_track(db: SimDatabase) -> None:
  _insert_cp_task(db, "PROJ-17", "done")
  _insert_cp_task(db, "PROJ-22", "done")
  _insert_cp_task(db, "PROJ-30", "done")
  assert compute_project_health(db) == HEALTH_ON_TRACK
