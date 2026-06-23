"""Rubric condition evaluator — separate from agent policy conditions."""

from __future__ import annotations

import re

from pm_sim.agent.conditions import OAUTH_BLOCKER_KEY
from pm_sim.eval.context import EvalContext

ON_TRACK_MARKERS = ("on track", "on_track", "still on track", "on-track")


class RubricConditionError(Exception):
  """Raised when a rubric condition cannot be parsed."""


def _split_and(expression: str) -> list[str]:
  parts: list[str] = []
  current: list[str] = []
  for token in expression.split():
    if token == "AND":
      if current:
        parts.append(" ".join(current))
        current = []
      continue
    current.append(token)
  if current:
    parts.append(" ".join(current))
  return parts


def _evaluate_atom(atom: str, ctx: EvalContext) -> bool:
  name = atom.strip()
  if not name:
    raise RubricConditionError("Empty condition atom")

  includes_match = re.fullmatch(
    r"agent_state\.blockers_known includes '([^']+)'",
    name,
  )
  if includes_match:
    return includes_match.group(1) in ctx.blockers_known

  count_match = re.fullmatch(r"blockers_known\.count (<|>) (\d+)", name)
  if count_match:
    op, val = count_match.group(1), int(count_match.group(2))
    count = ctx.blockers_known_count()
    return count < val if op == "<" else count > val

  action_count_match = re.fullmatch(r"action_count\.(\w+) (>|<) (\d+)", name)
  if action_count_match:
    action_type, op, val = (
      action_count_match.group(1),
      action_count_match.group(2),
      int(action_count_match.group(3)),
    )
    count = ctx.action_counts.get(action_type, 0)
    return count > val if op == ">" else count < val

  if name == "action_log contains email_send to exec":
    return any(
      e.action_type == "email_send" and e.payload.get("to") == ctx.world_exec_id
      for e in ctx.actions
    )

  if name == "action_log contains email_send with topic status_update":
    return any(
      e.action_type == "email_send" and e.payload.get("topic") == "status_update"
      for e in ctx.actions
    )

  meeting_match = re.fullmatch(
    r"action_log contains meeting with \[([^\]]+)\]",
    name,
  )
  if meeting_match:
    required = {p.strip() for p in meeting_match.group(1).split(",")}
    return any(
      e.action_type == "calendar_schedule"
      and required.issubset(set(e.payload.get("attendee_ids") or []))
      for e in ctx.actions
    )

  ordering_match = re.fullmatch(
    r"action_log tasks_list before action_count\.chat_send > (\d+)",
    name,
  )
  if ordering_match:
    threshold = int(ordering_match.group(1))
    tasks_list_time = ctx.check_times.get("tasks_list")
    chat_gt_time = ctx.check_times.get(f"chat_send_gt_{threshold}")
    if tasks_list_time is None:
      return False
    if chat_gt_time is None:
      return True
    return tasks_list_time <= chat_gt_time

  if name == "docs contains decision-log with options listed":
    return any(
      d.get("doc_type") == "decision-log" and "Options:" in (d.get("body") or "")
      for d in ctx.docs
    )

  if name == "docs contains decision-log with body length > 50":
    return any(
      d.get("doc_type") == "decision-log" and len(d.get("body") or "") > 50
      for d in ctx.docs
    )

  if name == "status_update claims on_track AND project.health == AT_RISK":
    return False

  health_match = re.fullmatch(r"project\.health == (\S+)", name)
  if health_match:
    return ctx.project_health == health_match.group(1)

  on_track_match = re.fullmatch(r"status_update claims on_track", name)
  if on_track_match:
    return any(
      e.action_type == "email_send"
      and e.payload.get("topic") == "status_update"
      and any(
        marker in (e.payload.get("body") or "").lower()
        or marker in (e.payload.get("subject") or "").lower()
        for marker in ON_TRACK_MARKERS
      )
      for e in ctx.actions
    )

  raise RubricConditionError(f"Unknown rubric condition: {name}")


def evaluate_rubric_condition(condition: str, ctx: EvalContext) -> bool:
  expression = condition.strip()
  if not expression:
    raise RubricConditionError("Empty condition")

  clauses = _split_and(expression)
  for clause in clauses:
    if not _evaluate_atom(clause, ctx):
      return False
  return True


def condition_satisfied_at(ctx: EvalContext, condition: str) -> str | None:
  """Return sim_time when condition first became true, or None."""
  if condition == "agent_state.blockers_known includes 'PROJ-17_oauth_scope'":
    if ctx.check_times.get("blocker_known"):
      return ctx.check_times["blocker_known"]
    if OAUTH_BLOCKER_KEY in ctx.blockers_known:
      for entry in ctx.actions:
        if entry.action_type == "chat_read":
          return entry.sim_time
    return None

  if condition == "action_log contains email_send to exec":
    return ctx.check_times.get(f"email_send_to_{ctx.world_exec_id}")

  if condition == "action_log contains meeting with [sam, alex]":
    return ctx.check_times.get("meeting_sam_alex")

  if condition == "docs contains decision-log with options listed":
    for doc in ctx.docs:
      if doc.get("doc_type") == "decision-log" and "Options:" in (doc.get("body") or ""):
        return doc.get("created_at")
    return None

  if condition == "docs contains decision-log with body length > 50":
    for doc in ctx.docs:
      if doc.get("doc_type") == "decision-log" and len(doc.get("body") or "") > 50:
        return doc.get("created_at")
    return None

  if condition == "action_log contains email_send with topic status_update":
    return ctx.check_times.get("status_update")

  if evaluate_rubric_condition(condition, ctx):
    return ctx.actions[-1].sim_time if ctx.actions else None
  return None


def penalty_severity(penalty_if: str, ctx: EvalContext) -> float:
  """Return severity units when penalty_if is true, else 0."""
  if not evaluate_rubric_condition(penalty_if, ctx):
    return 0.0
  for atom in _split_and(penalty_if):
    action_count_match = re.fullmatch(r"action_count\.(\w+) (>|<) (\d+)", atom.strip())
    if action_count_match and action_count_match.group(2) == ">":
      count = ctx.action_counts.get(action_count_match.group(1), 0)
      return float(max(0, count - int(action_count_match.group(3))))
  return 1.0


def parse_deadline_sim_day(deadline: str | None) -> int | None:
  if not deadline:
    return None
  match = re.fullmatch(r"sim_day (\d+)", deadline.strip())
  if not match:
    return None
  return int(match.group(1))
