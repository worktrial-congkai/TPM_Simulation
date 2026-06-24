"""Tests for scenario package validation and Phase 8 seeds."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pm_sim.agent.observation import build_observation
from pm_sim.scenario import ScenarioValidationError, validate_scenario
from pm_sim.scenario.load import scenario_dir
from pm_sim.sim.reset import reset_scenario

SCENARIO_ID = "first-week-pm"


def test_validate_scenario_passes() -> None:
  warnings = validate_scenario(SCENARIO_ID)
  assert isinstance(warnings, list)


def test_reset_unread_chat_count(tmp_path: Path) -> None:
  db = reset_scenario(SCENARIO_ID, db_path=tmp_path / "sim.db")
  try:
    obs = build_observation(db)
    assert len(obs.unread_channels) == 3
    assert "eng-launch" in obs.unread_channels
    assert "dm:alex" in obs.unread_channels
    assert "dm:sam" in obs.unread_channels
  finally:
    db.close()


def test_reset_emails_for_conflict(tmp_path: Path) -> None:
  db = reset_scenario(SCENARIO_ID, db_path=tmp_path / "sim.db")
  try:
    rows = db.conn.execute(
      """
      SELECT id, sender_id FROM emails
      WHERE recipient_id = 'agent' AND read_by_agent = 0
        AND id IN ('email-001', 'email-002')
      ORDER BY sender_id
      """
    ).fetchall()
    assert len(rows) == 2
    assert {row["sender_id"] for row in rows} == {"jordan", "sam"}
  finally:
    db.close()


def test_critical_path_tasks(tmp_path: Path) -> None:
  db = reset_scenario(SCENARIO_ID, db_path=tmp_path / "sim.db")
  try:
    proj17 = db.conn.execute(
      "SELECT status, blocker_reason, depends_on FROM tasks WHERE id = 'PROJ-17'"
    ).fetchone()
    assert proj17["status"] == "blocked"
    assert "integration" in proj17["blocker_reason"]

    proj22 = db.conn.execute(
      "SELECT depends_on FROM tasks WHERE id = 'PROJ-22'"
    ).fetchone()
    assert "PROJ-17" in proj22["depends_on"]

    proj30 = db.conn.execute(
      "SELECT depends_on FROM tasks WHERE id = 'PROJ-30'"
    ).fetchone()
    deps = proj30["depends_on"]
    assert "PROJ-17" in deps
    assert "PROJ-22" in deps
  finally:
    db.close()


def test_eval_rubric_loads() -> None:
  path = scenario_dir(SCENARIO_ID) / "eval_rubric.yaml"
  with path.open(encoding="utf-8") as f:
    rubric = yaml.safe_load(f)
  for key in (
    "blocker_discovery",
    "stakeholder_alignment",
    "project_outcome",
    "communication_discipline",
  ):
    assert key in rubric


def test_company_meta_seeded(tmp_path: Path) -> None:
  db = reset_scenario(SCENARIO_ID, db_path=tmp_path / "sim.db")
  try:
    assert db.get_meta("company_name") == "Acme SaaS"
    assert db.get_meta("company_product") == "Launch Platform"
    assert db.get_meta("company_launch_target") == "2026-06-24T18:00:00"
  finally:
    db.close()


def test_validate_raises_for_missing_scenario() -> None:
  with pytest.raises(ScenarioValidationError, match="Scenario not found"):
    validate_scenario("nonexistent-scenario")
