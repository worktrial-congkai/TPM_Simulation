"""CLI tests for compare-agents."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from pm_sim.cli.main import cli


def test_cli_compare_agents_smoke(tmp_path: Path) -> None:
  db_path = tmp_path / "sim.db"
  runner = CliRunner()
  result = runner.invoke(
    cli,
    [
      "eval",
      "first-week-pm",
      "--db-path",
      str(db_path),
      "--compare-agents",
      "--max-turns",
      "1",
    ],
  )
  assert result.exit_code == 0, result.output
  assert "Persona" in result.output
  assert "triage_first" in result.output
  assert "spam_ping" in result.output


def test_cli_eval_rubric_output(tmp_path: Path) -> None:
  db_path = tmp_path / "sim.db"
  runner = CliRunner()
  from pm_sim.sim.reset import reset_scenario
  reset_scenario("first-week-pm", db_path=db_path).close()
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
  assert "Phase 9" not in eval_result.output
