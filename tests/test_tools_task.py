"""Tests for task tool."""

from pathlib import Path

import pytest

from pm_sim.sim.reset import reset_scenario
from pm_sim.tools.base import ToolError
from pm_sim.tools.task import TaskTool


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_list_returns_proj17_blocked(db) -> None:
  tasks = TaskTool.list_tasks(db)
  proj17 = next(t for t in tasks if t["id"] == "PROJ-17")
  assert proj17["status"] == "blocked"
  assert proj17["duration_minutes"] == 780


def test_update_rejects_invalid_transition(db) -> None:
  with pytest.raises(ToolError, match="Cannot transition"):
    TaskTool.update_task(db, "PROJ-17", status="in_progress")
