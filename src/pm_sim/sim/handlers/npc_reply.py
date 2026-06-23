"""npc.reply — policy-driven NPC response handler."""

from __future__ import annotations

import uuid

from pm_sim.npcs.actions import apply_reply_side_effects
from pm_sim.npcs.templates import load_message_templates
from pm_sim.npcs.types import NpcReplyPlan
from pm_sim.sim.clock import format_sim_time, get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent
from pm_sim.tools.base import dm_channel


def handle_npc_reply(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  payload = event.payload
  coworker_id = payload.get("coworker_id", "alex")
  channel = payload.get("channel") or dm_channel(coworker_id)
  action = payload.get("action", "ack")
  scenario_id = db.get_meta("scenario_id") or "first-week-pm"

  body = payload.get("body")
  if not body:
    messages = load_message_templates(scenario_id)
    body = messages.get(action, messages.get("ack", "Got it, thanks."))

  sim_time = get_sim_time(db)
  msg_id = str(uuid.uuid4())
  db.conn.execute(
    """
    INSERT INTO chat_messages (id, channel, sender_id, body, sent_at)
    VALUES (?, ?, ?, ?, ?)
    """,
    (msg_id, channel, coworker_id, body, format_sim_time(sim_time)),
  )

  plan = NpcReplyPlan(
    template_id=payload.get("template_id", action),
    action=action,
    body=body,
    disclose_blocker=bool(payload.get("disclose_blocker")),
  )
  apply_reply_side_effects(db, plan)

  return []
