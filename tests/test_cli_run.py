"""CLI smoke tests for Phase 6 run commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from pm_sim.cli.main import cli
from pm_sim.sim.reset import reset_scenario


def test_cli_run_max_turns(tmp_path: Path) -> None:
  db_path = tmp_path / "sim.db"
  reset_scenario("first-week-pm", db_path=db_path).close()

  runner = CliRunner()
  result = runner.invoke(
    cli,
    [
      "run",
      "--scenario",
      "first-week-pm",
      "--agent",
      "triage_first",
      "--db-path",
      str(db_path),
      "--max-turns",
      "2",
      "--quiet",
      "--json",
    ],
  )

  assert result.exit_code == 0, result.output
  assert '"total_turns": 2' in result.output
  assert '"status": "incomplete"' in result.output


def test_cli_run_show_and_events_log(tmp_path: Path) -> None:
  db_path = tmp_path / "sim.db"
  reset_scenario("first-week-pm", db_path=db_path).close()

  runner = CliRunner()
  run_result = runner.invoke(
    cli,
    [
      "run",
      "--scenario",
      "first-week-pm",
      "--agent",
      "triage_first",
      "--db-path",
      str(db_path),
      "--max-turns",
      "1",
      "--quiet",
      "--json",
    ],
  )
  assert run_result.exit_code == 0, run_result.output

  payload = json.loads(run_result.output)
  run_id = payload["run_id"]

  show_result = runner.invoke(
    cli,
    ["run", "show", "--run-id", run_id, "--db-path", str(db_path)],
  )
  assert show_result.exit_code == 0, show_result.output
  assert "Turn 1" in show_result.output

  events_result = runner.invoke(
    cli,
    ["events", "log", "--run-id", run_id, "--db-path", str(db_path)],
  )
  assert events_result.exit_code == 0, events_result.output
  assert "tasks_list" in events_result.output


def test_cli_run_stdout_shows_action_and_result(tmp_path: Path) -> None:
  db_path = tmp_path / "sim.db"
  reset_scenario("first-week-pm", db_path=db_path).close()

  runner = CliRunner()
  result = runner.invoke(
    cli,
    [
      "run",
      "--scenario",
      "first-week-pm",
      "--agent",
      "triage_first",
      "--db-path",
      str(db_path),
      "--max-turns",
      "2",
    ],
  )

  assert result.exit_code == 0, result.output
  assert "OBSERVE:" in result.output
  assert "ACTION:" in result.output
  assert "RESULT:" in result.output


def test_cli_eval_stub(tmp_path: Path) -> None:
  db_path = tmp_path / "sim.db"
  reset_scenario("first-week-pm", db_path=db_path).close()

  runner = CliRunner()
  runner.invoke(
    cli,
    [
      "run",
      "--scenario",
      "first-week-pm",
      "--agent",
      "triage_first",
      "--db-path",
      str(db_path),
      "--max-turns",
      "1",
      "--quiet",
    ],
  )

  eval_result = runner.invoke(
    cli,
    ["eval", "first-week-pm", "--db-path", str(db_path)],
  )
  assert eval_result.exit_code == 0, eval_result.output
  assert "Total" in eval_result.output
  assert "/10" in eval_result.output
