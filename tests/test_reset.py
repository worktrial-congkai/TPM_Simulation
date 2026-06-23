"""Tests for scenario reset."""

import json
from pathlib import Path

import pytest

from pm_sim.sim.clock import get_sim_time
from pm_sim.sim.reset import reset_scenario


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
  return tmp_path / "sim.db"


def test_reset_creates_db_with_expected_state(db_path: Path) -> None:
  db = reset_scenario("first-week-pm", db_path=db_path)
  try:
    assert db_path.exists()
    assert get_sim_time(db).isoformat() == "2026-06-22T09:00:00"
    assert db.get_meta("scenario_id") == "first-week-pm"

    task = db.conn.execute(
      "SELECT status, blocker_reason FROM tasks WHERE id = 'PROJ-17'"
    ).fetchone()
    assert task["status"] == "blocked"
    assert task["blocker_reason"] == "integration issue"

    chat_count = db.conn.execute(
      "SELECT COUNT(*) AS c FROM chat_messages"
    ).fetchone()["c"]
    assert chat_count == 5

    policy_count = db.conn.execute(
      "SELECT COUNT(*) AS c FROM coworker_policies"
    ).fetchone()["c"]
    assert policy_count >= 1

    alex_policies = db.conn.execute(
      "SELECT template_id FROM coworker_policies WHERE coworker_id = 'alex'"
    ).fetchall()
    assert any(row["template_id"] == "eng_blocker_disclosure_full" for row in alex_policies)

    tasks_checked = json.loads(
      db.conn.execute(
        "SELECT value FROM agent_state WHERE key = 'tasks_checked'"
      ).fetchone()["value"]
    )
    assert tasks_checked is False

    pending_events = db.conn.execute(
      "SELECT COUNT(*) AS c FROM events WHERE status = 'pending'"
    ).fetchone()["c"]
    assert pending_events == 4

    event_types = {
      row["event_type"]
      for row in db.conn.execute(
        "SELECT event_type FROM events WHERE status = 'pending'"
      ).fetchall()
    }
    assert event_types == {"milestone.drift", "task.complete", "npc.policy_scan"}

    policy_scans = db.conn.execute(
      """
      SELECT start_ts FROM events
      WHERE event_type = 'npc.policy_scan' AND status = 'pending'
      ORDER BY start_ts
      """
    ).fetchall()
    assert len(policy_scans) == 2
    assert policy_scans[0]["start_ts"] == "2026-06-24T09:00:00"
    assert policy_scans[1]["start_ts"] == "2026-06-25T09:00:00"

    wiki_complete = db.conn.execute(
      """
      SELECT start_ts FROM events
      WHERE event_type = 'task.complete' AND json_extract(payload, '$.task_id') = 'PROJ-99'
      """
    ).fetchone()
    assert wiki_complete["start_ts"] == "2026-06-22T10:00:00"

    task_count = db.conn.execute(
      "SELECT COUNT(*) AS c FROM tasks"
    ).fetchone()["c"]
    assert task_count == 4

    milestone = db.conn.execute(
      "SELECT id FROM milestones WHERE id = 'launch'"
    ).fetchone()
    assert milestone is not None
  finally:
    db.close()
