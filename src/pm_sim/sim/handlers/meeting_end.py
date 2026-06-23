"""Meeting.end — complete meeting and apply NPC design gate."""

from __future__ import annotations

from pm_sim.npcs.actions import execute_world_action, plan_reply
from pm_sim.npcs.resolver import pick_meeting_template
from pm_sim.npcs.types import NpcContext
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent


DEFAULT_TRANSCRIPT = (
  "Meeting notes: requirements reviewed and design sign-off path discussed."
)


def handle_meeting_end(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  meeting_id = event.payload.get("meeting_id")
  if not meeting_id:
    return []

  row = db.conn.execute(
    "SELECT * FROM meetings WHERE id = ?",
    (meeting_id,),
  ).fetchone()
  if row is None or row["completed"]:
    return []

  meeting_type = event.payload.get("meeting_type") or row["meeting_type"]
  transcript = event.payload.get("transcript") or DEFAULT_TRANSCRIPT

  db.conn.execute(
    """
    UPDATE meetings
    SET completed = 1, transcript = ?
    WHERE id = ?
    """,
    (transcript, meeting_id),
  )

  ctx = NpcContext(
    coworker_id="morgan",
    meeting_type=meeting_type,
  )
  template = pick_meeting_template(db, ctx)
  if template is not None:
    plan = plan_reply(db, template, ctx)
    execute_world_action(db, plan.action)

  return []
