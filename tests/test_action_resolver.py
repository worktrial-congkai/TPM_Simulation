"""Tests for semantic action resolver."""

from pathlib import Path

import pytest

from pm_sim.agent.actions import resolve_action
from pm_sim.agent.observation import build_observation
from pm_sim.agent.types import WorldConfig
from pm_sim.sim.reset import reset_scenario


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


@pytest.fixture
def world() -> WorldConfig:
  return WorldConfig(vendor_id="vendor_api", exec_id="exec")


def test_ask_blocker_owner_dm(db, world) -> None:
  obs = build_observation(db)
  action = resolve_action("ask_blocker_owner_dm", obs, db, world=world)
  assert action.event_type == "agent.chat_send"
  assert action.payload["to"] == "alex"
  assert action.payload["task_id"] == "PROJ-17"
  assert action.payload["topic"] == "blocker_status"


def test_escalate_vendor(db, world) -> None:
  obs = build_observation(db)
  action = resolve_action("escalate_vendor", obs, db, world=world)
  assert action.event_type == "agent.email_send"
  assert action.payload["to"] == "vendor_api"
  assert action.payload["topic"] == "vendor_escalation"


def test_schedule_requirements_meeting_targets_proj22(db, world) -> None:
  obs = build_observation(db)
  action = resolve_action("schedule_requirements_meeting", obs, db, world=world)
  assert action.event_type == "agent.calendar_schedule"
  assert action.payload["task_id"] == "PROJ-22"
  assert action.payload["meeting_type"] == "requirements"


def test_start_next_critical_task_targets_proj22(db, world) -> None:
  db.conn.execute("UPDATE tasks SET status = 'done' WHERE id = 'PROJ-17'")
  db.conn.execute(
    """
    UPDATE tasks
    SET status = 'todo', blocker_reason = NULL
    WHERE id = 'PROJ-22'
    """
  )
  db.conn.commit()
  obs = build_observation(db)
  action = resolve_action("start_next_critical_task", obs, db, world=world)
  assert action.event_type == "agent.tasks_update"
  assert action.payload["task_id"] == "PROJ-22"
  assert action.payload["status"] == "in_progress"


def test_start_next_critical_task_targets_proj30(db, world) -> None:
  db.conn.execute("UPDATE tasks SET status = 'done' WHERE id IN ('PROJ-17', 'PROJ-22')")
  db.conn.commit()
  obs = build_observation(db)
  action = resolve_action("start_next_critical_task", obs, db, world=world)
  assert action.payload["task_id"] == "PROJ-30"
