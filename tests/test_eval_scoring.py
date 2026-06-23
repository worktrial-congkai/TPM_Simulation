"""Tests for rubric scoring and evaluate_run."""

from __future__ import annotations

from pathlib import Path

import pytest

from pm_sim.agent.state import set_flag
from pm_sim.eval.context import ActionLogEntry, EvalContext, build_eval_context
from pm_sim.eval.report import evaluate_run
from pm_sim.eval.rubric import RubricCheck, load_rubric
from pm_sim.eval.scoring import _score_condition_fraction, _score_penalty_deduction, score_rubric
from pm_sim.sim.clock import parse_sim_time
from pm_sim.sim.reset import reset_scenario


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def _insert_run(db, run_id: str = "run-eval") -> str:
  db.conn.execute(
    """
    INSERT INTO runs (id, scenario_id, agent_id, status, started_at, ended_at, seed)
    VALUES (?, 'first-week-pm', 'triage_first', 'incomplete', '2026-06-22T09:00:00', NULL, 42)
    """,
    (run_id,),
  )
  db.conn.execute(
    """
    INSERT INTO action_log (run_id, turn, sim_time, action_type, payload, result)
    VALUES (?, 1, '2026-06-22T09:00:00', 'tasks_list', '{}', '{"count": 4}')
    """,
    (run_id,),
  )
  db.conn.commit()
  return run_id


def test_load_rubric_has_components() -> None:
  rubric = load_rubric("first-week-pm")
  ids = {c.id for c in rubric.components}
  assert "blocker_discovery" in ids
  assert "project_outcome" in ids
  assert "prioritization" not in ids


def test_rubric_weights_sum_to_one() -> None:
  rubric = load_rubric("first-week-pm")
  total = sum(c.weight for c in rubric.components)
  assert abs(total - 1.0) < 0.001


def test_incomplete_run_scores_project_outcome_zero(db) -> None:
  run_id = _insert_run(db)
  report = evaluate_run(db, run_id, "first-week-pm")
  outcome = next(c for c in report.rubric.components if c.component_id == "project_outcome")
  assert outcome.score == 0.0
  assert report.status == "incomplete"


def test_blocker_known_improves_score(db) -> None:
  run_id = _insert_run(db)
  set_flag(db, "blockers_known", ["PROJ-17_oauth_scope"])
  db.conn.execute(
    """
    INSERT INTO action_log (run_id, turn, sim_time, action_type, payload, result)
    VALUES (?, 2, '2026-06-22T10:00:00', 'chat_read', '{"channel": "dm:alex"}', '{}')
    """,
    (run_id,),
  )
  db.conn.commit()
  report = evaluate_run(db, run_id, "first-week-pm")
  blocker = next(c for c in report.rubric.components if c.component_id == "blocker_discovery")
  assert blocker.score > 0


def test_eval_determinism(db) -> None:
  run_id = _insert_run(db)
  r1 = evaluate_run(db, run_id, "first-week-pm")
  r2 = evaluate_run(db, run_id, "first-week-pm")
  assert r1.rubric.total == r2.rubric.total


def test_vendor_early_penalty(db) -> None:
  run_id = _insert_run(db)
  db.conn.execute(
    """
    INSERT INTO action_log (run_id, turn, sim_time, action_type, payload, result)
    VALUES (?, 2, '2026-06-22T09:01:00', 'email_send',
            '{"to": "vendor_api", "topic": "vendor_escalation"}', '{}')
    """,
    (run_id,),
  )
  db.conn.commit()
  ctx = build_eval_context(db, run_id)
  rubric = load_rubric("first-week-pm")
  scored = score_rubric(ctx, rubric)
  assert "vendor_escalated_before_blocker_known" in scored.penalties


def _ctx_with_blocker_at(sim_time: str) -> EvalContext:
  return EvalContext(
    run_id="r",
    scenario_id="first-week-pm",
    agent_id="triage_first",
    status="completed",
    start_time=parse_sim_time("2026-06-22T09:00:00"),
    end_sim_time=parse_sim_time(sim_time),
    world_exec_id="exec",
    launch_slipped_days=0,
    actions=[
      ActionLogEntry(1, sim_time, "chat_read", {"channel": "dm:alex"}, {}),
    ],
    action_counts={"chat_read": 1},
    blockers_known=["PROJ-17_oauth_scope"],
    tradeoff_documented=False,
    docs=[],
    milestones=[],
    tasks=[],
    project_health="ON_TRACK",
    check_times={"blocker_known": sim_time},
  )


def test_condition_fraction_full_credit_within_window() -> None:
  check = RubricCheck(
    id="found_api_blocker",
    condition="agent_state.blockers_known includes 'PROJ-17_oauth_scope'",
    deadline="sim_day 1",
    full_credit_within_minutes=30,
    decay_minutes=60,
    on_time_floor=0.4,
  )
  ctx = _ctx_with_blocker_at("2026-06-22T09:20:00")
  assert _score_condition_fraction(check, ctx) == 1.0


def test_condition_fraction_partial_after_window() -> None:
  check = RubricCheck(
    id="found_api_blocker",
    condition="agent_state.blockers_known includes 'PROJ-17_oauth_scope'",
    deadline="sim_day 1",
    full_credit_within_minutes=30,
    decay_minutes=60,
    on_time_floor=0.4,
  )
  ctx = _ctx_with_blocker_at("2026-06-22T09:57:00")
  fraction = _score_condition_fraction(check, ctx)
  assert 0.7 < fraction < 0.85


def test_condition_fraction_zero_when_never_met() -> None:
  check = RubricCheck(
    id="found_api_blocker",
    condition="agent_state.blockers_known includes 'PROJ-17_oauth_scope'",
    deadline="sim_day 1",
  )
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
  )
  assert _score_condition_fraction(check, ctx) == 0.0


def test_penalty_deduction_graduated() -> None:
  check = RubricCheck(
    id="found_without_spam",
    penalty_if="action_count.chat_send > 10 AND blockers_known.count < 1",
    penalty_max=4,
    penalty_scale=5,
  )
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
    action_counts={"chat_send": 15},
    blockers_known=[],
    tradeoff_documented=False,
    docs=[],
    milestones=[],
    tasks=[],
    project_health="ON_TRACK",
  )
  assert _score_penalty_deduction(check, ctx) == 1.0


def test_team_health_starts_at_ten_without_penalty(db) -> None:
  run_id = _insert_run(db)
  ctx = build_eval_context(db, run_id)
  rubric = load_rubric("first-week-pm")
  scored = score_rubric(ctx, rubric)
  team = next(c for c in scored.components if c.component_id == "team_health")
  assert team.score == 10.0
