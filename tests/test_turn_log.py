"""Tests for turn log formatting."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from pm_sim.agent.observation import build_observation
from pm_sim.agent.policies import load_scenario_agent
from pm_sim.agent.state import set_flag
from pm_sim.agent.turn import action_to_event, plan_agent_turn
from pm_sim.agent.types import AgentAction
from pm_sim.agent.world import world_config_from_meta
from pm_sim.display.turn_log import (
  format_action_label,
  format_observation_line,
  format_result_line,
  format_turn_block,
)
from pm_sim.sim.clock import get_sim_time, parse_sim_time
from pm_sim.sim.events import SimEvent, insert_event
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.runs import create_run
from pm_sim.sim.turns import execute_tool_turn, execute_wait_turn


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  create_run(database, scenario_id="first-week-pm", agent_id="triage_first", base=tmp_path / "runs")
  yield database
  database.close()


def test_observation_hides_blocker_cause_when_resolved(db) -> None:
  from pm_sim.agent.state import add_to_set

  add_to_set(db, "blockers_known", "PROJ-17_oauth_scope")
  db.conn.execute(
    """
    UPDATE tasks
    SET status = 'in_progress', blocker_reason = NULL
    WHERE id = 'PROJ-17'
    """
  )
  db.conn.execute(
    """
    UPDATE tasks
    SET status = 'todo', blocker_reason = NULL
    WHERE id = 'PROJ-22'
    """
  )
  db.conn.commit()
  obs = build_observation(db)
  line = format_observation_line(obs, db, "ON_TRACK")
  assert "blockers: none" in line
  assert "blocker cause:" not in line


def test_action_label_start_next_critical_task_includes_task_name(db) -> None:
  action = AgentAction(
    type="tool",
    name="start_next_critical_task",
    payload={"action": "tasks_update", "task_id": "PROJ-22", "status": "in_progress"},
  )
  label = format_action_label(action, db)
  assert "task start → PROJ-22 (Design sign-off)" in label
  assert "start_next_critical_task" in label


def test_result_docs_write_omits_redundant_agent_event(db) -> None:
  from pm_sim.sim.handlers.agent.handlers import handle_agent_docs_write

  db.set_meta("current_turn", "14")
  event = SimEvent.create(
    event_type="agent.docs_write",
    start_ts=get_sim_time(db),
    source="test",
    payload={
      "action": "docs_write",
      "title": "Launch tradeoff decision",
      "body": "Options listed",
      "doc_type": "decision-log",
    },
  )
  handle_agent_docs_write(event, db)
  action = AgentAction(type="tool", name="write_decision_doc")
  result = format_result_line(
    action,
    db=db,
    turn=14,
    processed_event_ids=[event.id],
    minutes_advanced=10,
  )
  assert "SIM: +10min" in result
  assert "doc written: Launch tradeoff decision" in result
  assert "events: docs_write" not in result


def test_result_tasks_update_shows_task_name(db) -> None:
  from pm_sim.sim.handlers.agent.handlers import handle_agent_tasks_update

  db.conn.execute("UPDATE tasks SET status = 'done' WHERE id = 'PROJ-17'")
  db.conn.execute(
    """
    UPDATE tasks
    SET status = 'todo', blocker_reason = NULL
    WHERE id = 'PROJ-22'
    """
  )
  db.conn.commit()
  db.set_meta("current_turn", "20")
  event = SimEvent.create(
    event_type="agent.tasks_update",
    start_ts=get_sim_time(db),
    source="test",
    payload={
      "action": "tasks_update",
      "task_id": "PROJ-22",
      "status": "in_progress",
    },
  )
  handle_agent_tasks_update(event, db)
  action = AgentAction(
    type="tool",
    name="start_next_critical_task",
    payload={"action": "tasks_update", "task_id": "PROJ-22", "status": "in_progress"},
  )
  result = format_result_line(action, db=db, turn=20, minutes_advanced=1)
  assert "task started: PROJ-22 (Design sign-off)" in result
  assert "events: tasks_update" not in result


def test_observation_includes_blocker_and_awaiting(db) -> None:
  set_flag(db, "tasks_checked", True)
  reply_at = get_sim_time(db) + timedelta(minutes=45)
  insert_event(
    db,
    SimEvent.create(
      event_type="npc.reply",
      start_ts=reply_at,
      source="test",
      actor_id="alex",
      payload={"coworker_id": "alex", "channel": "dm:alex", "action": "ack"},
    ),
  )
  obs = build_observation(db)
  line = format_observation_line(obs, db, "BLOCKED")
  assert "blocker cause: undiscovered" in line
  assert "PROJ-17 (API integration)" in line
  assert "PROJ-22 (Design sign-off)" in line
  assert "tasks: checked" not in line
  assert "awaiting: alex" in line
  assert "health: BLOCKED" in line


def test_result_tasks_list_shows_blocked_tasks(db) -> None:
  set_flag(db, "tasks_checked", True)
  db.set_meta("current_turn", "1")
  from pm_sim.sim.handlers.agent.handlers import handle_agent_tasks_list

  event = SimEvent.create(
    event_type="agent.tasks_list",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "tasks_list"},
  )
  handle_agent_tasks_list(event, db)
  action = AgentAction(type="tool", name="tasks_list")
  result = format_result_line(action, db=db, turn=1, minutes_advanced=2)
  assert "SIM: +2min" in result
  assert "PROJ-17 blocked" in result
  assert "integration issue" in result


def test_result_chat_send_shows_scheduled_reply(db) -> None:
  db.set_meta("current_turn", "2")
  spec = load_scenario_agent("first-week-pm", "triage_first")
  world = world_config_from_meta(db)
  set_flag(db, "tasks_checked", True)
  action = plan_agent_turn(db, spec, world=world)
  event = action_to_event(action, db)
  assert event is not None
  execute_tool_turn(db, event, minutes=3)
  result = format_result_line(action, db=db, turn=2, minutes_advanced=3)
  assert "SIM: +3min" in result
  assert "sent:" in result
  assert "blocking" in result
  assert "Reply scheduled" in result or "reply ~" in result
  assert "alex" in result


def test_result_wait_shows_named_events(db) -> None:
  reply_at = get_sim_time(db) + timedelta(minutes=1)
  event = SimEvent.create(
    event_type="npc.reply",
    start_ts=reply_at,
    source="test",
    actor_id="alex",
    payload={"coworker_id": "alex", "channel": "dm:alex", "action": "ack", "body": "OAuth scope issue"},
  )
  insert_event(db, event)
  wait_result = execute_wait_turn(db)
  action = AgentAction(type="wait", name="wait")
  result = format_result_line(
    action,
    db=db,
    processed_event_ids=wait_result.processed_event_ids,
    health=wait_result.health,
    minutes_advanced=wait_result.minutes_advanced,
  )
  assert "SIM: +1min" in result
  assert 'alex reply: "OAuth scope issue"' in result


def test_action_label_includes_chat_send_body() -> None:
  action = AgentAction(
    type="tool",
    name="ask_blocker_owner_dm",
    payload={
      "to": "alex",
      "body": "What's blocking the critical path task?",
    },
  )
  label = format_action_label(action)
  assert "chat send → alex:" in label
  assert "blocking" in label
  assert "ask_blocker_owner_dm" in label


def test_action_label_tasks_list_includes_all_tasks(db) -> None:
  action = AgentAction(type="tool", name="tasks_list", payload={"action": "tasks_list"})
  label = format_action_label(action, db)
  assert "tasks list →" in label
  assert "PROJ-17 (API integration)" in label
  assert "PROJ-22 (Design sign-off)" in label
  assert "PROJ-30 (QA)" in label


def test_action_label_email_send_includes_content() -> None:
  action = AgentAction(
    type="tool",
    name="escalate_vendor",
    payload={
      "to": "vendor_api",
      "subject": "OAuth scope escalation",
      "body": "Please approve extended OAuth read scope for PROJ-17.",
    },
  )
  label = format_action_label(action)
  assert "email send → vendor_api" in label
  assert "OAuth scope escalation" in label
  assert "Please approve" in label


def test_action_label_calendar_schedule_includes_title() -> None:
  action = AgentAction(
    type="tool",
    name="schedule_requirements_meeting",
    payload={"title": "Requirements review"},
  )
  label = format_action_label(action)
  assert "calendar schedule →" in label
  assert "Requirements review" in label


def test_action_label_read_email_includes_subject(db) -> None:
  action = AgentAction(
    type="tool",
    name="read_email",
    payload={"email_id": "email-001"},
  )
  label = format_action_label(action, db)
  assert "email read →" in label
  assert "Scope question" in label


def test_result_chat_read_shows_incoming_sender_and_body(db) -> None:
  db.set_meta("current_turn", "3")
  from pm_sim.sim.handlers.agent.handlers import handle_agent_chat_read

  event = SimEvent.create(
    event_type="agent.chat_read",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "chat_read", "channel": "dm:alex"},
  )
  handle_agent_chat_read(event, db)
  action = AgentAction(
    type="tool",
    name="read_dm",
    payload={"channel": "dm:alex"},
  )
  result = format_result_line(action, db=db, turn=3, minutes_advanced=2)
  assert "read from alex:" in result
  assert "PROJ-17" in result
  assert "message(s) read" not in result


def test_turn_block_end_to_end(db) -> None:
  start_time = parse_sim_time(db.get_meta("start_time"))
  obs = build_observation(db)
  action = AgentAction(type="tool", name="tasks_list", payload={"action": "tasks_list"})
  db.set_meta("current_turn", "1")
  from pm_sim.sim.handlers.agent.handlers import handle_agent_tasks_list

  event = SimEvent.create(
    event_type="agent.tasks_list",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "tasks_list"},
  )
  handle_agent_tasks_list(event, db)
  block = format_turn_block(
    1,
    obs,
    action,
    db,
    start_time=start_time,
    health="BLOCKED",
    processed_event_ids=[event.id],
  )
  assert "[Turn 1," in block
  assert "OBSERVE:" in block
  assert "ACTION:   tasks list →" in block
  assert "PROJ-17 (API integration)" in block
  assert "PROJ-17 blocked" in block


def test_tool_turn_advances_clock(db) -> None:
  from pm_sim.sim.handlers.agent.handlers import handle_agent_tasks_list

  start = get_sim_time(db)
  event = SimEvent.create(
    event_type="agent.tasks_list",
    start_ts=start,
    source="test",
    payload={"action": "tasks_list"},
  )
  result = execute_tool_turn(db, event, minutes=2)
  assert get_sim_time(db) == start + timedelta(minutes=2)
  assert result.minutes_advanced == 2


def test_run_loop_observation_time_advances_after_tool_turn(db, tmp_path: Path) -> None:
  from pm_sim.sim.run_loop import RunConfig, run_simulation

  spec = load_scenario_agent("first-week-pm", "triage_first")
  world = world_config_from_meta(db)
  config = RunConfig(
    scenario_id="first-week-pm",
    agent_id="triage_first",
    max_turns=2,
    quiet=True,
    artifact_root=tmp_path / "runs",
  )
  run_simulation(db, spec, world=world, config=config)
  log_path = next((tmp_path / "runs").glob("*/turn.log"))
  text = log_path.read_text(encoding="utf-8")
  assert "[Turn 1, Mon 9:00 AM, Day 1]" in text
  assert "[Turn 2, Mon 9:02 AM, Day 1]" in text
