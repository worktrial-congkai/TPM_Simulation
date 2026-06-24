"""Simulation run loop — Phase 6."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pm_sim.agent.action_log import log_action
from pm_sim.agent.observation import build_observation
from pm_sim.agent.turn import action_to_event, plan_agent_turn
from pm_sim.agent.types import AgentSpec, WorldConfig
from pm_sim.display.turn_collapser import TurnLogPushResult
from pm_sim.display.interaction_timeline import write_interaction_timeline
from pm_sim.display.turn_log import (
  CollapsingTurnLogWriter,
  export_action_log_json,
  format_action_label,
  format_run_summary,
  format_turn_block,
  format_world_event_block,
  partition_processed_events,
)
from pm_sim.eval.metrics import compute_run_metrics
from pm_sim.eval.report import evaluate_run, write_eval_artifacts
from pm_sim.sim.clock import get_sim_time, parse_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.action_duration import resolve_action_duration
from pm_sim.sim.runs import clear_run_context, create_run, finalize_run
from pm_sim.sim.turns import execute_tool_turn, execute_wait_turn


@dataclass
class RunConfig:
  scenario_id: str
  agent_id: str
  max_turns: int | None = None
  quiet: bool = False
  summary_interval: int = 50
  artifact_root: Path | None = None


@dataclass
class RunResult:
  run_id: str
  scenario_id: str
  agent_id: str
  status: str
  total_turns: int
  wait_turns: int
  artifact_dir: Path
  summary: str


def _max_turns_for_run(db: SimDatabase, config: RunConfig) -> int:
  if config.max_turns is not None:
    return config.max_turns
  return int(db.get_meta("max_turns") or "15000")


def _end_time(db: SimDatabase) -> datetime:
  raw = db.get_meta("end_time")
  if raw is None:
    raise RuntimeError("end_time not set in sim_meta")
  return parse_sim_time(raw)


def _start_time(db: SimDatabase) -> datetime:
  raw = db.get_meta("start_time")
  if raw is None:
    raise RuntimeError("start_time not set in sim_meta")
  return parse_sim_time(raw)


def _launch_completed(db: SimDatabase) -> bool:
  row = db.conn.execute(
    "SELECT status FROM milestones WHERE id = 'launch'"
  ).fetchone()
  return row is not None and row["status"] == "completed"


def _log_wait_turn(db: SimDatabase, processed_event_ids: list[str]) -> None:
  log_action(db, "wait", {}, {"processed": processed_event_ids})
  db.conn.commit()


def run_simulation(
  db: SimDatabase,
  spec: AgentSpec,
  *,
  world: WorldConfig,
  config: RunConfig,
  on_turn: Callable[[TurnLogPushResult], None] | None = None,
) -> RunResult:
  """Drive the agent until stop conditions; persist turn logs and run metadata."""
  max_turns = _max_turns_for_run(db, config)
  end_time = _end_time(db)
  start_time = _start_time(db)

  run_id, artifact_dir = create_run(
    db,
    scenario_id=config.scenario_id,
    agent_id=config.agent_id,
    base=config.artifact_root,
  )
  turn_log_path = artifact_dir / "turn.log"
  action_log_path = artifact_dir / "action_log.json"
  timeline_path = artifact_dir / "timeline.txt"
  turn_log_writer = CollapsingTurnLogWriter(turn_log_path, start_time=start_time)

  status = "completed"
  turn = 0
  wait_turns = 0
  summary = ""

  def _record_turn(
    block: str,
    *,
    turn_num: int,
    sim_time: datetime,
    action_label: str,
    minutes_advanced: int = 0,
  ) -> None:
    push_result = turn_log_writer.push(
      turn_num,
      sim_time,
      block,
      minutes_advanced=minutes_advanced,
      action_label=action_label,
    )
    if on_turn:
      on_turn(push_result)

  try:
    while True:
      turn += 1
      db.set_meta("current_turn", str(turn))

      obs = build_observation(db)
      health = db.get_meta("project_health") or "ON_TRACK"
      action = plan_agent_turn(db, spec, world=world)
      log_action(
        db,
        "policy_decision",
        {
          "condition": action.policy_condition,
          "action": action.name,
        },
      )

      if action.type == "done":
        block = format_turn_block(
          turn, obs, action, db, start_time=start_time, health=health,
        )
        _record_turn(
          block,
          turn_num=turn,
          sim_time=obs.sim_time,
          action_label=format_action_label(action, db),
        )
        break

      processed: list[str] = []
      minutes_advanced = 0
      if action.type == "wait":
        result = execute_wait_turn(db)
        processed = result.processed_event_ids
        health = result.health
        minutes_advanced = result.minutes_advanced
        _log_wait_turn(db, processed)
        wait_turns += 1
      else:
        event = action_to_event(action, db)
        if event is None:
          raise RuntimeError(f"Tool action missing event: {action.name}")
        minutes = resolve_action_duration(db, action)
        tool_result = execute_tool_turn(db, event, minutes=minutes)
        processed = tool_result.processed_event_ids
        health = tool_result.health
        minutes_advanced = tool_result.minutes_advanced
        db.conn.commit()

      if not (action.type == "wait" and not processed):
        at_start_events, mid_turn_events = partition_processed_events(
          db, processed, obs.sim_time,
        )
        block = format_turn_block(
          turn,
          obs,
          action,
          db,
          start_time=start_time,
          health=health,
          processed_event_ids=at_start_events,
          minutes_advanced=minutes_advanced,
        )
        _record_turn(
          block,
          turn_num=turn,
          sim_time=obs.sim_time,
          action_label=format_action_label(action, db),
          minutes_advanced=minutes_advanced,
        )
        for event_id in mid_turn_events:
          world_block = format_world_event_block(
            event_id, db, start_time=start_time,
          )
          if world_block:
            turn_log_writer.append_standalone_block(world_block)
            if on_turn:
              on_turn(TurnLogPushResult(standalone_block=world_block))

      if get_sim_time(db) >= end_time:
        break

      if _launch_completed(db):
        break

      if turn >= max_turns:
        status = "incomplete"
        break

  except Exception:
    status = "error"
    raise
  finally:
    flush_result = turn_log_writer.flush()
    if on_turn and flush_result.live_block:
      on_turn(flush_result)
    finalize_run(db, run_id, status=status)
    export_action_log_json(db, run_id, action_log_path)
    metrics = compute_run_metrics(db, run_id)
    report = evaluate_run(db, run_id, config.scenario_id)
    write_eval_artifacts(report, artifact_dir)
    timeline = write_interaction_timeline(db, run_id, timeline_path)
    summary = format_run_summary(
      scenario_id=config.scenario_id,
      agent_id=config.agent_id,
      status=status,
      total_turns=turn,
      wait_turns=wait_turns,
      launch_sim_datetime=metrics.launch_sim_datetime,
      time_to_blocker_known=metrics.time_to_blocker_known,
      rubric_total=report.rubric.total,
    )
    summary = summary + "\n\n" + timeline
    clear_run_context(db)

  return RunResult(
    run_id=run_id,
    scenario_id=config.scenario_id,
    agent_id=config.agent_id,
    status=status,
    total_turns=turn,
    wait_turns=wait_turns,
    artifact_dir=artifact_dir,
    summary=summary,
  )
