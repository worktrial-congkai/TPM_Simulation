"""Tests for per-action sim time costs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pm_sim.agent.types import AgentAction
from pm_sim.sim.action_duration import (
  DEFAULT_ACTION_DURATIONS,
  DEFAULT_WAIT_MINUTES,
  resolve_action_duration,
  resolve_wait_minutes,
)
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.reset import reset_scenario


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_default_action_durations(db: SimDatabase) -> None:
  action = AgentAction(type="tool", name="tasks_list", event_type="agent.tasks_list")
  assert resolve_action_duration(db, action) == DEFAULT_ACTION_DURATIONS["tasks_list"]


def test_default_wait_minutes(db: SimDatabase) -> None:
  assert resolve_wait_minutes(db) == DEFAULT_WAIT_MINUTES


def test_scenario_override_from_meta(db: SimDatabase) -> None:
  overrides = dict(DEFAULT_ACTION_DURATIONS)
  overrides["tasks_list"] = 7
  overrides["default"] = 4
  db.set_meta("action_durations", json.dumps(overrides))
  db.set_meta("wait_minutes", "5")

  assert resolve_wait_minutes(db) == 5
  assert resolve_action_duration(
    db,
    AgentAction(type="tool", name="tasks_list"),
  ) == 7
  assert resolve_action_duration(
    db,
    AgentAction(type="tool", name="unknown_action"),
  ) == 4


def test_wait_action_uses_wait_minutes(db: SimDatabase) -> None:
  db.set_meta("wait_minutes", "3")
  action = AgentAction(type="wait", name="wait")
  assert resolve_action_duration(db, action) == 3
