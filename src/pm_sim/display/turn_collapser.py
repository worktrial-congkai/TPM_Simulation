"""Collapse consecutive identical turn log blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_HEADER_RE = re.compile(
  r"^\[Turn (?P<turn>\d+(?:–\d+)?), (?P<time>.+?), (?P<day>Day \d+(?:–\d+)?)\]$"
)


def _format_clock(sim_time: datetime) -> str:
  return sim_time.strftime("%a %I:%M %p").replace(" 0", " ")


def _format_clock_range(start: datetime, end: datetime) -> str:
  if start.date() == end.date():
    start_part = start.strftime("%a %I:%M").replace(" 0", " ")
    end_part = end.strftime("%I:%M %p").replace(" 0", " ")
    return f"{start_part}–{end_part}"
  return f"{_format_clock(start)}–{_format_clock(end)}"


def _day_label(sim_time: datetime, start_time: datetime) -> str:
  day = (sim_time.date() - start_time.date()).days + 1
  return f"Day {day}"


def block_body_signature(block: str) -> tuple[str, ...]:
  lines = block.splitlines()
  if not lines:
    return ()
  return tuple(lines[1:])


def parse_turn_header(block: str) -> tuple[int, datetime | None, str | None]:
  first = block.splitlines()[0] if block else ""
  match = _HEADER_RE.match(first.strip())
  if not match:
    return 0, None, None
  turn_raw = match.group("turn").split("–", 1)[0]
  return int(turn_raw), None, match.group("day")


def _action_label_from_body(body_lines: tuple[str, ...]) -> str:
  for line in body_lines:
    if line.startswith("  ACTION:"):
      return line.removeprefix("  ACTION:").strip()
  return "action"


def _replace_result_sim_line(body_lines: tuple[str, ...], new_result_first_line: str) -> list[str]:
  out: list[str] = []
  replaced = False
  for line in body_lines:
    if not replaced and line.startswith("  RESULT:"):
      out.append(new_result_first_line)
      replaced = True
      continue
    if replaced and line.startswith("          SIM:"):
      continue
    out.append(line)
  if not replaced:
    out.append(new_result_first_line)
  return out


@dataclass
class TurnStreak:
  start_turn: int
  end_turn: int
  start_sim_time: datetime
  end_sim_time: datetime
  start_time: datetime
  body_lines: tuple[str, ...]
  minutes_per_turn: int
  action_label: str

  @property
  def count(self) -> int:
    return self.end_turn - self.start_turn + 1


def format_collapsed_header(streak: TurnStreak) -> str:
  start_day = _day_label(streak.start_sim_time, streak.start_time)
  end_day = _day_label(streak.end_sim_time, streak.start_time)
  if streak.count == 1:
    return (
      f"[Turn {streak.start_turn}, {_format_clock(streak.start_sim_time)}, {start_day}]"
    )
  day_part = start_day if start_day == end_day else f"{start_day}–{end_day.split(' ', 1)[1]}"
  return (
    f"[Turn {streak.start_turn}–{streak.end_turn}, "
    f"{_format_clock_range(streak.start_sim_time, streak.end_sim_time)}, {day_part}]"
  )


def format_collapsed_result(streak: TurnStreak) -> str:
  total_minutes = streak.minutes_per_turn * streak.count
  if streak.count == 1:
    return f"  RESULT:   SIM: +{streak.minutes_per_turn}min"
  return f"  RESULT:   SIM: +{total_minutes}min ({streak.count}× {streak.action_label})"


def format_collapsed_block(streak: TurnStreak) -> str:
  header = format_collapsed_header(streak)
  result_line = format_collapsed_result(streak)
  body = _replace_result_sim_line(streak.body_lines, result_line)
  return "\n".join([header, *body])


@dataclass
class TurnLogPushResult:
  """Outcome of pushing one turn block through the collapser."""

  flushed_block: str | None = None
  live_block: str | None = None
  finalize: bool = False
  in_place: bool = False
  standalone_block: str | None = None


class TurnLogCollapser:
  """Merge consecutive turns with identical block bodies."""

  def __init__(self, *, start_time: datetime) -> None:
    self._start_time = start_time
    self._streak: TurnStreak | None = None

  def push(
    self,
    turn: int,
    sim_time: datetime,
    block: str,
    *,
    minutes_advanced: int,
    action_label: str,
  ) -> TurnLogPushResult:
    body = block_body_signature(block)
    if not body:
      return self._start_new_streak(turn, sim_time, body, minutes_advanced, action_label, block)

    if self._streak is not None and body == self._streak.body_lines:
      self._streak.end_turn = turn
      self._streak.end_sim_time = sim_time
      collapsed = format_collapsed_block(self._streak)
      return TurnLogPushResult(live_block=collapsed, in_place=True)

    return self._start_new_streak(turn, sim_time, body, minutes_advanced, action_label, block)

  def _start_new_streak(
    self,
    turn: int,
    sim_time: datetime,
    body: tuple[str, ...],
    minutes_advanced: int,
    action_label: str,
    block: str,
  ) -> TurnLogPushResult:
    flushed = None
    if self._streak is not None:
      flushed = format_collapsed_block(self._streak)

    label = action_label or _action_label_from_body(body)
    self._streak = TurnStreak(
      start_turn=turn,
      end_turn=turn,
      start_sim_time=sim_time,
      end_sim_time=sim_time,
      start_time=self._start_time,
      body_lines=body,
      minutes_per_turn=minutes_advanced,
      action_label=label,
    )
    return TurnLogPushResult(flushed_block=flushed, live_block=block)

  def flush(self) -> str | None:
    if self._streak is None:
      return None
    block = format_collapsed_block(self._streak)
    self._streak = None
    return block
