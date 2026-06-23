"""Tests for NPC cooperation gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pm_sim.sim.clock import get_sim_time, set_sim_time
from pm_sim.sim.events import SimEvent, process_due_events
from pm_sim.sim.handlers.meeting_end import handle_meeting_end
from pm_sim.sim.handlers.npc_policy_scan import handle_npc_policy_scan
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.turns import execute_tool_turn


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def _drain_npc_replies(db) -> None:
  from pm_sim.sim.clock import parse_sim_time

  while True:
    pending = db.conn.execute(
      """
      SELECT start_ts FROM events
      WHERE event_type = 'npc.reply' AND status = 'pending'
      ORDER BY start_ts LIMIT 1
      """
    ).fetchone()
    if pending is None:
      return
    due = parse_sim_time(pending["start_ts"])
    if get_sim_time(db) < due:
      set_sim_time(db, due)
    process_due_events(db)


def test_dm_full_disclosure(db) -> None:
  event = SimEvent.create(
    event_type="agent.chat_send",
    start_ts=get_sim_time(db),
    source="test",
    payload={
      "action": "chat_send",
      "to": "alex",
      "body": "What's blocking PROJ-17?",
      "topic": "blocker_status",
    },
  )
  execute_tool_turn(db, event)
  _drain_npc_replies(db)

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


def test_channel_partial_disclosure(db) -> None:
  event = SimEvent.create(
    event_type="agent.chat_send",
    start_ts=get_sim_time(db),
    source="test",
    payload={
      "action": "chat_send",
      "to": "eng-launch",
      "body": "What's blocking PROJ-17?",
      "topic": "blocker_status",
    },
  )
  execute_tool_turn(db, event)
  _drain_npc_replies(db)

  reply = db.conn.execute(
    "SELECT body FROM chat_messages WHERE sender_id = 'alex'"
  ).fetchone()
  assert reply is not None
  assert "OAuth" not in reply["body"]

  blockers = json.loads(
    db.conn.execute(
      "SELECT value FROM agent_state WHERE key = 'blockers_known'"
    ).fetchone()["value"]
  )
  assert "PROJ-17_oauth_scope" not in blockers


def test_sam_soft_pushback_after_status_update(db) -> None:
  status = SimEvent.create(
    event_type="agent.email_send",
    start_ts=get_sim_time(db),
    source="test",
    payload={
      "action": "email_send",
      "to": "sam",
      "subject": "Status",
      "body": "Blocker update",
      "topic": "status_update",
    },
  )
  execute_tool_turn(db, status)

  delay = SimEvent.create(
    event_type="agent.email_send",
    start_ts=get_sim_time(db),
    source="test",
    payload={
      "action": "email_send",
      "to": "sam",
      "subject": "Delay?",
      "body": "Can we slip launch?",
      "topic": "launch_delay",
    },
  )
  execute_tool_turn(db, delay)
  _drain_npc_replies(db)

  replies = db.conn.execute(
    """
    SELECT body FROM chat_messages
    WHERE sender_id = 'sam'
    ORDER BY sent_at
    """
  ).fetchall()
  assert len(replies) >= 1
  assert any("mitigations" in row["body"].lower() for row in replies)


def test_jordan_proactive_dm(db) -> None:
  set_sim_time(db, get_sim_time(db).replace(day=24, hour=9, minute=0))
  scan = db.conn.execute(
    """
    SELECT id FROM events
    WHERE event_type = 'npc.policy_scan' AND status = 'pending'
    LIMIT 1
    """
  ).fetchone()
  assert scan is not None

  from pm_sim.sim.events import load_event

  event = load_event(db, scan["id"])
  handle_npc_policy_scan(event, db)
  db.conn.execute(
    "UPDATE events SET status = 'processed' WHERE id = ?",
    (scan["id"],),
  )
  db.conn.commit()

  dm = db.conn.execute(
    """
    SELECT body FROM chat_messages
    WHERE sender_id = 'jordan' AND channel = 'dm:jordan'
    """
  ).fetchone()
  assert dm is not None
  assert "Enterprise customer" in dm["body"]


def test_design_signoff_gate_unblocks_proj_22(db) -> None:
  end_event = SimEvent.create(
    event_type="meeting.end",
    start_ts=get_sim_time(db),
    source="test",
    payload={"meeting_id": "req-meeting", "meeting_type": "requirements"},
  )
  db.conn.execute(
    """
    INSERT INTO meetings (
      id, title, start_at, end_at, attendee_ids, meeting_type, transcript, completed
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
      "req-meeting",
      "Requirements sync",
      "2026-06-22T11:00:00",
      "2026-06-22T12:00:00",
      '["agent", "morgan"]',
      "requirements",
      "",
      0,
    ),
  )
  db.conn.commit()

  handle_meeting_end(end_event, db)

  task = db.conn.execute(
    "SELECT status, blocker_reason FROM tasks WHERE id = 'PROJ-22'"
  ).fetchone()
  assert task["status"] == "todo"
  assert task["blocker_reason"] is None
