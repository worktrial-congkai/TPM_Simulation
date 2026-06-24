"""Meeting.end — complete meeting and apply NPC design gate."""

from __future__ import annotations

import json

from pm_sim.agent.state import set_flag
from pm_sim.npcs.actions import PROJ22_UNBLOCKED_LABEL, execute_world_action, plan_reply
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
  world_effects: list[str] = []
  if template is not None:
    plan = plan_reply(db, template, ctx)
    if execute_world_action(db, plan.action):
      if plan.action == "unblock_proj_22":
        world_effects.append(PROJ22_UNBLOCKED_LABEL)

  if meeting_type == "requirements":
    set_flag(db, "requirements_meeting_held", True)
  elif meeting_type == "tradeoff":
    set_flag(db, "tradeoff_meeting_held", True)

  if world_effects:
    payload = dict(event.payload or {})
    payload["world_effects"] = world_effects
    db.conn.execute(
      "UPDATE events SET payload = ? WHERE id = ?",
      (json.dumps(payload), event.id),
    )

  return []
