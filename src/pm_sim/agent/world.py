"""Scenario world config loaded from sim_meta."""

from __future__ import annotations

from pm_sim.agent.types import WorldConfig
from pm_sim.sim.db import SimDatabase
from pm_sim.scenario.load import load_yaml, scenario_dir

DEFAULT_VENDOR_ID = "vendor_api"
DEFAULT_EXEC_ID = "exec"


def world_config_from_meta(db: SimDatabase) -> WorldConfig:
  return WorldConfig(
    vendor_id=db.get_meta("world_vendor_id") or DEFAULT_VENDOR_ID,
    exec_id=db.get_meta("world_exec_id") or DEFAULT_EXEC_ID,
  )


def world_config_from_scenario(scenario_id: str) -> WorldConfig:
  scenario = load_yaml(scenario_dir(scenario_id) / "scenario.yaml")
  world = scenario.get("world") or {}
  return WorldConfig(
    vendor_id=world.get("vendor_id", DEFAULT_VENDOR_ID),
    exec_id=world.get("exec_id", DEFAULT_EXEC_ID),
  )
