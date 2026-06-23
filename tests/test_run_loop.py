"""Tests for Phase 6 run loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from pm_sim.agent.policies import load_agent_spec, load_scenario_agent
from pm_sim.agent.turn import plan_agent_turn
from pm_sim.agent.world import world_config_from_meta
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.run_loop import RunConfig, run_simulation

FIXTURE_WAIT = Path(__file__).resolve().parent / "fixtures" / "wait_only.yaml"
SCENARIO = "first-week-pm"


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = reset_scenario(SCENARIO, db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_run_stops_at_max_turns(db: SimDatabase, tmp_path: Path) -> None:
  spec = load_scenario_agent(SCENARIO, "triage_first")
  world = world_config_from_meta(db)
  config = RunConfig(
    scenario_id=SCENARIO,
    agent_id="triage_first",
    max_turns=3,
    quiet=True,
    artifact_root=tmp_path / "runs",
  )

  result = run_simulation(db, spec, world=world, config=config)

  assert result.status == "incomplete"
  assert result.total_turns == 3
  row = db.conn.execute(
    "SELECT status FROM runs WHERE id = ?", (result.run_id,)
  ).fetchone()
  assert row["status"] == "incomplete"
  assert (result.artifact_dir / "turn.log").exists()
  assert (result.artifact_dir / "summary.txt").exists()
  assert (result.artifact_dir / "action_log.json").exists()


def test_run_logs_action_on_tool_turn(db: SimDatabase, tmp_path: Path) -> None:
  spec = load_scenario_agent(SCENARIO, "triage_first")
  world = world_config_from_meta(db)
  config = RunConfig(
    scenario_id=SCENARIO,
    agent_id="triage_first",
    max_turns=1,
    quiet=True,
    artifact_root=tmp_path / "runs",
  )

  result = run_simulation(db, spec, world=world, config=config)

  row = db.conn.execute(
    """
    SELECT action_type FROM action_log
    WHERE run_id = ? AND turn = 1 AND action_type != 'policy_decision'
    """,
    (result.run_id,),
  ).fetchone()
  assert row["action_type"] == "tasks_list"


def test_run_logs_wait_turn(db: SimDatabase, tmp_path: Path) -> None:
  spec = load_agent_spec(FIXTURE_WAIT)
  world = world_config_from_meta(db)
  config = RunConfig(
    scenario_id=SCENARIO,
    agent_id="wait_only",
    max_turns=1,
    quiet=True,
    artifact_root=tmp_path / "runs",
  )

  result = run_simulation(db, spec, world=world, config=config)

  row = db.conn.execute(
    """
    SELECT action_type FROM action_log
    WHERE run_id = ? AND action_type = 'wait'
    """,
    (result.run_id,),
  ).fetchone()
  assert row is not None


def test_run_clears_active_run_id(db: SimDatabase, tmp_path: Path) -> None:
  spec = load_scenario_agent(SCENARIO, "triage_first")
  world = world_config_from_meta(db)
  config = RunConfig(
    scenario_id=SCENARIO,
    agent_id="triage_first",
    max_turns=2,
    quiet=True,
    artifact_root=tmp_path / "runs",
  )

  run_simulation(db, spec, world=world, config=config)

  assert db.get_meta("active_run_id") is None
  assert db.get_meta("current_turn") is None


def test_run_first_action_matches_plan(db: SimDatabase, tmp_path: Path) -> None:
  spec = load_scenario_agent(SCENARIO, "triage_first")
  world = world_config_from_meta(db)
  planned = plan_agent_turn(db, spec, world=world)
  config = RunConfig(
    scenario_id=SCENARIO,
    agent_id="triage_first",
    max_turns=1,
    quiet=True,
    artifact_root=tmp_path / "runs",
  )

  result = run_simulation(db, spec, world=world, config=config)

  row = db.conn.execute(
    """
    SELECT action_type FROM action_log
    WHERE run_id = ? AND turn = 1 AND action_type != 'policy_decision'
    """,
    (result.run_id,),
  ).fetchone()
  assert row["action_type"] == planned.name


@pytest.mark.slow
def test_run_stops_when_launch_completes(db: SimDatabase, tmp_path: Path) -> None:
  spec = load_scenario_agent(SCENARIO, "triage_first")
  world = world_config_from_meta(db)
  config = RunConfig(
    scenario_id=SCENARIO,
    agent_id="triage_first",
    quiet=True,
    artifact_root=tmp_path / "runs",
  )

  result = run_simulation(db, spec, world=world, config=config)

  launch = db.conn.execute(
    "SELECT status FROM milestones WHERE id = 'launch'"
  ).fetchone()
  assert launch["status"] == "completed"
  assert result.status == "completed"
  assert result.total_turns < 3000
