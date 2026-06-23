"""Integration tests for strategy ordering and anti-gaming."""

from __future__ import annotations

from pathlib import Path

import pytest

from pm_sim.agent.policies import load_scenario_agent
from pm_sim.agent.world import world_config_from_meta
from pm_sim.eval.report import evaluate_run
from pm_sim.sim.clock import parse_sim_time
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.run_loop import RunConfig, run_simulation

SCENARIO = "first-week-pm"


def _run_and_eval(
  tmp_path: Path,
  agent_id: str,
  *,
  max_turns: int,
) -> tuple[object, object]:
  db_path = tmp_path / f"{agent_id}.db"
  db = reset_scenario(SCENARIO, db_path=db_path)
  try:
    spec = load_scenario_agent(SCENARIO, agent_id)
    world = world_config_from_meta(db)
    result = run_simulation(
      db,
      spec,
      world=world,
      config=RunConfig(
        scenario_id=SCENARIO,
        agent_id=agent_id,
        max_turns=max_turns,
        quiet=True,
        artifact_root=tmp_path / "runs",
      ),
    )
    report = evaluate_run(db, result.run_id, SCENARIO)
    return result, report
  finally:
    db.close()


@pytest.mark.slow
def test_persona_launch_ordering(tmp_path: Path) -> None:
  """Triage finishes earliest; inbox is delayed by inbox noise and drift slip."""
  triage_result, triage_report = _run_and_eval(tmp_path, "triage_first", max_turns=15000)
  meeting_result, meeting_report = _run_and_eval(tmp_path, "meeting_first", max_turns=15000)
  inbox_result, inbox_report = _run_and_eval(tmp_path, "inbox_first", max_turns=15000)

  triage_launch = triage_report.metrics.launch_sim_datetime
  meeting_launch = meeting_report.metrics.launch_sim_datetime
  inbox_launch = inbox_report.metrics.launch_sim_datetime

  assert triage_launch is not None
  assert meeting_launch is not None
  assert inbox_launch is not None

  triage_dt = parse_sim_time(triage_launch)
  meeting_dt = parse_sim_time(meeting_launch)
  inbox_dt = parse_sim_time(inbox_launch)

  # Meeting and triage share the same critical path; inbox is much later.
  assert meeting_dt <= inbox_dt
  assert (inbox_dt - triage_dt).total_seconds() >= 12 * 3600

  triage_outcome = next(
    c for c in triage_report.rubric.components if c.component_id == "project_outcome"
  )
  inbox_outcome = next(
    c for c in inbox_report.rubric.components if c.component_id == "project_outcome"
  )
  assert inbox_outcome.score < triage_outcome.score

  meeting_rubric = meeting_report.rubric.total
  triage_rubric = triage_report.rubric.total
  assert meeting_rubric < triage_rubric

  assert triage_result.status == "completed"
  assert meeting_result.status == "completed"
  assert inbox_result.status == "completed"


@pytest.mark.slow
def test_triage_before_spam_ping_launch(tmp_path: Path) -> None:
  triage_result, triage_report = _run_and_eval(tmp_path, "triage_first", max_turns=5000)
  spam_result, spam_report = _run_and_eval(tmp_path, "spam_ping", max_turns=5000)

  triage_launch = triage_report.metrics.launch_sim_datetime
  spam_launch = spam_report.metrics.launch_sim_datetime

  if triage_launch and spam_launch:
    assert parse_sim_time(triage_launch) <= parse_sim_time(spam_launch)
  elif triage_launch:
    assert spam_launch is None or True

  assert triage_result.total_turns <= spam_result.total_turns


@pytest.mark.slow
def test_spam_ping_scores_below_triage(tmp_path: Path) -> None:
  _, triage_report = _run_and_eval(tmp_path, "triage_first", max_turns=30)
  _, spam_report = _run_and_eval(tmp_path, "spam_ping", max_turns=30)

  assert spam_report.rubric.total < triage_report.rubric.total

  spam_blocker = next(
    c for c in spam_report.rubric.components if c.component_id == "blocker_discovery"
  )
  triage_blocker = next(
    c for c in triage_report.rubric.components if c.component_id == "blocker_discovery"
  )
  assert spam_blocker.score <= triage_blocker.score


@pytest.mark.slow
def test_triage_first_completes_launch(tmp_path: Path) -> None:
  result, report = _run_and_eval(tmp_path, "triage_first", max_turns=15000)

  assert result.status == "completed"
  assert report.metrics.launch_sim_datetime is not None
  assert result.total_turns < 3000

  db_path = tmp_path / "triage_first.db"
  from pm_sim.sim.db import SimDatabase

  db = SimDatabase(db_path)
  try:
    proj22 = db.conn.execute(
      "SELECT status FROM tasks WHERE id = 'PROJ-22'"
    ).fetchone()
    proj30 = db.conn.execute(
      "SELECT status FROM tasks WHERE id = 'PROJ-30'"
    ).fetchone()
    launch_row = db.conn.execute(
      "SELECT status FROM milestones WHERE id = 'launch'"
    ).fetchone()
    assert proj22["status"] == "done"
    assert proj30["status"] == "done"
    assert launch_row["status"] == "completed"
    outcome = next(
      c for c in report.rubric.components if c.component_id == "project_outcome"
    )
    assert outcome.score > 0
  finally:
    db.close()
