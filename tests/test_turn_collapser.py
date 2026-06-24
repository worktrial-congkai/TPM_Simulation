"""Tests for turn log collapse."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pm_sim.display.turn_collapser import (
  TurnLogCollapser,
  block_body_signature,
  format_collapsed_block,
)
from pm_sim.display.turn_log import CollapsingTurnLogWriter


def _wait_block(turn: int, hour: int, minute: int) -> str:
  time_label = f"Mon {hour}:{minute:02d} AM" if hour < 12 else f"Mon {hour - 12}:{minute:02d} PM"
  if hour == 19 and minute == 42:
    time_label = "Tue 7:42 PM"
  if hour == 19 and minute == 43:
    time_label = "Tue 7:43 PM"
  if hour == 19 and minute == 44:
    time_label = "Tue 7:44 PM"
  return "\n".join(
    [
      f"[Turn {turn}, {time_label}, Day 2]",
      "  OBSERVE:  chat unread: alex:1, sam:2 | health: ON_TRACK",
      "  ACTION:   wait",
      "  RESULT:   SIM: +1min",
      "          health: ON_TRACK",
    ]
  )


START = datetime(2026, 6, 22, 9, 0, 0)


def test_block_body_signature_ignores_header() -> None:
  block_a = _wait_block(1, 19, 42)
  block_b = _wait_block(2, 19, 43)
  assert block_body_signature(block_a) == block_body_signature(block_b)


def test_collapser_merges_three_waits() -> None:
  collapser = TurnLogCollapser(start_time=START)
  t0 = datetime(2026, 6, 23, 19, 42)
  t1 = datetime(2026, 6, 23, 19, 43)
  t2 = datetime(2026, 6, 23, 19, 44)

  collapser.push(2056, t0, _wait_block(2056, 19, 42), minutes_advanced=1, action_label="wait")
  collapser.push(2057, t1, _wait_block(2057, 19, 43), minutes_advanced=1, action_label="wait")
  result = collapser.push(
    2058, t2, _wait_block(2058, 19, 44), minutes_advanced=1, action_label="wait",
  )

  assert result.flushed_block is None
  assert result.live_block is not None
  assert result.in_place is True
  assert "Turn 2056–2058" in result.live_block
  assert "SIM: +3min (3× wait)" in result.live_block


def test_collapser_splits_on_result_change() -> None:
  collapser = TurnLogCollapser(start_time=START)
  t0 = datetime(2026, 6, 23, 19, 42)
  t1 = datetime(2026, 6, 23, 19, 43)

  wait = _wait_block(1, 19, 42)
  wait_with_event = wait.replace(
    "  RESULT:   SIM: +1min",
    "  RESULT:   SIM: +1min\n          events: alex reply",
  )

  collapser.push(1, t0, wait, minutes_advanced=1, action_label="wait")
  result = collapser.push(2, t1, wait_with_event, minutes_advanced=1, action_label="wait")

  assert result.flushed_block is not None
  assert "[Turn 1," in result.flushed_block
  assert result.live_block == wait_with_event


def test_collapsing_writer_keeps_one_block_for_streak(tmp_path: Path) -> None:
  path = tmp_path / "turn.log"
  writer = CollapsingTurnLogWriter(path, start_time=START)
  t0 = datetime(2026, 6, 23, 19, 42)
  t1 = datetime(2026, 6, 23, 19, 43)
  t2 = datetime(2026, 6, 23, 19, 44)

  writer.push(1, t0, _wait_block(1, 19, 42), minutes_advanced=1, action_label="wait")
  writer.push(2, t1, _wait_block(2, 19, 43), minutes_advanced=1, action_label="wait")
  writer.push(3, t2, _wait_block(3, 19, 44), minutes_advanced=1, action_label="wait")
  writer.flush()

  text = path.read_text(encoding="utf-8")
  assert text.count("[Turn ") == 1
  assert "Turn 1–3" in text
  assert "SIM: +3min (3× wait)" in text


def test_format_collapsed_single_turn() -> None:
  from pm_sim.display.turn_collapser import TurnStreak

  streak = TurnStreak(
    start_turn=5,
    end_turn=5,
    start_sim_time=datetime(2026, 6, 22, 9, 0),
    end_sim_time=datetime(2026, 6, 22, 9, 0),
    start_time=START,
    body_lines=(
      "  OBSERVE:  health: ON_TRACK",
      "  ACTION:   wait",
      "  RESULT:   SIM: +1min",
    ),
    minutes_per_turn=1,
    action_label="wait",
  )
  block = format_collapsed_block(streak)
  assert "[Turn 5," in block
  assert "–" not in block.splitlines()[0]
  assert "SIM: +1min" in block
  assert "3×" not in block


def test_run_loop_suppresses_empty_wait_turns_in_turn_log(tmp_path: Path) -> None:
  from pm_sim.agent.policies import load_agent_spec
  from pm_sim.agent.world import world_config_from_meta
  from pm_sim.sim.reset import reset_scenario
  from pm_sim.sim.run_loop import RunConfig, run_simulation

  fixture = Path(__file__).resolve().parent / "fixtures" / "wait_only.yaml"
  db = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
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
        quiet=True,
        artifact_root=tmp_path / "runs",
      ),
    )
    text = (result.artifact_dir / "turn.log").read_text(encoding="utf-8")
    assert "[Turn " not in text
    assert result.wait_turns == 5
  finally:
    db.close()
