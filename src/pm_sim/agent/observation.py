"""Observation snapshot builder."""

from __future__ import annotations

from pm_sim.agent.state import get_flag, set_flag
from pm_sim.agent.types import Observation
from pm_sim.sim.clock import get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.tools.chat import ChatTool
from pm_sim.tools.email import EmailTool


def _resolve_blocker_owner(db: SimDatabase) -> str | None:
  row = db.conn.execute(
    """
    SELECT owner_id FROM tasks
    WHERE critical_path = 1 AND status = 'blocked' AND owner_id IS NOT NULL
    ORDER BY id
    LIMIT 1
    """
  ).fetchone()
  return row["owner_id"] if row else None


def _waiting_on_reply(db: SimDatabase) -> bool:
  row = db.conn.execute(
    """
    SELECT 1 FROM events
    WHERE event_type = 'npc.reply' AND status = 'pending'
    LIMIT 1
    """
  ).fetchone()
  return row is not None


def build_observation(db: SimDatabase) -> Observation:
  blocker_owner = _resolve_blocker_owner(db)
  if blocker_owner is not None:
    set_flag(db, "blocker_owner", blocker_owner)

  blockers_known = get_flag(db, "blockers_known", [])
  stakeholders_informed = get_flag(db, "stakeholders_informed", [])
  unread = ChatTool.list_unread(db)
  unread_channels = tuple(sorted({msg["channel"] for msg in unread}))
  unread_emails = EmailTool.list_unread(db)
  unread_email_ids = tuple(msg["id"] for msg in unread_emails)

  return Observation(
    sim_time=get_sim_time(db),
    blocker_owner=blocker_owner,
    tasks_checked=bool(get_flag(db, "tasks_checked", False)),
    vendor_escalated=bool(get_flag(db, "vendor_escalated", False)),
    requirements_meeting_held=bool(get_flag(db, "requirements_meeting_held", False)),
    tradeoff_documented=bool(get_flag(db, "tradeoff_documented", False)),
    blockers_known=tuple(blockers_known) if isinstance(blockers_known, list) else (),
    stakeholders_informed=(
      tuple(stakeholders_informed) if isinstance(stakeholders_informed, list) else ()
    ),
    waiting_on_reply=_waiting_on_reply(db),
    unread_channels=unread_channels,
    unread_email_ids=unread_email_ids,
  )
