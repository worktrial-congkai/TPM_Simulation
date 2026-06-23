"""Tests for interaction timeline formatting."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pm_sim.agent.action_log import log_action
from pm_sim.agent.policies import load_scenario_agent
from pm_sim.agent.world import world_config_from_meta
from pm_sim.display.interaction_timeline import (
  TimelineEntry,
  _agent_action_entries,
  build_interaction_timeline,
  collect_timeline_entries,
  format_interaction_timeline,
)
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.run_loop import RunConfig, run_simulation

SCENARIO = "first-week-pm"


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario(SCENARIO, db_path=tmp_path / "sim.db")
  yield database
  database.close()


def _seed_run(db, run_id: str = "test-run") -> None:
  db.set_meta("active_run_id", run_id)
  db.conn.execute(
    """
    INSERT INTO runs (id, scenario_id, agent_id, status, started_at, seed)
    VALUES (?, ?, ?, 'completed', '2026-06-22T09:00:00', 1)
    """,
    (run_id, SCENARIO, "triage_first"),
  )
  db.conn.commit()


@pytest.mark.slow
def test_timeline_includes_agent_and_coworker_events(db, tmp_path: Path) -> None:
  spec = load_scenario_agent(SCENARIO, "triage_first")
  world = world_config_from_meta(db)
  result = run_simulation(
    db,
    spec,
    world=world,
    config=RunConfig(
      scenario_id=SCENARIO,
      agent_id="triage_first",
      quiet=True,
      artifact_root=tmp_path / "runs",
    ),
  )

  text = build_interaction_timeline(db, result.run_id)
  assert "Interaction timeline" in text
  assert "agent ──► alex" in text
  assert "agent ──► morgan" in text
  assert "vendor_api" in text
  assert "OAuth" in text
  assert "launch complete" in text
  assert "world" not in text
  assert "Mon  9:00 AM" in text or "Mon 9:00 AM" in text
  assert "why        " in text
  assert "…" not in text
  assert (result.artifact_dir / "timeline.txt").exists()
  assert "Interaction timeline" in result.summary


def test_timeline_orders_by_sim_time(db, tmp_path: Path) -> None:
  spec = load_scenario_agent(SCENARIO, "triage_first")
  world = world_config_from_meta(db)
  result = run_simulation(
    db,
    spec,
    world=world,
    config=RunConfig(
      scenario_id=SCENARIO,
      agent_id="triage_first",
      max_turns=5,
      quiet=True,
      artifact_root=tmp_path / "runs",
    ),
  )

  entries = collect_timeline_entries(db, result.run_id)
  times = [e.sim_time for e in entries]
  assert times == sorted(times)


def test_timeline_row_includes_timestamp() -> None:
  start = datetime(2026, 6, 22, 9, 0)
  entries = [
    TimelineEntry(start, 1, "agent", "morgan", "PROJ-22 → in_progress"),
    TimelineEntry(datetime(2026, 6, 23, 10, 0), 2, "morgan", "agent", "PROJ-22 complete"),
  ]
  text = format_interaction_timeline(entries, start_time=start)
  assert "Mon" in text and "9:00 AM" in text
  assert "agent ──► morgan" in text
  assert "morgan" in text and "PROJ-22 complete" in text
  assert "── Day" not in text


def test_timeline_renders_full_message_without_truncation() -> None:
  long_body = (
    "PROJ-17 integration is still blocked — I'll share more on DM if needed."
  )
  entries = [
    TimelineEntry(
      datetime(2026, 6, 22, 9, 5),
      0,
      "alex",
      "agent",
      "reply",
      (("message", long_body),),
    ),
  ]
  text = format_interaction_timeline(entries, start_time=datetime(2026, 6, 22, 9, 0))
  assert long_body in text
  assert "…" not in text
  assert "message    " in text


def test_timeline_includes_policy_why_for_agent_action(db) -> None:
  _seed_run(db)
  db.set_meta("current_turn", "2")
  log_action(
    db,
    "policy_decision",
    {"condition": "blocker_unknown AND NOT waiting_on_reply", "action": "ask_blocker_owner_dm"},
  )
  log_action(
    db,
    "chat_send",
    {"to": "alex", "body": "What's blocking the critical path task?", "topic": "blocker_status"},
    {"id": "msg-1", "channel": "dm:alex"},
  )
  db.conn.commit()

  entries = collect_timeline_entries(db, "test-run")
  assert len(entries) == 1
  assert entries[0].details[0] == (
    "why",
    "blocker_unknown AND NOT waiting_on_reply → ask_blocker_owner_dm",
  )

  text = build_interaction_timeline(db, "test-run")
  assert "why        blocker_unknown AND NOT waiting_on_reply → ask_blocker_owner_dm" in text
  assert "topic      blocker_status" in text
  assert "message    What's blocking the critical path task?" in text


def test_timeline_email_read_shows_subject_and_body(db) -> None:
  _seed_run(db)
  db.set_meta("current_turn", "3")
  log_action(
    db,
    "policy_decision",
    {"condition": "unread_email", "action": "read_email"},
  )
  log_action(
    db,
    "email_read",
    {"email_id": "email-1"},
    {
      "id": "email-1",
      "sender_id": "sam",
      "subject": "Launch status check",
      "body": "Hearing rumors about a launch delay. Anyone know what's up?",
    },
  )
  db.conn.commit()

  entries = collect_timeline_entries(db, "test-run")
  assert len(entries) == 1
  assert entries[0].headline == "read email from sam"
  detail_keys = [key for key, _ in entries[0].details]
  assert detail_keys[:3] == ["why", "subject", "body"]

  text = build_interaction_timeline(db, "test-run")
  assert "subject    Launch status check" in text
  assert "body       Hearing rumors about a launch delay. Anyone know what's up?" in text


def test_agent_action_entries_email_read_from_result(db) -> None:
  entry = {
    "turn": 1,
    "sim_time": "2026-06-22T09:14:00",
    "action_type": "email_read",
    "payload": {"email_id": "email-1"},
    "result": {
      "sender_id": "sam",
      "subject": "Requirements sync",
      "body": "Can you join a requirements sync this week?",
    },
  }
  rows = _agent_action_entries(
    db,
    entry,
    policy={"condition": "unread_email", "action": "read_email"},
  )
  assert rows[0].target == "sam"
  assert ("subject", "Requirements sync") in rows[0].details
  assert ("body", "Can you join a requirements sync this week?") in rows[0].details
