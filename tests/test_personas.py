"""Tests for scenario agent personas (Phase 5)."""

from __future__ import annotations

import pytest

from pm_sim.agent.conditions import SPAM_PING_MIN_SENDS, SPAM_PING_TARGETS, evaluate_condition
from pm_sim.agent.observation import build_observation
from pm_sim.agent.policies import list_scenario_agents, load_scenario_agent
from pm_sim.agent.turn import action_to_event, plan_agent_turn
from pm_sim.agent.world import world_config_from_meta
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.turns import execute_tool_turn

SCENARIO_ID = "first-week-pm"
EXPECTED_AGENTS = (
  "inbox_first",
  "meeting_first",
  "spam_ping",
  "triage_first",
)


@pytest.fixture
def db(tmp_path):
  database = reset_scenario(SCENARIO_ID, db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_list_scenario_agents() -> None:
  assert list_scenario_agents(SCENARIO_ID) == list(EXPECTED_AGENTS)


def test_all_persona_specs_load() -> None:
  for agent_id in EXPECTED_AGENTS:
    spec = load_scenario_agent(SCENARIO_ID, agent_id)
    assert spec.id == agent_id
    assert len(spec.policies) >= 1


@pytest.mark.parametrize(
  ("agent_id", "expected_action"),
  [
    ("triage_first", "tasks_list"),
    ("inbox_first", "read_email"),
    ("meeting_first", "schedule_requirements_meeting"),
    ("spam_ping", "spam_ping_dm"),
  ],
)
def test_first_action_on_fresh_reset(db, agent_id: str, expected_action: str) -> None:
  spec = load_scenario_agent(SCENARIO_ID, agent_id)
  world = world_config_from_meta(db)
  action = plan_agent_turn(db, spec, world=world)
  assert action.name == expected_action


def test_spam_ping_exhausted_before_tasks_list(db) -> None:
  spec = load_scenario_agent(SCENARIO_ID, "spam_ping")
  world = world_config_from_meta(db)
  obs = build_observation(db)

  for _ in range(SPAM_PING_MIN_SENDS):
    action = plan_agent_turn(db, spec, world=world)
    assert action.name == "spam_ping_dm"
    event = action_to_event(action, db)
    assert event is not None
    execute_tool_turn(db, event)
    obs = build_observation(db)

  assert not evaluate_condition("can_spam_ping", obs, db)
  next_action = plan_agent_turn(db, spec, world=world)
  assert next_action.name != "tasks_list"
