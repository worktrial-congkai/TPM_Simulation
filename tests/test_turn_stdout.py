"""Tests for stdout turn rendering."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from pm_sim.agent.policies import load_agent_spec
from pm_sim.agent.world import world_config_from_meta
from pm_sim.display.turn_collapser import TurnLogPushResult
from pm_sim.display.turn_stdout import TurnStdoutRenderer
from pm_sim.sim.reset import reset_scenario
from pm_sim.sim.run_loop import RunConfig, run_simulation


def _wait_block(turn: int) -> str:
  return "\n".join(
    [
      f"[Turn {turn}, Mon 9:00 AM, Day 1]",
      "  OBSERVE:  health: ON_TRACK",
      "  ACTION:   wait",
      "  RESULT:   SIM: +1min",
    ]
  )


def _collapsed_block(start: int, end: int) -> str:
  count = end - start + 1
  return "\n".join(
    [
      f"[Turn {start}–{end}, Mon 9:00–9:0{end} AM, Day 1]",
      "  OBSERVE:  health: ON_TRACK",
      "  ACTION:   wait",
      f"  RESULT:   SIM: +{count}min ({count}× wait)",
    ]
  )


def test_stdout_renderer_updates_streak_in_place() -> None:
  buffer = StringIO()
  renderer = TurnStdoutRenderer(Console(file=buffer, force_terminal=True, width=120))
  renderer.emit(TurnLogPushResult(live_block=_wait_block(1)))
  renderer.emit(
    TurnLogPushResult(
      live_block=_collapsed_block(1, 2),
      in_place=True,
    )
  )
  renderer.emit(
    TurnLogPushResult(
      live_block=_collapsed_block(1, 3),
      in_place=True,
    )
  )
  renderer.close()

  output = buffer.getvalue()
  assert output.count("[Turn ") == 1
  assert "Turn 1–3" in output
  assert "ACTION:" in output
  assert "RESULT:" in output


def test_stdout_renderer_prints_flushed_then_new_turn() -> None:
  buffer = StringIO()
  renderer = TurnStdoutRenderer(Console(file=buffer, force_terminal=True, width=120))
  renderer.emit(TurnLogPushResult(live_block=_wait_block(1)))
  renderer.emit(
    TurnLogPushResult(
      live_block=_collapsed_block(1, 2),
      in_place=True,
    )
  )
  renderer.emit(
    TurnLogPushResult(
      flushed_block=_collapsed_block(1, 2),
      live_block=_wait_block(3),
    )
  )
  renderer.close()

  output = buffer.getvalue()
  assert output.count("[Turn ") == 2
  assert "Turn 1–2" in output
  assert "[Turn 3," in output


def test_stdout_matches_turn_log_collapse_for_wait_streak(tmp_path: Path) -> None:
  fixture = Path(__file__).resolve().parent / "fixtures" / "wait_only.yaml"
  db = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  buffer = StringIO()
  renderer = TurnStdoutRenderer(Console(file=buffer, force_terminal=True, width=120))
  try:
    spec = load_agent_spec(fixture)
    world = world_config_from_meta(db)
    result = run_simulation(
      db,
      spec,
      world=world,
      config=RunConfig(
        scenario_id="first-week-pm",
        agent_id="wait_only",
        max_turns=5,
        artifact_root=tmp_path / "runs",
      ),
      on_turn=renderer.emit,
    )
    renderer.close()
  finally:
    db.close()

  stdout = buffer.getvalue()
  turn_log = (result.artifact_dir / "turn.log").read_text(encoding="utf-8")
  assert stdout.count("[Turn ") == turn_log.count("[Turn ")
  assert "×" in stdout or "SIM: +5min" in stdout or "SIM: +4min" in stdout
  assert "ACTION:" in stdout
  assert "RESULT:" in stdout
