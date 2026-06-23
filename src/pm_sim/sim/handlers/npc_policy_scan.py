"""npc.policy_scan — proactive NPC policy evaluation."""

from __future__ import annotations

import uuid

from pm_sim.npcs.actions import plan_reply
from pm_sim.npcs.resolver import pick_matching_template
from pm_sim.npcs.types import NpcContext
from pm_sim.sim.clock import format_sim_time, get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent
from pm_sim.tools.base import dm_channel


def handle_npc_policy_scan(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  payload = event.payload or {}
  target_id = payload.get("coworker_id")

  if target_id:
    coworker_ids = [target_id]
  else:
    rows = db.conn.execute(
      "SELECT DISTINCT coworker_id FROM coworker_policies ORDER BY coworker_id"
    ).fetchall()
    coworker_ids = [row["coworker_id"] for row in rows]

  followups: list[SimEvent] = []
  ctx = NpcContext(coworker_id="", channel="", topic=None, message_kind="dm")

  for coworker_id in coworker_ids:
    ctx = NpcContext(coworker_id=coworker_id, channel=dm_channel(coworker_id))
    template = pick_matching_template(db, coworker_id, "policy_scan", ctx)
    if template is None:
      continue

    plan = plan_reply(db, template, ctx)
    if template.action != "dm_agent":
      continue

    channel = dm_channel(coworker_id)
    sim_time = get_sim_time(db)
    msg_id = str(uuid.uuid4())
    db.conn.execute(
      """
      INSERT INTO chat_messages (id, channel, sender_id, body, sent_at)
      VALUES (?, ?, ?, ?, ?)
      """,
      (msg_id, channel, coworker_id, plan.body, format_sim_time(sim_time)),
    )

  return followups
