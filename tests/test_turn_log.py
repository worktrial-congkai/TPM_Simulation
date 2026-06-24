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
  format_world_event_block,
)
from pm_sim.sim.handlers.meeting_end import handle_meeting_end
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
  line = format_observation_line(obs)
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


def test_observation_shows_stakeholder_conflict_when_both_emails_read(db) -> None:
  db.conn.execute("UPDATE emails SET read_by_agent = 1")
  db.conn.commit()
  obs = build_observation(db)
  line = format_observation_line(obs)
  assert "stakeholder conflict:" in line
  assert "Jordan Lee (customer success):" in line
  assert "Scope question on launch feature" in line
  assert "Sam Rivera (product):" in line
  assert "Launch date pressure" in line
  assert " vs " in line


def test_observation_shows_stakeholder_conflict_even_when_tradeoff_documented(db) -> None:
  db.conn.execute("UPDATE emails SET read_by_agent = 1")
  set_flag(db, "tradeoff_documented", True)
  db.conn.commit()
  obs = build_observation(db)
  line = format_observation_line(obs)
  assert "stakeholder conflict:" in line
  assert "Jordan Lee" in line
  assert "Sam Rivera" in line


def test_observation_shows_stakeholder_conflict_after_tradeoff_meeting_scheduled(db) -> None:
  db.conn.execute("UPDATE emails SET read_by_agent = 1")
  set_flag(db, "tradeoff_meeting_scheduled", True)
  db.conn.commit()
  obs = build_observation(db)
  line = format_observation_line(obs)
  assert "stakeholder conflict:" in line
  assert "Jordan Lee" in line
  assert "Sam Rivera" in line


def test_observation_hides_stakeholder_conflict_after_tradeoff_meeting_held(db) -> None:
  db.conn.execute("UPDATE emails SET read_by_agent = 1")
  set_flag(db, "tradeoff_meeting_scheduled", True)
  set_flag(db, "tradeoff_meeting_held", True)
  db.conn.commit()
  obs = build_observation(db)
  line = format_observation_line(obs)
  assert "stakeholder conflict:" not in line


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
  line = format_observation_line(obs)
  assert "chat unread: alex:1, sam:2, eng-launch:2" in line
  assert "blocker cause: undiscovered" in line
  assert "PROJ-17 (API integration)" in line
  assert "PROJ-22 (Design sign-off)" in line
  assert "tasks: checked" not in line
  assert "awaiting: reply from alex (dm)" in line
  assert "~" not in line.split("awaiting:")[1].split("|")[0]
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


def test_mid_turn_world_event_prints_to_stdout(db, tmp_path: Path) -> None:
  from io import StringIO

  from rich.console import Console

  from pm_sim.display.turn_stdout import TurnStdoutRenderer
  from pm_sim.sim.run_loop import RunConfig, run_simulation

  buffer = StringIO()
  renderer = TurnStdoutRenderer(Console(file=buffer, force_terminal=True, width=120))
  spec = load_scenario_agent("first-week-pm", "triage_first")
  world = world_config_from_meta(db)
  result = run_simulation(
    db,
    spec,
    world=world,
    config=RunConfig(
      scenario_id="first-week-pm",
      agent_id="triage_first",
      max_turns=5,
      quiet=True,
      artifact_root=tmp_path / "runs",
    ),
    on_turn=renderer.emit,
  )
  renderer.close()
  output = buffer.getvalue()
  log_text = (result.artifact_dir / "turn.log").read_text(encoding="utf-8")
  assert "[WORLD, Mon 9:52 AM, Day 1]" in log_text
  assert "[WORLD, Mon 9:52 AM, Day 1]" in output


def test_action_label_includes_chat_send_body(db) -> None:
  action = AgentAction(
    type="tool",
    name="ask_blocker_owner_dm",
    payload={
      "to": "alex",
      "task_id": "PROJ-17",
      "body": "What's blocking the critical path task?",
    },
  )
  label = format_action_label(action, db)
  assert "chat send → alex re PROJ-17 (API integration):" in label
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


def test_action_label_calendar_schedule_includes_title(db) -> None:
  action = AgentAction(
    type="tool",
    name="schedule_requirements_meeting",
    payload={"title": "Requirements review", "task_id": "PROJ-22"},
  )
  label = format_action_label(action, db)
  assert "calendar schedule →" in label
  assert "Requirements review" in label
  assert "re PROJ-22 (Design sign-off)" in label


def test_action_label_read_email_includes_subject(db) -> None:
  action = AgentAction(
    type="tool",
    name="read_email",
    payload={"email_id": "email-001"},
  )
  label = format_action_label(action, db)
  assert "email read →" in label
  assert "Scope question" in label


def test_result_email_read_shows_sender_and_subject(db) -> None:
  db.set_meta("current_turn", "5")
  from pm_sim.sim.handlers.agent.handlers import handle_agent_email_read

  event = SimEvent.create(
    event_type="agent.email_read",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "email_read", "email_id": "email-001"},
  )
  handle_agent_email_read(event, db)
  action = AgentAction(
    type="tool",
    name="read_email",
    payload={"email_id": "email-001"},
  )
  result = format_result_line(action, db=db, turn=5, minutes_advanced=37)
  assert "from jordan:" in result.lower()
  assert "Scope question" in result
  assert "email(s) read" not in result


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
  assert "OAuth scope disclosed" not in result


def test_result_chat_read_lists_all_incoming_messages(db) -> None:
  db.conn.execute(
    """
    INSERT INTO chat_messages (id, channel, sender_id, body, sent_at, read_by_agent)
    VALUES ('msg-sam-reply', 'dm:sam', 'sam', 'Got it, thanks.', '2026-06-22T10:55:00', 0)
    """
  )
  db.conn.commit()
  db.set_meta("current_turn", "12")
  from pm_sim.sim.handlers.agent.handlers import handle_agent_chat_read

  event = SimEvent.create(
    event_type="agent.chat_read",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "chat_read", "channel": "dm:sam"},
  )
  handle_agent_chat_read(event, db)
  action = AgentAction(
    type="tool",
    name="read_dm",
    payload={"channel": "dm:sam"},
  )
  result = format_result_line(action, db=db, turn=12, minutes_advanced=12)
  assert result.count("read from sam:") == 3
  assert "requirements sync" in result
  assert "product review deck" in result
  assert "Got it, thanks." in result
  assert "OAuth scope disclosed" not in result


def test_result_chat_read_shows_oauth_disclosure_only_when_read_discovers_blocker(db) -> None:
  from pm_sim.sim.handlers.agent.handlers import handle_agent_chat_read

  db.conn.execute(
    """
    INSERT INTO chat_messages (id, channel, sender_id, body, sent_at, read_by_agent)
    VALUES (
      'msg-oauth',
      'dm:alex',
      'alex',
      'The blocker is an OAuth scope mismatch on the vendor API.',
      '2026-06-22T09:52:00',
      0
    )
    """
  )
  db.conn.commit()
  db.set_meta("current_turn", "6")
  read = SimEvent.create(
    event_type="agent.chat_read",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "chat_read", "channel": "dm:alex"},
  )
  handle_agent_chat_read(read, db)
  action = AgentAction(type="tool", name="read_dm", payload={"channel": "dm:alex"})
  result = format_result_line(action, db=db, turn=6, minutes_advanced=12)
  assert "read from alex:" in result
  assert "OAuth" in result
  assert "OAuth scope disclosed → blocker_known" in result


def test_result_chat_read_omits_oauth_disclosure_when_blocker_already_known(db) -> None:
  from pm_sim.sim.handlers.agent.handlers import handle_agent_chat_read

  set_flag(db, "blockers_known", ["PROJ-17_oauth_scope"])
  db.conn.execute(
    """
    INSERT INTO chat_messages (id, channel, sender_id, body, sent_at, read_by_agent)
    VALUES ('msg-sam-later', 'dm:sam', 'sam', 'Follow-up ping.', '2026-06-22T11:00:00', 0)
    """
  )
  db.conn.commit()
  db.set_meta("current_turn", "12")
  read_sam = SimEvent.create(
    event_type="agent.chat_read",
    start_ts=get_sim_time(db),
    source="test",
    payload={"action": "chat_read", "channel": "dm:sam"},
  )
  handle_agent_chat_read(read_sam, db)
  sam_action = AgentAction(type="tool", name="read_dm", payload={"channel": "dm:sam"})
  sam_result = format_result_line(sam_action, db=db, turn=12, minutes_advanced=12)
  assert "read from sam:" in sam_result
  assert "OAuth scope disclosed" not in sam_result


def test_turn_block_includes_why_line(db) -> None:
  set_flag(db, "tasks_checked", True)
  spec = load_scenario_agent("first-week-pm", "triage_first")
  world = world_config_from_meta(db)
  obs = build_observation(db)
  action = plan_agent_turn(db, spec, world=world)
  start_time = parse_sim_time(db.get_meta("start_time"))
  block = format_turn_block(2, obs, action, db, start_time=start_time, health="BLOCKED")
  assert "WHY:      blocker_unknown AND NOT waiting_on_reply → ask_blocker_owner_dm" in block
  assert block.index("ACTION:") < block.index("WHY:")
  assert block.index("WHY:") < block.index("RESULT:")


def test_turn_block_end_to_end(db) -> None:
  start_time = parse_sim_time(db.get_meta("start_time"))
  obs = build_observation(db)
  action = AgentAction(
    type="tool",
    name="tasks_list",
    payload={"action": "tasks_list"},
    policy_condition="NOT tasks_checked",
  )
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
  assert "WHY:      NOT tasks_checked → tasks_list" in block
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


def test_world_event_meeting_end_shows_proj22_unblocked(db) -> None:
  start_time = parse_sim_time(db.get_meta("start_time"))
  end_event = SimEvent.create(
    event_type="meeting.end",
    start_ts=parse_sim_time("2026-06-22T12:00:00"),
    source="test",
    payload={"meeting_id": "req-meeting", "meeting_type": "requirements"},
  )
  insert_event(db, end_event)
  db.conn.execute(
    """
    INSERT INTO meetings (
      id, title, start_at, end_at, attendee_ids, meeting_type, transcript, completed
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
      "req-meeting",
      "Requirements review",
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

  block = format_world_event_block(end_event.id, db, start_time=start_time)
  assert block is not None
  assert "Requirements review ended" in block
  assert "PROJ-22 (Design sign-off) unblocked" in block


def test_observation_line_uses_turn_start_snapshot(db) -> None:
  obs = build_observation(db)
  db.conn.execute(
    """
    UPDATE tasks
    SET status = 'in_progress', blocker_reason = NULL
    WHERE id = 'PROJ-17'
    """
  )
  db.conn.commit()
  line = format_observation_line(obs)
  assert "PROJ-17 (API integration)" in line
  assert "health: BLOCKED" in line


def test_turn_block_shows_post_wait_health_in_result_not_observe(db) -> None:
  from pm_sim.agent.state import add_to_set

  add_to_set(db, "blockers_known", "PROJ-17_oauth_scope")
  obs = build_observation(db)
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
  action = AgentAction(type="wait", name="wait")
  block = format_turn_block(
    99,
    obs,
    action,
    db,
    start_time=parse_sim_time(db.get_meta("start_time")),
    health="AT_RISK",
    minutes_advanced=1,
  )
  assert "PROJ-17 (API integration)" in block
  assert "health: BLOCKED" in block.split("RESULT:")[0]
  assert "health: AT_RISK" in block


def test_world_event_vendor_turnaround_shows_proj17_unblocked(db) -> None:
  from pm_sim.sim.handlers.vendor_turnaround import handle_vendor_turnaround

  start_time = parse_sim_time(db.get_meta("start_time"))
  event = SimEvent.create(
    event_type="vendor.turnaround_complete",
    start_ts=parse_sim_time("2026-06-23T10:11:00"),
    source="test",
    payload={"task_id": "PROJ-17"},
  )
  insert_event(db, event)
  handle_vendor_turnaround(event, db)
  block = format_world_event_block(event.id, db, start_time=start_time)
  assert block is not None
  assert "vendor turnaround complete" in block
  assert "PROJ-17 (API integration) unblocked" in block


def test_world_event_drift_no_slip_when_blocker_resolved(db) -> None:
  from pm_sim.sim.handlers.milestone_drift import handle_milestone_drift

  start_time = parse_sim_time(db.get_meta("start_time"))
  db.conn.execute(
    "UPDATE tasks SET status = 'in_progress', blocker_reason = NULL WHERE id = 'PROJ-17'"
  )
  db.conn.commit()
  event = SimEvent.create(
    event_type="milestone.drift",
    start_ts=parse_sim_time("2026-06-23T18:00:00"),
    source="test",
    payload={"task_id": "PROJ-17", "milestone_id": "launch", "slip_days": 1},
  )
  insert_event(db, event)
  handle_milestone_drift(event, db)
  block = format_world_event_block(event.id, db, start_time=start_time)
  assert block is not None
  assert "no launch slip — launch date unchanged (blocker resolved)" in block


def test_world_event_drift_slips_when_blocker_open(db) -> None:
  from pm_sim.sim.handlers.milestone_drift import handle_milestone_drift

  start_time = parse_sim_time(db.get_meta("start_time"))
  event = SimEvent.create(
    event_type="milestone.drift",
    start_ts=parse_sim_time("2026-06-23T18:00:00"),
    source="test",
    payload={"task_id": "PROJ-17", "milestone_id": "launch", "slip_days": 1},
  )
  insert_event(db, event)
  handle_milestone_drift(event, db)
  block = format_world_event_block(event.id, db, start_time=start_time)
  assert block is not None
  assert "launch slipped +1d — PROJ-17 still blocked" in block


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
