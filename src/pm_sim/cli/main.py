"""Click CLI entrypoint."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console

from pm_sim.display.turn_collapser import TurnLogPushResult
from pm_sim.display.turn_stdout import TurnStdoutRenderer

from pm_sim.agent.policies import list_scenario_agents, load_scenario_agent
from pm_sim.agent.world import world_config_from_meta
from pm_sim.eval.compare import compare_agents as run_compare_agents
from pm_sim.eval.report import evaluate_run, format_compare_table, format_report_json, format_report_text, write_eval_artifacts
from pm_sim.sim.runs import run_artifact_dir
from pm_sim.sim.clock import get_sim_time
from pm_sim.sim.db import open_existing_db
from pm_sim.sim.reset import DEFAULT_DB_PATH, _repo_root, reset_scenario
from pm_sim.sim.run_loop import RunConfig, run_simulation
from pm_sim.sim.runs import get_run, run_artifact_dir

console = Console()


def _resolve_db_path(db_path: str) -> Path:
  path = Path(db_path)
  if not path.is_absolute():
    path = _repo_root() / path
  return path


@click.group()
def cli() -> None:
  """PM Simulation — strategy-evaluating PM first-week simulator."""


@cli.group()
def scenario() -> None:
  """Scenario management commands."""


@scenario.command("reset")
@click.argument("scenario_id")
@click.option(
  "--db-path",
  default=str(DEFAULT_DB_PATH),
  show_default=True,
  help="Path to SQLite database file.",
)
def scenario_reset(scenario_id: str, db_path: str) -> None:
  """Reset and seed a scenario into a fresh database."""
  db = reset_scenario(scenario_id, db_path=Path(db_path))
  sim_time = get_sim_time(db)
  db.close()
  console.print(
    f"[green]Scenario reset complete[/green]: {scenario_id}\n"
    f"  sim_time: {sim_time.isoformat()}\n"
    f"  db:       {db_path}"
  )


@cli.group("run", invoke_without_command=True)
@click.pass_context
@click.option(
  "--scenario",
  "scenario_id",
  default=None,
  help="Scenario id (required for run; omit for subcommands).",
)
@click.option("--agent", default=None, help="Agent persona id under scenarios/.../agents/")
@click.option(
  "--db-path",
  default=str(DEFAULT_DB_PATH),
  show_default=True,
  help="Path to SQLite database file (must be reset first).",
)
@click.option("--max-turns", type=int, default=None, help="Override scenario max_turns cap.")
@click.option("--quiet", is_flag=True, help="Write turn log to file only; periodic stdout summary.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable RunResult JSON.")
def run_group(
  ctx: click.Context,
  scenario_id: str | None,
  agent: str | None,
  db_path: str,
  max_turns: int | None,
  quiet: bool,
  as_json: bool,
) -> None:
  """Run an agent persona, or inspect runs via subcommands (show)."""
  if ctx.invoked_subcommand is not None:
    return

  if scenario_id is None or agent is None:
    raise click.ClickException(
      "Usage: pm-sim run --scenario <scenario_id> --agent <persona>"
    )

  agents = list_scenario_agents(scenario_id)
  if agent not in agents:
    raise click.ClickException(
      f"Unknown agent {agent!r}. Available: {', '.join(agents)}"
    )

  path = _resolve_db_path(db_path)
  try:
    db = open_existing_db(path)
  except RuntimeError as exc:
    raise click.ClickException(str(exc)) from exc

  spec = load_scenario_agent(scenario_id, agent)
  world = world_config_from_meta(db)
  config = RunConfig(
    scenario_id=scenario_id,
    agent_id=agent,
    max_turns=max_turns,
    quiet=quiet,
  )

  stdout_renderer = TurnStdoutRenderer(console) if not quiet else None

  def on_turn(result: TurnLogPushResult) -> None:
    if stdout_renderer is not None:
      stdout_renderer.emit(result)

  try:
    result = run_simulation(
      db,
      spec,
      world=world,
      config=config,
      on_turn=on_turn,
    )
  finally:
    if stdout_renderer is not None:
      stdout_renderer.close()
    db.close()

  if as_json:
    payload = {
      "run_id": result.run_id,
      "scenario_id": result.scenario_id,
      "agent_id": result.agent_id,
      "status": result.status,
      "total_turns": result.total_turns,
      "wait_turns": result.wait_turns,
      "artifact_dir": str(result.artifact_dir),
    }
    click.echo(json.dumps(payload, indent=2))
  else:
    console.print(result.summary)
    console.print(f"  run_id: {result.run_id}")
    console.print(f"  logs:   {result.artifact_dir}")


@run_group.command("show")
@click.option("--run-id", required=True, help="Run id from pm-sim run output.")
@click.option(
  "--db-path",
  default=str(DEFAULT_DB_PATH),
  show_default=True,
  help="Path to SQLite database file.",
)
def run_show(run_id: str, db_path: str) -> None:
  """Print the turn log for a completed run."""
  path = _resolve_db_path(db_path)
  db = open_existing_db(path)
  try:
    if get_run(db, run_id) is None:
      raise click.ClickException(f"Run not found: {run_id}")
  finally:
    db.close()

  log_path = run_artifact_dir(run_id) / "turn.log"
  if not log_path.exists():
    raise click.ClickException(f"Turn log not found: {log_path}")
  console.print(log_path.read_text(encoding="utf-8"))


@cli.group("events")
def events_group() -> None:
  """Event and action log commands."""


@events_group.command("log")
@click.option("--run-id", required=True, help="Run id from pm-sim run output.")
@click.option(
  "--db-path",
  default=str(DEFAULT_DB_PATH),
  show_default=True,
  help="Path to SQLite database file.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON action log.")
def events_log(run_id: str, db_path: str, as_json: bool) -> None:
  """Print the action log for a completed run."""
  path = _resolve_db_path(db_path)
  db = open_existing_db(path)
  try:
    if get_run(db, run_id) is None:
      raise click.ClickException(f"Run not found: {run_id}")

    rows = db.conn.execute(
      """
      SELECT turn, sim_time, action_type, payload, result
      FROM action_log
      WHERE run_id = ?
      ORDER BY turn, id
      """,
      (run_id,),
    ).fetchall()

    if as_json:
      entries = [
        {
          "turn": row["turn"],
          "sim_time": row["sim_time"],
          "action_type": row["action_type"],
          "payload": json.loads(row["payload"]),
          "result": json.loads(row["result"]) if row["result"] else None,
        }
        for row in rows
      ]
      click.echo(json.dumps(entries, indent=2))
      return

    for row in rows:
      console.print(
        f"Turn {row['turn']} [{row['sim_time']}] {row['action_type']}"
      )
  finally:
    db.close()


@cli.command("eval")
@click.argument("scenario_id")
@click.option("--run-id", default=None, help="Run id to evaluate (latest run if omitted).")
@click.option(
  "--db-path",
  default=str(DEFAULT_DB_PATH),
  show_default=True,
  help="Path to SQLite database file.",
)
@click.option("--compare-agents", is_flag=True, help="Reset, run, and compare all personas.")
@click.option("--max-turns", type=int, default=None, help="Override max_turns for compare runs.")
@click.option("--json", "as_json", is_flag=True, help="Emit metrics as JSON.")
def eval_command(
  scenario_id: str,
  run_id: str | None,
  db_path: str,
  compare_agents: bool,
  max_turns: int | None,
  as_json: bool,
) -> None:
  """Evaluate a run with strategy metrics and rubric scoring."""
  path = _resolve_db_path(db_path)

  if compare_agents:
    reports = run_compare_agents(
      scenario_id,
      path,
      max_turns=max_turns,
      quiet=True,
    )
    if as_json:
      click.echo(json.dumps([format_report_json(r) for r in reports], indent=2))
      return
    console.print(format_compare_table(reports))
    return

  db = open_existing_db(path)
  try:
    if run_id is None:
      row = db.conn.execute(
        """
        SELECT id FROM runs
        WHERE scenario_id = ?
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (scenario_id,),
      ).fetchone()
      if row is None:
        raise click.ClickException(f"No runs found for scenario {scenario_id!r}")
      run_id = row["id"]

    report = evaluate_run(db, run_id, scenario_id)
    write_eval_artifacts(report, run_artifact_dir(run_id))
  finally:
    db.close()

  if as_json:
    click.echo(json.dumps(format_report_json(report), indent=2))
    return

  console.print(format_report_text(report))


if __name__ == "__main__":
  cli()
