"""Tests for task timer helpers."""

import json
from pathlib import Path

import pytest

from pm_sim.sim.db import SimDatabase
from pm_sim.sim.task_timers import dependencies_met, schedule_task_complete


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = SimDatabase(tmp_path / "test.db")
  database.init_schema()
  database.set_meta("sim_time", "2026-06-22T09:00:00")
  return database


def _insert_task(db: SimDatabase, **kwargs: object) -> None:
  defaults = {
    "id": "T1",
    "title": "Task",
    "status": "in_progress",
    "owner_id": "alex",
    "duration_minutes": 60,
    "blocker_reason": None,
    "critical_path": 0,
    "depends_on": "[]",
  }
  defaults.update(kwargs)
  db.conn.execute(
    """
    INSERT INTO tasks (
      id, title, status, owner_id, duration_minutes,
      blocker_reason, critical_path, depends_on
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
      defaults["id"], defaults["title"], defaults["status"], defaults["owner_id"],
      defaults["duration_minutes"], defaults["blocker_reason"],
      defaults["critical_path"], defaults["depends_on"],
    ),
  )
  db.conn.commit()


def test_dependencies_met_when_all_deps_done(db: SimDatabase) -> None:
  _insert_task(db, id="PROJ-17", status="done", depends_on="[]")
  _insert_task(
    db,
    id="PROJ-30",
    depends_on=json.dumps(["PROJ-17"]),
    duration_minutes=60,
  )
  assert dependencies_met(db, "PROJ-30") is True


def test_dependencies_not_met_when_dep_incomplete(db: SimDatabase) -> None:
  _insert_task(db, id="PROJ-17", status="in_progress", depends_on="[]")
  _insert_task(
    db,
    id="PROJ-30",
    depends_on=json.dumps(["PROJ-17", "PROJ-22"]),
    duration_minutes=60,
  )
  _insert_task(db, id="PROJ-22", status="todo", depends_on=json.dumps(["PROJ-17"]))
  assert dependencies_met(db, "PROJ-30") is False


def test_schedule_task_complete_uses_duration(db: SimDatabase) -> None:
  _insert_task(db, id="PROJ-30", duration_minutes=120)
  event = schedule_task_complete(db, "PROJ-30", source="test")
  assert event is not None
  assert event.event_type == "task.complete"
  assert event.start_ts.isoformat() == "2026-06-22T11:00:00"


def test_schedule_task_complete_returns_none_without_duration(db: SimDatabase) -> None:
  _insert_task(db, id="T1", duration_minutes=None)
  assert schedule_task_complete(db, "T1", source="test") is None
