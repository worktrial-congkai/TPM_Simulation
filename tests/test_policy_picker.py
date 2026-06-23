"""Tests for policy picker."""

from pathlib import Path

import pytest

from pm_sim.agent.policies import load_agent_spec, load_scenario_agent, pick_first_policy
from pm_sim.agent.observation import build_observation
from pm_sim.agent.state import add_to_set, set_flag
from pm_sim.agent.world import world_config_from_meta
from pm_sim.sim.reset import reset_scenario

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "triage_first_minimal.yaml"


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_picker_chooses_tasks_list_first(db) -> None:
  spec = load_agent_spec(FIXTURE)
  world = world_config_from_meta(db)
  obs = build_observation(db)
  action = pick_first_policy(spec, obs, db, world=world)
  assert action.name == "tasks_list"
  assert action.event_type == "agent.tasks_list"
  assert action.policy_condition == "NOT tasks_checked"


def test_picker_chooses_ask_blocker_owner_after_tasks_checked(db) -> None:
  set_flag(db, "tasks_checked", True)
  spec = load_agent_spec(FIXTURE)
  world = world_config_from_meta(db)
  obs = build_observation(db)
  action = pick_first_policy(spec, obs, db, world=world)
  assert action.name == "ask_blocker_owner_dm"
  assert action.event_type == "agent.chat_send"
  assert action.policy_condition == "blocker_unknown AND NOT waiting_on_reply"


def test_picker_waits_when_reply_pending(db) -> None:
  from datetime import timedelta

  from pm_sim.sim.clock import get_sim_time
  from pm_sim.sim.events import SimEvent, insert_event

  set_flag(db, "tasks_checked", True)
  reply_at = get_sim_time(db) + timedelta(minutes=45)
  insert_event(
    db,
    SimEvent.create(
      event_type="npc.reply",
      start_ts=reply_at,
      source="test",
      actor_id="alex",
      payload={"coworker_id": "alex", "channel": "dm:alex", "action": "ack"},
    ),
  )
  spec = load_agent_spec(FIXTURE)
  world = world_config_from_meta(db)
  obs = build_observation(db)
  assert obs.waiting_on_reply is True
  action = pick_first_policy(spec, obs, db, world=world)
  assert action.name != "ask_blocker_owner_dm"
  assert action.name in ("wait", "read_dm")


def test_picker_starts_critical_path_when_ready(db) -> None:
  add_to_set(db, "blockers_known", "PROJ-17_oauth_scope")
  set_flag(db, "tasks_checked", True)
  set_flag(db, "vendor_escalated", True)
  set_flag(db, "requirements_meeting_scheduled", True)
  set_flag(db, "tradeoff_documented", True)
  set_flag(db, "stakeholders_informed", ["sam"])
  db.conn.execute("UPDATE tasks SET status = 'done' WHERE id = 'PROJ-17'")
  db.conn.execute(
    """
    UPDATE tasks
    SET status = 'todo', blocker_reason = NULL
    WHERE id = 'PROJ-22'
    """
  )
  db.conn.commit()

  spec = load_scenario_agent("first-week-pm", "triage_first")
  world = world_config_from_meta(db)
  obs = build_observation(db)
  action = pick_first_policy(spec, obs, db, world=world)
  assert action.name == "start_next_critical_task"
  assert action.payload["task_id"] == "PROJ-22"
