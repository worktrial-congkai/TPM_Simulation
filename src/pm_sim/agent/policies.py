"""Agent policy loading and first-match picker."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pm_sim.agent.actions import resolve_action
from pm_sim.agent.conditions import evaluate_condition
from pm_sim.agent.types import AgentAction, AgentSpec, Observation, PolicyRule, WorldConfig
from pm_sim.sim.db import SimDatabase
from pm_sim.scenario.load import load_yaml, scenario_dir


def agent_spec_path(scenario_id: str, agent_id: str) -> Path:
  return scenario_dir(scenario_id) / "agents" / f"{agent_id}.yaml"


def load_scenario_agent(scenario_id: str, agent_id: str) -> AgentSpec:
  path = agent_spec_path(scenario_id, agent_id)
  if not path.exists():
    raise FileNotFoundError(f"Agent spec not found: {path}")
  return load_agent_spec(path)


def list_scenario_agents(scenario_id: str) -> list[str]:
  agents_dir = scenario_dir(scenario_id) / "agents"
  if not agents_dir.is_dir():
    return []
  return sorted(p.stem for p in agents_dir.glob("*.yaml"))


def load_agent_spec(path: Path) -> AgentSpec:
  data = load_yaml(path)
  policies = tuple(
    PolicyRule(condition=str(rule["condition"]), action=str(rule["action"]))
    for rule in (data.get("policies") or [])
  )
  return AgentSpec(id=str(data["id"]), policies=policies)


def pick_first_policy(
  spec: AgentSpec,
  obs: Observation,
  db: SimDatabase,
  *,
  world: WorldConfig,
) -> AgentAction:
  for rule in spec.policies:
    if evaluate_condition(rule.condition, obs, db):
      action = resolve_action(rule.action, obs, db, world=world)
      return replace(action, policy_condition=rule.condition)
  return AgentAction(type="wait", name="wait")
