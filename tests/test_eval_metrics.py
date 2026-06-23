"""Tests for extended run metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pm_sim.eval.metrics import compute_run_metrics
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.runs import create_run


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def _seed_run(db, run_id: str = "run-1") -> None:
  db.conn.execute(
    """
    INSERT INTO runs (id, scenario_id, agent_id, status, started_at, ended_at, seed)
    VALUES (?, 'first-week-pm', 'triage_first', 'completed', '2026-06-22T09:00:00', NULL, 42)
    """,
    (run_id,),
  )
  entries = [
    (1, "2026-06-22T09:00:00", "tasks_list", "{}", '{"count": 4}'),
    (2, "2026-06-22T09:05:00", "chat_send", '{"to": "alex", "topic": "blocker_status"}', "{}"),
    (3, "2026-06-22T10:00:00", "chat_read", '{"channel": "dm:alex"}', '{"count": 1}'),
    (
      4,
      "2026-06-22T10:30:00",
      "email_send",
      '{"to": "vendor_api", "topic": "vendor_escalation"}',
      "{}",
    ),
    (
      5,
      "2026-06-22T11:00:00",
      "docs_write",
      '{"doc_type": "decision-log", "body": "Options: delay"}',
      '{"id": "doc-1"}',
    ),
  ]
  for turn, sim_time, action_type, payload, result in entries:
    db.conn.execute(
      """
      INSERT INTO action_log (run_id, turn, sim_time, action_type, payload, result)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (run_id, turn, sim_time, action_type, payload, result),
    )
  db.conn.commit()


def test_extended_metrics_from_action_log(db) -> None:
  _seed_run(db)
  metrics = compute_run_metrics(db, "run-1")
  assert metrics.time_to_vendor_escalated == "2026-06-22T10:30:00"
  assert metrics.time_to_tradeoff_decision == "2026-06-22T11:00:00"
  assert metrics.total_turns == 5
  assert metrics.wait_turns == 0
  assert metrics.chat_tool_count == 2
  assert metrics.email_tool_count == 1
  assert metrics.meeting_tool_count == 0
  assert metrics.total_tool_count == 5


def test_metrics_with_create_run(db, tmp_path: Path) -> None:
  run_id, _ = create_run(db, scenario_id="first-week-pm", agent_id="triage_first", base=tmp_path)
  db.conn.execute(
    """
    INSERT INTO action_log (run_id, turn, sim_time, action_type, payload, result)
    VALUES (?, 1, '2026-06-22T09:00:00', 'wait', '{}', '{}')
    """,
    (run_id,),
  )
  db.conn.commit()
  metrics = compute_run_metrics(db, run_id)
  assert metrics.wait_turns == 1
