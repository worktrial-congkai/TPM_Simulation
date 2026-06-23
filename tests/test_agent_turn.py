"""Tests for agent turn planning bridge."""

from pathlib import Path

import pytest

from pm_sim.agent.policies import load_agent_spec
from pm_sim.agent.state import get_flag
from pm_sim.agent.turn import action_to_event, plan_agent_turn
from pm_sim.agent.world import world_config_from_meta
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.turns import execute_tool_turn

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "triage_first_minimal.yaml"


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_plan_and_execute_tasks_list(db) -> None:
  spec = load_agent_spec(FIXTURE)
  world = world_config_from_meta(db)
  action = plan_agent_turn(db, spec, world=world)
  event = action_to_event(action, db)
  assert event is not None
  execute_tool_turn(db, event)
  assert get_flag(db, "tasks_checked") is True
