"""Tests for NPC policy resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from pm_sim.npcs.conditions import evaluate_npc_condition
from pm_sim.npcs.resolver import pick_matching_template, pick_reactive_reply, resolve_policies
from pm_sim.npcs.types import NpcContext
from pm_sim.sim.reset import reset_scenario


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_resolve_policies_alex_gets_engineering_template() -> None:
  templates = [
    {
      "id": "eng_blocker_disclosure_full",
      "requires_role": "engineering",
      "trigger": "message_received",
      "action": "reply_with_full_blocker_details",
    },
    {
      "id": "protect_launch_date_pushback",
      "requires_goal": "protect_launch_date",
      "trigger": "message_received",
      "action": "push_back_on_delay",
    },
  ]
  alex = {
    "id": "alex",
    "role": "engineering",
    "goals": ["protect_engineering_capacity"],
    "constraints": [],
  }
  assert resolve_policies(alex, templates) == ["eng_blocker_disclosure_full"]


def test_pick_matching_template_dm_blocker(db) -> None:
  ctx = NpcContext(
    coworker_id="alex",
    channel="dm:alex",
    topic="blocker_status",
    message_kind="dm",
  )
  template = pick_matching_template(db, "alex", "message_received", ctx)
  assert template is not None
  assert template.id == "eng_blocker_disclosure_full"


def test_pick_matching_template_channel_blocker(db) -> None:
  ctx = NpcContext(
    coworker_id="",
    channel="eng-launch",
    topic="blocker_status",
    message_kind="channel",
  )
  match = pick_reactive_reply(db, ctx)
  assert match is not None
  coworker_id, template = match
  assert coworker_id == "alex"
  assert template.id == "eng_blocker_disclosure_partial"


def test_jordan_policy_scan_template(db) -> None:
  ctx = NpcContext(coworker_id="jordan", channel="dm:jordan")
  template = pick_matching_template(db, "jordan", "policy_scan", ctx)
  assert template is None

  from pm_sim.sim.clock import set_sim_time, parse_sim_time

  set_sim_time(db, parse_sim_time("2026-06-24T09:00:00"))
  template = pick_matching_template(db, "jordan", "policy_scan", ctx)
  assert template is not None
  assert template.id == "customer_pressure_dm"


def test_evaluate_sim_day_condition(db) -> None:
  ctx = NpcContext(coworker_id="jordan")
  assert evaluate_npc_condition("sim_day >= 3", ctx, db) is False

  from pm_sim.sim.clock import set_sim_time, parse_sim_time

  set_sim_time(db, parse_sim_time("2026-06-24T09:00:00"))
  assert evaluate_npc_condition("sim_day >= 3", ctx, db) is True
