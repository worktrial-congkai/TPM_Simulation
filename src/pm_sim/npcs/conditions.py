"""NPC policy condition evaluator."""

from __future__ import annotations

import re

from pm_sim.agent.state import get_flag
from pm_sim.npcs.types import NpcContext
from pm_sim.sim.clock import get_sim_time, parse_sim_time
from pm_sim.sim.db import SimDatabase


class NpcConditionError(Exception):
  """Raised when an NPC condition cannot be parsed or evaluated."""


def _sim_day(db: SimDatabase) -> int:
  start_raw = db.get_meta("start_time")
  if not start_raw:
    return 1
  sim_time = get_sim_time(db)
  start_time = parse_sim_time(start_raw)
  return (sim_time.date() - start_time.date()).days + 1


def _channel_is_dm(ctx: NpcContext) -> bool:
  return ctx.channel.startswith("dm:") or ctx.message_kind == "dm"


def _evaluate_atom(atom: str, ctx: NpcContext, db: SimDatabase) -> bool:
  name = atom.strip()
  if not name:
    raise NpcConditionError("Empty condition atom")

  sim_day_match = re.fullmatch(r"sim_day >= (\d+)", name)
  if sim_day_match:
    return _sim_day(db) >= int(sim_day_match.group(1))

  eq_match = re.fullmatch(r"(\w+) == (\S+)", name)
  if eq_match:
    key, value = eq_match.group(1), eq_match.group(2)
    if key == "channel":
      if value == "dm":
        return _channel_is_dm(ctx)
      return ctx.channel == value
    if key == "topic":
      return (ctx.topic or "") == value
    if key == "meeting_type":
      return (ctx.meeting_type or "") == value

  neq_match = re.fullmatch(r"(\w+) != (\S+)", name)
  if neq_match:
    key, value = neq_match.group(1), neq_match.group(2)
    if key == "channel":
      if value == "dm":
        return not _channel_is_dm(ctx)
      return ctx.channel != value

  if name == "tradeoff_decision":
    return bool(get_flag(db, "tradeoff_documented", False))

  raise NpcConditionError(f"Unknown NPC condition identifier: {name}")


def _split_and(expression: str) -> list[str]:
  parts: list[str] = []
  current: list[str] = []
  tokens = expression.split()
  i = 0
  while i < len(tokens):
    token = tokens[i]
    if token == "AND":
      if current:
        parts.append(" ".join(current))
        current = []
      i += 1
      continue
    current.append(token)
    i += 1
  if current:
    parts.append(" ".join(current))
  return parts


def evaluate_npc_condition(condition: str, ctx: NpcContext, db: SimDatabase) -> bool:
  expression = condition.strip()
  if not expression:
    return True

  clauses = _split_and(expression)
  for clause in clauses:
    clause = clause.strip()
    if clause.startswith("NOT "):
      if _evaluate_atom(clause[4:], ctx, db):
        return False
    elif not _evaluate_atom(clause, ctx, db):
      return False
  return True
