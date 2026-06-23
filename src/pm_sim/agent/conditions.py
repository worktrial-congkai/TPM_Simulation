"""Policy condition evaluator."""

from __future__ import annotations

import re

from pm_sim.agent.state import get_flag
from pm_sim.agent.types import Observation
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.task_timers import dependencies_met
from pm_sim.tools.base import AGENT_ID, dm_channel

OAUTH_BLOCKER_KEY = "PROJ-17_oauth_scope"
CONFLICT_SENDERS = ("jordan", "sam")
SPAM_PING_TARGETS = ("alex", "sam", "morgan", "jordan")


class PolicyError(Exception):
  """Raised when a policy condition cannot be parsed or evaluated."""


def _blocked_critical_path_exists(db: SimDatabase) -> bool:
  row = db.conn.execute(
    """
    SELECT 1 FROM tasks
    WHERE critical_path = 1 AND status = 'blocked'
    LIMIT 1
    """
  ).fetchone()
  return row is not None


def _blocker_known(obs: Observation) -> bool:
  return OAUTH_BLOCKER_KEY in obs.blockers_known


def _stakeholder_conflict_detected(db: SimDatabase) -> bool:
  for sender_id in CONFLICT_SENDERS:
    row = db.conn.execute(
      """
      SELECT 1 FROM emails
      WHERE sender_id = ? AND recipient_id = ? AND read_by_agent = 1
      LIMIT 1
      """,
      (sender_id, AGENT_ID),
    ).fetchone()
    if row is None:
      return False
  return True


def _unread_dm(obs: Observation) -> bool:
  return len(obs.unread_channels) > 0


def _unread_email(obs: Observation) -> bool:
  return len(obs.unread_email_ids) > 0


def _unread_dm_from(obs: Observation, target: str) -> bool:
  if target == "blocker_owner":
    if not obs.blocker_owner:
      return False
    target = obs.blocker_owner
  return dm_channel(target) in obs.unread_channels


def _can_spam_ping(db: SimDatabase) -> bool:
  sent_to = get_flag(db, "spam_ping_sent_to", [])
  if not isinstance(sent_to, list):
    sent_to = []
  return any(target not in sent_to for target in SPAM_PING_TARGETS)


def next_ready_critical_task(db: SimDatabase) -> str | None:
  rows = db.conn.execute(
    """
    SELECT id FROM tasks
    WHERE critical_path = 1 AND status = 'todo'
    ORDER BY id
    """
  ).fetchall()
  for row in rows:
    if dependencies_met(db, row["id"]):
      return row["id"]
  return None


def _critical_path_task_ready(db: SimDatabase) -> bool:
  return next_ready_critical_task(db) is not None


def _evaluate_atom(atom: str, obs: Observation, db: SimDatabase) -> bool:
  name = atom.strip()
  if not name:
    raise PolicyError("Empty condition atom")

  dm_match = re.fullmatch(r"unread_dm_from\s+(\S+)", name)
  if dm_match:
    return _unread_dm_from(obs, dm_match.group(1))

  if name == "tasks_checked":
    return obs.tasks_checked
  if name == "vendor_escalated":
    return obs.vendor_escalated
  if name == "requirements_meeting_held":
    return obs.requirements_meeting_held
  if name == "requirements_meeting_scheduled":
    return bool(get_flag(db, "requirements_meeting_scheduled", False))
  if name == "tradeoff_meeting_scheduled":
    return bool(get_flag(db, "tradeoff_meeting_scheduled", False))
  if name == "tradeoff_documented":
    return obs.tradeoff_documented
  if name == "waiting_on_reply":
    return obs.waiting_on_reply
  if name == "unread_dm":
    return _unread_dm(obs)
  if name == "unread_email":
    return _unread_email(obs)
  if name == "blocker_known":
    return _blocker_known(obs)
  if name == "blocker_unknown":
    return _blocked_critical_path_exists(db) and not _blocker_known(obs)
  if name == "stakeholder_conflict_detected":
    return _stakeholder_conflict_detected(db)
  if name == "stakeholders_not_informed":
    return _blocker_known(obs) and "sam" not in obs.stakeholders_informed
  if name == "tradeoff_decision":
    return obs.tradeoff_documented
  if name == "can_spam_ping":
    return _can_spam_ping(db)
  if name == "critical_path_task_ready":
    return _critical_path_task_ready(db)
  if name == "no_urgent_items":
    conflict_open = _stakeholder_conflict_detected(db) and not obs.tradeoff_documented
    return not (
      _unread_dm(obs)
      or _unread_email(obs)
      or (_blocked_critical_path_exists(db) and not _blocker_known(obs))
      or conflict_open
      or obs.waiting_on_reply
    )

  raise PolicyError(f"Unknown condition identifier: {name}")


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


def evaluate_condition(condition: str, obs: Observation, db: SimDatabase) -> bool:
  expression = condition.strip()
  if not expression:
    raise PolicyError("Empty condition")

  clauses = _split_and(expression)
  for clause in clauses:
    clause = clause.strip()
    if clause.startswith("NOT "):
      if _evaluate_atom(clause[4:], obs, db):
        return False
    elif not _evaluate_atom(clause, obs, db):
      return False
  return True
