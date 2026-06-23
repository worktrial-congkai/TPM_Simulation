"""Stdout rendering for turn log blocks during pm-sim run."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live

from pm_sim.display.turn_collapser import TurnLogPushResult


class TurnStdoutRenderer:
  """Mirror CollapsingTurnLogWriter: one live region rewritten per streak."""

  def __init__(self, console: Console) -> None:
    self._console = console
    self._live: Live | None = None

  def emit(self, result: TurnLogPushResult) -> None:
    if result.flushed_block:
      self._end_live_streak()

    if result.finalize:
      self._end_live_streak()
      return

    if result.live_block:
      self._update_live(result.live_block)

  def close(self) -> None:
    self._end_live_streak()

  def _update_live(self, block: str) -> None:
    if self._live is None:
      self._live = Live(
        console=self._console,
        refresh_per_second=4,
        transient=False,
        vertical_overflow="visible",
      )
      self._live.start()
    self._live.update(block)

  def _end_live_streak(self) -> None:
    if self._live is None:
      return
    self._live.stop()
    self._live = None
