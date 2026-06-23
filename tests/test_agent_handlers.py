"""Tests for agent event handlers."""

import json
from pathlib import Path

import pytest

from pm_sim.sim.clock import get_sim_time, set_sim_time
from pm_sim.sim.events import SimEvent, process_due_events
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.turns import execute_tool_turn


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_tasks_list_sets_tasks_checked(db) -> None:
  event = SimEvent.create(
    event_type="agent.tasks_list",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "tasks_list"},
  )
  execute_tool_turn(db, event)
  checked = json.loads(
    db.conn.execute(
      "SELECT value FROM agent_state WHERE key = 'tasks_checked'"
    ).fetchone()["value"]
  )
  assert checked is True


def test_chat_send_schedules_npc_reply_not_processed_same_turn(db) -> None:
  event = SimEvent.create(
    event_type="agent.chat_send",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "chat_send", "to": "alex", "body": "Status?"},
  )
  execute_tool_turn(db, event)

  before = db.conn.execute(
    "SELECT COUNT(*) AS c FROM chat_messages WHERE sender_id = 'alex'"
  ).fetchone()["c"]

  pending = db.conn.execute(
    "SELECT event_type, status FROM events WHERE event_type = 'npc.reply'"
  ).fetchone()
  assert pending is not None
  assert pending["status"] == "pending"

  after = db.conn.execute(
    "SELECT COUNT(*) AS c FROM chat_messages WHERE sender_id = 'alex'"
  ).fetchone()["c"]
  assert after == before


def test_npc_reply_processed_after_clock_advances(db) -> None:
  event = SimEvent.create(
    event_type="agent.chat_send",
    start_ts=get_sim_time(db),
    source="test",
    payload={
      "action": "chat_send",
      "to": "alex",
      "body": "What's the blocker?",
      "topic": "blocker_status",
    },
  )
  execute_tool_turn(db, event)

  pending = db.conn.execute(
    "SELECT start_ts FROM events WHERE event_type = 'npc.reply' AND status = 'pending'"
  ).fetchone()
  assert pending is not None
  from pm_sim.sim.clock import parse_sim_time

  set_sim_time(db, parse_sim_time(pending["start_ts"]))
  process_due_events(db)

  reply = db.conn.execute(
    """
    SELECT body FROM chat_messages
    WHERE sender_id = 'alex'
    ORDER BY sent_at DESC
    LIMIT 1
    """
  ).fetchone()
  assert reply is not None
  assert "OAuth" in reply["body"]

  blockers = json.loads(
    db.conn.execute(
      "SELECT value FROM agent_state WHERE key = 'blockers_known'"
    ).fetchone()["value"]
  )
  assert "PROJ-17_oauth_scope" in blockers
