"""Tests for policy condition evaluator."""

from pathlib import Path

import pytest

from pm_sim.agent.conditions import evaluate_condition
from pm_sim.agent.observation import build_observation
from pm_sim.agent.state import add_to_set, set_flag
from pm_sim.sim.reset import reset_scenario


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_not_tasks_checked(db) -> None:
  obs = build_observation(db)
  assert evaluate_condition("NOT tasks_checked", obs, db) is True
  set_flag(db, "tasks_checked", True)
  obs = build_observation(db)
  assert evaluate_condition("NOT tasks_checked", obs, db) is False


def test_blocker_unknown_and_known(db) -> None:
  obs = build_observation(db)
  assert evaluate_condition("blocker_unknown", obs, db) is True
  assert evaluate_condition("blocker_known", obs, db) is False

  add_to_set(db, "blockers_known", "PROJ-17_oauth_scope")
  obs = build_observation(db)
  assert evaluate_condition("blocker_known", obs, db) is True
  assert evaluate_condition("blocker_unknown", obs, db) is False


def test_blocker_known_and_not_vendor_escalated(db) -> None:
  add_to_set(db, "blockers_known", "PROJ-17_oauth_scope")
  obs = build_observation(db)
  assert evaluate_condition("blocker_known AND NOT vendor_escalated", obs, db) is True
  set_flag(db, "vendor_escalated", True)
  obs = build_observation(db)
  assert evaluate_condition("blocker_known AND NOT vendor_escalated", obs, db) is False


def test_no_urgent_items_when_inbox_clear_and_blocker_known(db) -> None:
  add_to_set(db, "blockers_known", "PROJ-17_oauth_scope")
  set_flag(db, "tradeoff_documented", True)
  db.conn.execute("UPDATE chat_messages SET read_by_agent = 1")
  db.conn.execute("UPDATE emails SET read_by_agent = 1")
  db.conn.commit()
  obs = build_observation(db)
  assert evaluate_condition("no_urgent_items", obs, db) is True


def test_critical_path_task_ready_when_proj22_unblocked(db) -> None:
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
  assert evaluate_condition("critical_path_task_ready", obs, db) is True


def test_critical_path_task_ready_false_when_deps_unmet(db) -> None:
  obs = build_observation(db)
  assert evaluate_condition("critical_path_task_ready", obs, db) is False
