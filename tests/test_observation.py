"""Tests for observation snapshot builder."""

from pathlib import Path

import pytest

from pm_sim.agent.observation import build_observation
from pm_sim.sim.reset import reset_scenario


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_observation_after_reset(db) -> None:
  obs = build_observation(db)
  assert obs.blocker_owner == "alex"
  assert obs.tasks_checked is False
  assert obs.blockers_known == ()
  assert obs.vendor_escalated is False
  assert len(obs.unread_channels) == 3
  assert "eng-launch" in obs.unread_channels
  assert "dm:alex" in obs.unread_channels
  assert "dm:sam" in obs.unread_channels
  assert len(obs.unread_email_ids) == 19
