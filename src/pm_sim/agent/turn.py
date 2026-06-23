"""Agent turn planning bridge for Phase 6 run loop."""

from __future__ import annotations

from pm_sim.agent.observation import build_observation
from pm_sim.agent.policies import pick_first_policy
from pm_sim.agent.types import AgentAction, AgentSpec, WorldConfig
from pm_sim.sim.clock import get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent


def plan_agent_turn(
  db: SimDatabase,
  spec: AgentSpec,
  *,
  world: WorldConfig,
) -> AgentAction:
  obs = build_observation(db)
  return pick_first_policy(spec, obs, db, world=world)


def action_to_event(action: AgentAction, db: SimDatabase) -> SimEvent | None:
  if action.type != "tool":
    return None
  if not action.event_type or action.payload is None:
    raise ValueError(f"Tool action missing event details: {action.name}")
  return SimEvent.create(
    event_type=action.event_type,
    start_ts=get_sim_time(db),
    source=f"agent:{action.name}",
    payload=action.payload,
  )
