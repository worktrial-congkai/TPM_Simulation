"""Unit tests for rubric condition evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pm_sim.agent.conditions import OAUTH_BLOCKER_KEY
from pm_sim.eval.conditions import evaluate_rubric_condition
from pm_sim.eval.context import ActionLogEntry, EvalContext
from pm_sim.sim.clock import parse_sim_time


def test_blockers_known_includes() -> None:
  ctx = EvalContext(
    run_id="r",
    scenario_id="first-week-pm",
    agent_id="triage_first",
    status="completed",
    start_time=parse_sim_time("2026-06-22T09:00:00"),
    end_sim_time=parse_sim_time("2026-06-22T09:00:00"),
    world_exec_id="exec",
    launch_slipped_days=0,
    actions=[],
    action_counts={},
    blockers_known=["PROJ-17_oauth_scope"],
    tradeoff_documented=False,
    docs=[],
    milestones=[],
    tasks=[],
    project_health="ON_TRACK",
  )
  assert evaluate_rubric_condition(
    "agent_state.blockers_known includes 'PROJ-17_oauth_scope'",
    ctx,
  )


def test_action_count_chat_send() -> None:
  ctx = EvalContext(
    run_id="r",
    scenario_id="first-week-pm",
    agent_id="triage_first",
    status="completed",
    start_time=parse_sim_time("2026-06-22T09:00:00"),
    end_sim_time=parse_sim_time("2026-06-22T09:00:00"),
    world_exec_id="exec",
    launch_slipped_days=0,
    actions=[
      ActionLogEntry(i, "2026-06-22T09:00:00", "chat_send", {}, None)
      for i in range(1, 32)
    ],
    action_counts={"chat_send": 31},
    blockers_known=[],
    tradeoff_documented=False,
    docs=[],
    milestones=[],
    tasks=[],
    project_health="AT_RISK",
  )
  assert evaluate_rubric_condition(
    "action_count.chat_send > 30 AND blockers_known.count < 1",
    ctx,
  )


def test_email_send_to_exec() -> None:
  ctx = EvalContext(
    run_id="r",
    scenario_id="first-week-pm",
    agent_id="triage_first",
    status="completed",
    start_time=parse_sim_time("2026-06-22T09:00:00"),
    end_sim_time=parse_sim_time("2026-06-22T09:00:00"),
    world_exec_id="exec",
    launch_slipped_days=0,
    actions=[
      ActionLogEntry(
        1,
        "2026-06-22T10:00:00",
        "email_send",
        {"to": "exec", "topic": "status_update"},
        {},
      )
    ],
    action_counts={"email_send": 1},
    blockers_known=[],
    tradeoff_documented=False,
    docs=[],
    milestones=[],
    tasks=[],
    project_health="ON_TRACK",
  )
  assert evaluate_rubric_condition("action_log contains email_send to exec", ctx)


def test_meeting_with_sam_alex() -> None:
  ctx = EvalContext(
    run_id="r",
    scenario_id="first-week-pm",
    agent_id="triage_first",
    status="completed",
    start_time=parse_sim_time("2026-06-22T09:00:00"),
    end_sim_time=parse_sim_time("2026-06-22T09:00:00"),
    world_exec_id="exec",
    launch_slipped_days=0,
    actions=[
      ActionLogEntry(
        1,
        "2026-06-22T10:00:00",
        "calendar_schedule",
        {"attendee_ids": ["agent", "sam", "alex"]},
        {},
      )
    ],
    action_counts={"calendar_schedule": 1},
    blockers_known=[],
    tradeoff_documented=False,
    docs=[],
    milestones=[],
    tasks=[],
    project_health="ON_TRACK",
    check_times={"meeting_sam_alex": "2026-06-22T10:00:00"},
  )
  assert evaluate_rubric_condition(
    "action_log contains meeting with [sam, alex]",
    ctx,
  )


def test_tasks_list_before_spam() -> None:
  ctx = EvalContext(
    run_id="r",
    scenario_id="first-week-pm",
    agent_id="triage_first",
    status="completed",
    start_time=parse_sim_time("2026-06-22T09:00:00"),
    end_sim_time=parse_sim_time("2026-06-22T09:00:00"),
    world_exec_id="exec",
    launch_slipped_days=0,
    actions=[],
    action_counts={},
    blockers_known=[],
    tradeoff_documented=False,
    docs=[],
    milestones=[],
    tasks=[],
    project_health="ON_TRACK",
    check_times={
      "tasks_list": "2026-06-22T09:00:00",
      "chat_send_gt_10": "2026-06-22T11:00:00",
    },
  )
  assert evaluate_rubric_condition(
    "action_log tasks_list before action_count.chat_send > 10",
    ctx,
  )


def test_decision_log_options() -> None:
  ctx = EvalContext(
    run_id="r",
    scenario_id="first-week-pm",
    agent_id="triage_first",
    status="completed",
    start_time=parse_sim_time("2026-06-22T09:00:00"),
    end_sim_time=parse_sim_time("2026-06-22T09:00:00"),
    world_exec_id="exec",
    launch_slipped_days=0,
    actions=[],
    action_counts={},
    blockers_known=[],
    tradeoff_documented=True,
    docs=[{"doc_type": "decision-log", "body": "Options: cut scope"}],
    milestones=[],
    tasks=[],
    project_health="ON_TRACK",
  )
  assert evaluate_rubric_condition(
    "docs contains decision-log with options listed",
    ctx,
  )
