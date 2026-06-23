"""Compare all scenario personas — reset and run each."""

from __future__ import annotations

from pathlib import Path

from pm_sim.agent.policies import list_scenario_agents, load_scenario_agent
from pm_sim.agent.world import world_config_from_meta
from pm_sim.eval.report import EvalReport, evaluate_run, write_eval_artifacts
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.run_loop import RunConfig, run_simulation
from pm_sim.sim.runs import run_artifact_dir


def compare_agents(
  scenario_id: str,
  db_path: Path | str,
  *,
  max_turns: int | None = None,
  artifact_root: Path | None = None,
  quiet: bool = True,
) -> list[EvalReport]:
  """Reset, run, and evaluate each persona; return reports in agent_id order."""
  reports: list[EvalReport] = []
  path = Path(db_path)

  for agent_id in list_scenario_agents(scenario_id):
    db = reset_scenario(scenario_id, db_path=path)
    run_id: str | None = None
    artifact_dir: Path | None = None
    try:
      spec = load_scenario_agent(scenario_id, agent_id)
      world = world_config_from_meta(db)
      config = RunConfig(
        scenario_id=scenario_id,
        agent_id=agent_id,
        max_turns=max_turns,
        quiet=quiet,
        artifact_root=artifact_root,
      )
      try:
        result = run_simulation(db, spec, world=world, config=config)
        run_id = result.run_id
        artifact_dir = result.artifact_dir
      except Exception:
        row = db.conn.execute(
          """
          SELECT id FROM runs
          WHERE agent_id = ?
          ORDER BY started_at DESC
          LIMIT 1
          """,
          (agent_id,),
        ).fetchone()
        if row is None:
          raise
        run_id = row["id"]
        artifact_dir = run_artifact_dir(run_id, base=artifact_root)

      report = evaluate_run(db, run_id, scenario_id)
      if artifact_dir:
        write_eval_artifacts(report, artifact_dir)
      reports.append(report)
    finally:
      db.close()

  return reports
