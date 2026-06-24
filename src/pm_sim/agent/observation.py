"""Observation snapshot builder."""

from __future__ import annotations

import json
from collections import Counter

from pm_sim.agent.conditions import stakeholder_conflicts
from pm_sim.agent.state import get_flag, set_flag
from pm_sim.agent.types import Observation, PendingReply
from pm_sim.sim.clock import get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.health import compute_project_health
from pm_sim.tools.chat import ChatTool
from pm_sim.tools.email import EmailTool


def _task_label(task_id: str, title: str) -> str:
  return f"{task_id} ({title})"


def _blocked_critical_tasks(db: SimDatabase) -> tuple[str, ...]:
  rows = db.conn.execute(
    """
    SELECT id, title FROM tasks
    WHERE critical_path = 1 AND status = 'blocked'
    ORDER BY id
    """
  ).fetchall()
  return tuple(_task_label(row["id"], row["title"]) for row in rows)


def _resolve_blocker_focus(db: SimDatabase) -> tuple[str | None, str | None]:
  row = db.conn.execute(
    """
    SELECT id, owner_id FROM tasks
    WHERE critical_path = 1 AND status = 'blocked' AND owner_id IS NOT NULL
    ORDER BY id
    LIMIT 1
    """
  ).fetchone()
  if row is None:
    return None, None
  return row["id"], row["owner_id"]


def _pending_replies(db: SimDatabase) -> tuple[PendingReply, ...]:
  rows = db.conn.execute(
    """
    SELECT actor_id, payload FROM events
    WHERE event_type = 'npc.reply' AND status = 'pending'
    ORDER BY start_ts, id
    """
  ).fetchall()
  pending: list[PendingReply] = []
  for row in rows:
    payload = json.loads(row["payload"]) if row["payload"] else {}
    pending.append(
      PendingReply(
        actor_id=row["actor_id"] or "npc",
        channel=payload.get("channel", ""),
      )
    )
  return tuple(pending)


def build_observation(db: SimDatabase) -> Observation:
  blocker_task_id, blocker_owner = _resolve_blocker_focus(db)
  if blocker_owner is not None:
    set_flag(db, "blocker_owner", blocker_owner)

  blockers_known = get_flag(db, "blockers_known", [])
  stakeholders_informed = get_flag(db, "stakeholders_informed", [])
  unread = ChatTool.list_unread(db)
  unread_by_channel = Counter(msg["channel"] for msg in unread)
  unread_channels = tuple(sorted(unread_by_channel))
  unread_chat_by_channel = tuple(
    (channel, unread_by_channel[channel]) for channel in unread_channels
  )
  unread_emails = EmailTool.list_unread(db)
  unread_email_ids = tuple(msg["id"] for msg in unread_emails)
  pending_replies = _pending_replies(db)
  tradeoff_meeting_held = bool(get_flag(db, "tradeoff_meeting_held", False))
  conflicts = () if tradeoff_meeting_held else stakeholder_conflicts(db)

  return Observation(
    sim_time=get_sim_time(db),
    blocker_owner=blocker_owner,
    blocker_task_id=blocker_task_id,
    tasks_checked=bool(get_flag(db, "tasks_checked", False)),
    vendor_escalated=bool(get_flag(db, "vendor_escalated", False)),
    requirements_meeting_held=bool(get_flag(db, "requirements_meeting_held", False)),
    tradeoff_documented=bool(get_flag(db, "tradeoff_documented", False)),
    blockers_known=tuple(blockers_known) if isinstance(blockers_known, list) else (),
    stakeholders_informed=(
      tuple(stakeholders_informed) if isinstance(stakeholders_informed, list) else ()
    ),
    waiting_on_reply=bool(pending_replies),
    pending_replies=pending_replies,
    unread_channels=unread_channels,
    unread_chat_by_channel=unread_chat_by_channel,
    unread_email_ids=unread_email_ids,
    blocked_tasks=_blocked_critical_tasks(db),
    health=compute_project_health(db),
    stakeholder_conflicts=conflicts,
  )
